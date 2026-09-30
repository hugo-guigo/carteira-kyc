"""Carteira em partidas dobradas. Não existe coluna de saldo: o saldo é a soma dos lançamentos.

Cada Transacao (depósito ou saque) tem dois Lancamento que somam zero: um na conta do cliente e o oposto
na conta de sistema "caixa externo", que representa o dinheiro de fora. Um trigger do Postgres
(migração 0002) confere a soma no fim de cada transação do banco e recusa as duas tabelas a UPDATE e DELETE.
"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

LIMITE_CENTAVOS = 1_000_000  # R$ 10.000,00 por operação (demo)
CAIXA_EXTERNO = "caixa-externo"


class Conta(models.Model):
    class Tipo(models.TextChoices):
        CLIENTE = "cliente", "Cliente"
        SISTEMA = "sistema", "Sistema"

    dono = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                related_name="conta")
    tipo = models.CharField(max_length=8, choices=Tipo.choices, default=Tipo.CLIENTE)
    nome = models.CharField(max_length=40, blank=True)  # só nas contas de sistema
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(tipo="cliente") & Q(dono__isnull=False)) | (Q(tipo="sistema") & Q(dono__isnull=True)
                                                                         & ~Q(nome="")),
                name="conta_cliente_tem_dono_sistema_tem_nome"),
            models.UniqueConstraint(fields=["nome"], condition=Q(tipo="sistema"), name="nome_unico_conta_sistema"),
        ]

    def __str__(self) -> str:
        return self.nome or f"conta de {self.dono_id}"


class Transacao(models.Model):
    class Tipo(models.TextChoices):
        DEPOSITO = "deposito", "Depósito"
        SAQUE = "saque", "Saque"

    # UUID: o id aparece na API e não deve ser sequencial (não dá para adivinhar o de outra pessoa)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conta = models.ForeignKey(Conta, on_delete=models.PROTECT, related_name="transacoes")
    tipo = models.CharField(max_length=8, choices=Tipo.choices)
    valor_centavos = models.BigIntegerField()
    chave_idempotencia = models.CharField(max_length=64)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="transacoes")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # A mesma chave não grava duas vezes na mesma conta, nem com duas requisições simultâneas.
            models.UniqueConstraint(fields=["conta", "chave_idempotencia"], name="idempotencia_por_conta"),
            models.CheckConstraint(condition=Q(valor_centavos__gt=0) & Q(valor_centavos__lte=LIMITE_CENTAVOS),
                                   name="valor_da_transacao_no_limite"),
        ]


class Lancamento(models.Model):
    transacao = models.ForeignKey(Transacao, on_delete=models.PROTECT, related_name="lancamentos")
    # Sem o índice simples que o Django cria em toda chave estrangeira: o índice do extrato começa pela
    # conta e atende as mesmas buscas (migração 0004).
    conta = models.ForeignKey(Conta, on_delete=models.PROTECT, related_name="lancamentos", db_index=False)
    valor_centavos = models.BigIntegerField()  # positivo entra na conta, negativo sai
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=~Q(valor_centavos=0), name="lancamento_nao_nulo")]
        indexes = [
            # Extrato: as linhas da conta já saem na ordem da tela, sem ordenar o histórico inteiro.
            # INCLUDE valor_centavos: o saldo (soma da conta) sai só do índice, sem ler a tabela.
            # Medido em docs/explain-extrato.md.
            models.Index(fields=["conta", "-criado_em", "-id"], include=["valor_centavos"],
                         name="lancamento_extrato"),
        ]

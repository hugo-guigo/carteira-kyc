import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Status(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    APROVADA = "aprovada", "Aprovada"
    RECUSADA = "recusada", "Recusada"


def caminho_documento(instancia: "Verificacao", nome: str) -> str:
    # nome aleatório: o nome original do arquivo não vai para o disco nem para a URL
    extensao = nome.rsplit(".", 1)[-1].lower() if "." in nome else "bin"
    return f"kyc/{instancia.cliente_id}/{uuid.uuid4().hex}.{extensao}"


class Verificacao(models.Model):
    """Um pedido de verificação de identidade (KYC). Recusado, o cliente pode enviar outro."""

    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="verificacoes")
    nome_completo = models.CharField(max_length=120)
    cpf = models.CharField(max_length=11)
    data_nascimento = models.DateField()
    documento = models.FileField(upload_to=caminho_documento)
    documento_tipo = models.CharField(max_length=40)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDENTE)
    motivo_recusa = models.TextField(blank=True)
    decidido_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="decisoes")
    decidido_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criado_em"]
        constraints = [
            # No máximo um pedido em aberto ou aprovado por cliente. Índice único parcial do Postgres:
            # vale mesmo se duas requisições chegarem juntas, onde uma checagem só no Python falharia.
            models.UniqueConstraint(fields=["cliente"], condition=Q(status__in=["pendente", "aprovada"]),
                                    name="uma_verificacao_ativa_por_cliente"),
            models.CheckConstraint(condition=~Q(status="recusada") | ~Q(motivo_recusa=""),
                                   name="recusa_exige_motivo"),
        ]
        indexes = [models.Index(fields=["status", "criado_em"], name="fila_por_status")]


class EventoAuditoria(models.Model):
    """Trilha de auditoria: quem fez o quê e quando. Só recebe INSERT (trigger na migração 0002).

    Cada evento aponta para exatamente um alvo: uma verificação (KYC) ou uma transação da carteira
    (migração 0003, que acrescentou a coluna transacao).
    """

    ator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="eventos")
    acao = models.CharField(max_length=40)
    verificacao = models.ForeignKey(Verificacao, null=True, blank=True, on_delete=models.PROTECT,
                                    related_name="eventos")
    transacao = models.ForeignKey("carteira.Transacao", null=True, blank=True, on_delete=models.PROTECT,
                                  related_name="eventos")
    dados = models.JSONField(default=dict)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(verificacao__isnull=False) & Q(transacao__isnull=True))
                | (Q(verificacao__isnull=True) & Q(transacao__isnull=False)),
                name="evento_tem_um_alvo"),
        ]

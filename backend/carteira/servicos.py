"""Regras da carteira, fora das views para serem testadas sem HTTP.

Toda operação grava a transação, os dois lançamentos e o evento de auditoria numa única transação do
banco: ou tudo entra, ou nada entra.
"""
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import Sum

from carteira.models import CAIXA_EXTERNO, LIMITE_CENTAVOS, Conta, Lancamento, Transacao
from kyc.models import EventoAuditoria


class SemConta(Exception):
    """O cliente ainda não tem conta (KYC não aprovado)."""


class SaldoInsuficiente(Exception):
    pass


class ChaveReusada(Exception):
    """A chave de idempotência já foi usada com outro pedido (outro valor ou outro tipo)."""


@dataclass(frozen=True)
class Resultado:
    transacao: Transacao
    repetida: bool  # True quando a chave já existia e a transação original foi devolvida


def saldo(conta: Conta) -> int:
    return conta.lancamentos.aggregate(total=Sum("valor_centavos"))["total"] or 0


def conta_do(cliente) -> Conta:
    try:
        return Conta.objects.get(dono=cliente)
    except Conta.DoesNotExist:
        raise SemConta("a conta é liberada depois da aprovação do KYC") from None


def caixa_externo() -> Conta:
    """A contrapartida de depósitos e saques. A migração 0002 cria; get_or_create cobre um banco em que a
    linha foi apagada (os testes com threads limpam as tabelas com TRUNCATE). O índice único parcial
    impede dois caixas mesmo se duas requisições tentarem criar ao mesmo tempo."""
    return Conta.objects.get_or_create(tipo=Conta.Tipo.SISTEMA, nome=CAIXA_EXTERNO)[0]


def abrir_conta(cliente) -> Conta:
    """Chamado dentro da transação que aprova o KYC."""
    return Conta.objects.get_or_create(dono=cliente, defaults={"tipo": Conta.Tipo.CLIENTE})[0]


def _repetida(conta: Conta, chave: str, tipo: str, valor: int) -> Resultado | None:
    original = Transacao.objects.filter(conta=conta, chave_idempotencia=chave).first()
    if original is None:
        return None
    if (original.tipo, original.valor_centavos) != (tipo, valor):
        raise ChaveReusada("esta chave de idempotência já foi usada com outro pedido")
    return Resultado(original, repetida=True)


def depositar(cliente, valor_centavos: int, chave: str) -> Resultado:
    return _operar(cliente, Transacao.Tipo.DEPOSITO, valor_centavos, chave)


def sacar(cliente, valor_centavos: int, chave: str) -> Resultado:
    return _operar(cliente, Transacao.Tipo.SAQUE, valor_centavos, chave)


def _operar(cliente, tipo: str, valor: int, chave: str) -> Resultado:
    if not 0 < valor <= LIMITE_CENTAVOS:
        raise ValueError(f"o valor deve ficar entre 1 e {LIMITE_CENTAVOS} centavos")
    conta = conta_do(cliente)
    anterior = _repetida(conta, chave, tipo, valor)  # caminho rápido: repetição sem travar nada
    if anterior:
        return anterior
    try:
        return _gravar(conta, cliente, tipo, valor, chave)
    except IntegrityError as erro:
        # Duas requisições com a mesma chave chegaram juntas e a outra gravou primeiro: o índice único
        # barrou esta. Devolve a transação que ficou gravada.
        repetida = _repetida(conta, chave, tipo, valor) if "idempotencia_por_conta" in str(erro) else None
        if repetida is None:
            raise
        return repetida


@transaction.atomic
def _gravar(conta: Conta, cliente, tipo: str, valor: int, chave: str) -> Resultado:
    # Trava a linha da conta até o fim da transação. Dois saques simultâneos na mesma conta passam por
    # aqui um de cada vez, e o segundo calcula o saldo já com o primeiro descontado.
    conta = Conta.objects.select_for_update().get(pk=conta.pk)
    if tipo == Transacao.Tipo.SAQUE and saldo(conta) < valor:
        raise SaldoInsuficiente("saldo insuficiente")
    caixa = caixa_externo()
    t = Transacao.objects.create(conta=conta, tipo=tipo, valor_centavos=valor, chave_idempotencia=chave,
                                 criado_por=cliente)
    sinal = 1 if tipo == Transacao.Tipo.DEPOSITO else -1
    Lancamento.objects.bulk_create([
        Lancamento(transacao=t, conta=conta, valor_centavos=sinal * valor),
        Lancamento(transacao=t, conta=caixa, valor_centavos=-sinal * valor),
    ])
    EventoAuditoria.objects.create(ator=cliente, acao=tipo, transacao=t,
                                   dados={"valor_centavos": valor, "conta": conta.pk})
    return Resultado(t, repetida=False)

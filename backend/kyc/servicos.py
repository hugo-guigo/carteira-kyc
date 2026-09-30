"""Regras do KYC, fora das views para serem testadas sem HTTP.

Toda mudança de estado grava um EventoAuditoria na mesma transação: ou as duas coisas acontecem, ou nenhuma.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone

from carteira.servicos import abrir_conta
from kyc.models import EventoAuditoria, Status, Verificacao


class Conflito(Exception):
    """A operação não vale para o estado atual (ex.: decidir um pedido já decidido)."""


@transaction.atomic
def enviar(cliente, *, nome_completo: str, cpf: str, data_nascimento, documento) -> Verificacao:
    try:
        with transaction.atomic():  # savepoint: o IntegrityError não estraga a transação de fora
            v = Verificacao.objects.create(cliente=cliente, nome_completo=nome_completo, cpf=cpf,
                                           data_nascimento=data_nascimento, documento=documento,
                                           documento_tipo=documento.content_type)
    except IntegrityError as erro:
        if "uma_verificacao_ativa_por_cliente" in str(erro):
            raise Conflito("já existe uma verificação pendente ou aprovada") from erro
        raise
    EventoAuditoria.objects.create(ator=cliente, acao="kyc_enviado", verificacao=v,
                                   dados={"status": v.status})
    return v


@transaction.atomic
def decidir(verificacao_id: int, operador, *, aprovar: bool, motivo: str = "") -> Verificacao:
    # select_for_update trava a linha até o fim da transação: dois operadores decidindo o mesmo
    # pedido ao mesmo tempo não conseguem os dois passar pela checagem de "pendente".
    v = Verificacao.objects.select_for_update().get(pk=verificacao_id)
    if v.status != Status.PENDENTE:
        raise Conflito(f"verificação já está {v.status}")
    if not aprovar and not motivo.strip():
        raise ValueError("recusa exige motivo")
    antes = v.status
    v.status = Status.APROVADA if aprovar else Status.RECUSADA
    v.motivo_recusa = "" if aprovar else motivo.strip()
    v.decidido_por = operador
    v.decidido_em = timezone.now()
    v.save(update_fields=["status", "motivo_recusa", "decidido_por", "decidido_em"])
    if aprovar:
        abrir_conta(v.cliente)  # a conta nasce na mesma transação da aprovação
    EventoAuditoria.objects.create(ator=operador, acao="kyc_aprovado" if aprovar else "kyc_recusado",
                                   verificacao=v, dados={"antes": antes, "depois": v.status,
                                                         "motivo": v.motivo_recusa})
    return v

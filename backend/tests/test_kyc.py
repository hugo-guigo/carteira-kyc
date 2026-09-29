import threading

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction

from kyc import servicos
from kyc.models import EventoAuditoria, Status, Verificacao
from kyc.validadores import cpf_valido
from tests.conftest import dados_envio, documento, gerar_cpf

pytestmark = pytest.mark.django_db


def enviar(api, usuario, **troca):
    return api(usuario).post("/api/kyc/minha", dados_envio(**troca), format="multipart")


def test_cpf_pelos_digitos_verificadores():
    assert cpf_valido("529.982.247-25") and cpf_valido(gerar_cpf("987654321"))
    assert not cpf_valido("529.982.247-24")
    assert not cpf_valido("111.111.111-11") and not cpf_valido("123")


def test_cliente_envia_e_ve_a_propria_verificacao(api, cliente):
    r = enviar(api, cliente)
    assert r.status_code == 201, r.content
    assert r.json()["status"] == "pendente"
    assert api(cliente).get("/api/kyc/minha").json()["id"] == r.json()["id"]
    evento = EventoAuditoria.objects.get()
    assert (evento.acao, evento.ator) == ("kyc_enviado", cliente)


@pytest.mark.parametrize("troca, campo", [
    ({"cpf": "111.111.111-11"}, "cpf"),
    ({"data_nascimento": "2015-01-01"}, "data_nascimento"),
    ({"documento": documento(b"MZ executavel", "application/pdf", "rg.pdf")}, "documento"),  # tipo falso
    ({"documento": documento(b"%PDF" + b"0" * (2 * 1024 * 1024), "application/pdf")}, "documento"),  # > 2 MB
    ({"documento": documento(b"GIF89a", "image/gif", "rg.gif")}, "documento"),
])
def test_envio_invalido_e_400(api, cliente, troca, campo):
    r = enviar(api, cliente, **troca)
    assert r.status_code == 400 and campo in r.json()
    assert not Verificacao.objects.exists()


def test_segundo_envio_com_pedido_pendente_e_409(api, cliente):
    assert enviar(api, cliente).status_code == 201
    assert enviar(api, cliente).status_code == 409
    assert Verificacao.objects.count() == 1


def test_banco_barra_dois_pedidos_ativos_mesmo_fora_da_api(cliente):
    """A regra vale no banco (índice único parcial), não só no código da view."""
    Verificacao.objects.create(cliente=cliente, nome_completo="A", cpf=gerar_cpf(), data_nascimento="1990-01-01",
                               documento="x.pdf", documento_tipo="application/pdf")
    with pytest.raises(IntegrityError), transaction.atomic():
        Verificacao.objects.create(cliente=cliente, nome_completo="A", cpf=gerar_cpf(), data_nascimento="1990-01-01",
                                   documento="y.pdf", documento_tipo="application/pdf")


def test_operador_aprova_e_nao_decide_duas_vezes(api, cliente, operador):
    vid = enviar(api, cliente).json()["id"]
    fila = api(operador).get("/api/kyc/fila").json()["results"]
    assert [v["id"] for v in fila] == [vid]
    r = api(operador).post(f"/api/kyc/{vid}/decisao", {"aprovar": True}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "aprovada"
    assert r.json()["decidido_por_email"] == operador.email
    assert api(operador).post(f"/api/kyc/{vid}/decisao", {"aprovar": False, "motivo": "x"},
                              format="json").status_code == 409
    assert api(operador).get("/api/kyc/fila").json()["results"] == []


def test_recusa_exige_motivo_e_cliente_pode_reenviar(api, cliente, operador):
    vid = enviar(api, cliente).json()["id"]
    sem_motivo = api(operador).post(f"/api/kyc/{vid}/decisao", {"aprovar": False}, format="json")
    assert sem_motivo.status_code == 400
    r = api(operador).post(f"/api/kyc/{vid}/decisao", {"aprovar": False, "motivo": "foto ilegível"}, format="json")
    assert r.json()["status"] == "recusada" and r.json()["motivo_recusa"] == "foto ilegível"
    assert enviar(api, cliente).status_code == 201  # recusado não bloqueia novo envio


def test_decidir_pedido_inexistente_e_404(api, operador):
    assert api(operador).post("/api/kyc/999/decisao", {"aprovar": True}, format="json").status_code == 404


@pytest.mark.parametrize("papel", ["cliente", "compliance"])
def test_so_operador_ve_fila_e_decide(api, cliente, compliance, papel):
    vid = enviar(api, cliente).json()["id"]
    quem = cliente if papel == "cliente" else compliance
    assert api(quem).get("/api/kyc/fila").status_code == 403
    assert api(quem).post(f"/api/kyc/{vid}/decisao", {"aprovar": True}, format="json").status_code == 403
    assert Verificacao.objects.get(pk=vid).status == Status.PENDENTE


def test_equipe_nao_usa_rota_de_cliente(api, operador):
    assert api(operador).post("/api/kyc/minha", dados_envio(), format="multipart").status_code == 403


def test_documento_so_para_dono_e_operador(api, cliente, outro_cliente, operador, compliance):
    vid = enviar(api, cliente).json()["id"]
    dono = api(cliente).get(f"/api/kyc/{vid}/documento")
    assert dono.status_code == 200 and b"".join(dono.streaming_content).startswith(b"%PDF")
    assert api(operador).get(f"/api/kyc/{vid}/documento").status_code == 200
    assert api(outro_cliente).get(f"/api/kyc/{vid}/documento").status_code == 404  # nem confirma que existe
    assert api(compliance).get(f"/api/kyc/{vid}/documento").status_code == 404
    assert api(outro_cliente).get("/api/kyc/minha").status_code == 404  # não vê o pedido da Ana


def test_auditoria_so_compliance_e_registra_a_decisao(api, cliente, operador, compliance):
    vid = enviar(api, cliente).json()["id"]
    api(operador).post(f"/api/kyc/{vid}/decisao", {"aprovar": False, "motivo": "dados divergentes"}, format="json")
    assert api(operador).get("/api/auditoria").status_code == 403
    assert api(cliente).get("/api/auditoria").status_code == 403
    eventos = api(compliance).get("/api/auditoria").json()["results"]
    assert [e["acao"] for e in eventos] == ["kyc_recusado", "kyc_enviado"]
    assert eventos[0]["dados"] == {"antes": "pendente", "depois": "recusada", "motivo": "dados divergentes"}
    assert eventos[0]["ator_email"] == operador.email


def test_auditoria_e_somente_insercao_no_banco(api, cliente):
    enviar(api, cliente)
    evento = EventoAuditoria.objects.get()
    with pytest.raises(DatabaseError, match="somente inserção"), transaction.atomic():
        EventoAuditoria.objects.filter(pk=evento.pk).update(acao="apagado")
    with pytest.raises(DatabaseError, match="somente inserção"), transaction.atomic():
        evento.delete()


@pytest.mark.django_db(transaction=True)
def test_dois_operadores_ao_mesmo_tempo_so_um_decide(criar_usuario, cliente):
    """Corrida real: duas threads, duas conexões, o mesmo pedido. O select_for_update faz a segunda
    esperar a primeira terminar e então ver que o pedido não está mais pendente."""
    op1, op2 = criar_usuario("op1@teste.local", "operador"), criar_usuario("op2@teste.local", "operador")
    v = servicos.enviar(cliente, nome_completo="Ana", cpf=gerar_cpf(), data_nascimento="1990-01-01",
                        documento=documento())
    largada = threading.Barrier(2)
    resultados: list[str] = []

    def decidir(operador, aprovar):
        try:
            largada.wait()
            servicos.decidir(v.pk, operador, aprovar=aprovar, motivo="" if aprovar else "divergente")
            resultados.append("ok")
        except servicos.Conflito:
            resultados.append("conflito")
        finally:
            connection.close()

    threads = [threading.Thread(target=decidir, args=(op1, True)), threading.Thread(target=decidir, args=(op2, False))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(resultados) == ["conflito", "ok"]
    assert EventoAuditoria.objects.filter(verificacao=v).exclude(acao="kyc_enviado").count() == 1

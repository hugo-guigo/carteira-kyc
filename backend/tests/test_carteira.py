import threading
import uuid

import pytest
from django.db import DatabaseError, connection, transaction

from carteira import servicos
from carteira.models import CAIXA_EXTERNO, Conta, Lancamento, Transacao
from kyc import servicos as kyc
from kyc.models import EventoAuditoria
from tests.conftest import documento, gerar_cpf

pytestmark = pytest.mark.django_db


def aprovar(cliente, operador) -> Conta:
    v = kyc.enviar(cliente, nome_completo="Ana Teste", cpf=gerar_cpf(), data_nascimento="1990-01-01",
                   documento=documento())
    kyc.decidir(v.pk, operador, aprovar=True)
    return Conta.objects.get(dono=cliente)


def chave() -> str:
    return uuid.uuid4().hex


def operar(api, usuario, rota: str, valor, chave_idem: str | None = None):
    cabecalhos = {} if chave_idem is None else {"HTTP_IDEMPOTENCY_KEY": chave_idem}
    return api(usuario).post(f"/api/carteira/{rota}", {"valor_centavos": valor}, format="json", **cabecalhos)


@pytest.fixture
def conta(cliente, operador) -> Conta:
    return aprovar(cliente, operador)


def test_conta_nasce_com_a_aprovacao_do_kyc(api, cliente, operador):
    assert api(cliente).get("/api/carteira").status_code == 404
    assert operar(api, cliente, "depositos", 100, chave()).status_code == 404
    aprovar(cliente, operador)
    assert api(cliente).get("/api/carteira").json() == {"saldo_centavos": 0}


def test_saldo_e_a_soma_dos_lancamentos_em_partidas_dobradas(api, cliente, conta):
    assert operar(api, cliente, "depositos", 10_000, chave()).status_code == 201
    r = operar(api, cliente, "saques", 2_500, chave())
    assert r.status_code == 201 and r.json()["saldo_centavos"] == 7_500
    assert api(cliente).get("/api/carteira").json() == {"saldo_centavos": 7_500}
    for t in Transacao.objects.all():  # cada transação fecha em zero
        assert sum(t.lancamentos.values_list("valor_centavos", flat=True)) == 0
    caixa = Conta.objects.get(nome=CAIXA_EXTERNO)
    assert servicos.saldo(caixa) == -7_500
    assert not hasattr(Conta, "saldo")  # não existe campo de saldo para alguém editar


@pytest.mark.parametrize("chave_idem", [None, "curta", "x" * 65])
def test_operacao_sem_chave_valida_e_400(api, cliente, conta, chave_idem):
    r = operar(api, cliente, "depositos", 100, chave_idem)
    assert r.status_code == 400 and "Idempotency-Key" in r.json()["detail"]
    assert not Transacao.objects.exists()


@pytest.mark.parametrize("valor", [0, -500, 1_000_001, "10,50", None])
def test_valor_fora_do_limite_e_400(api, cliente, conta, valor):
    assert operar(api, cliente, "depositos", valor, chave()).status_code == 400
    assert not Transacao.objects.exists()


def test_mesma_chave_devolve_a_transacao_original_sem_gravar_de_novo(api, cliente, conta):
    k = chave()
    primeira = operar(api, cliente, "depositos", 5_000, k)
    repetida = operar(api, cliente, "depositos", 5_000, k)
    assert primeira.status_code == 201 and "Idempotent-Replayed" not in primeira.headers
    assert repetida.status_code == 200 and repetida.headers["Idempotent-Replayed"] == "true"
    assert repetida.json()["id"] == primeira.json()["id"]
    assert Transacao.objects.count() == 1 and servicos.saldo(conta) == 5_000


def test_mesma_chave_com_outro_pedido_e_422(api, cliente, conta):
    k = chave()
    assert operar(api, cliente, "depositos", 5_000, k).status_code == 201
    assert operar(api, cliente, "depositos", 6_000, k).status_code == 422
    assert operar(api, cliente, "saques", 5_000, k).status_code == 422
    assert Transacao.objects.count() == 1


def test_a_chave_e_unica_por_conta_e_nao_entre_clientes(api, cliente, outro_cliente, operador, conta):
    aprovar(outro_cliente, operador)
    k = chave()
    assert operar(api, cliente, "depositos", 100, k).status_code == 201
    assert operar(api, outro_cliente, "depositos", 100, k).status_code == 201


def test_saque_maior_que_o_saldo_e_409_e_nao_grava(api, cliente, conta):
    operar(api, cliente, "depositos", 1_000, chave())
    r = operar(api, cliente, "saques", 1_001, chave())
    assert r.status_code == 409 and r.json()["detail"] == "saldo insuficiente"
    assert Transacao.objects.count() == 1 and servicos.saldo(conta) == 1_000


@pytest.mark.parametrize("papel", ["operador", "compliance"])
def test_equipe_nao_deposita_saca_nem_ve_extrato(api, criar_usuario, papel):
    membro = criar_usuario(f"{papel}2@teste.local", papel)
    assert operar(api, membro, "depositos", 100, chave()).status_code == 403
    assert operar(api, membro, "saques", 100, chave()).status_code == 403
    assert api(membro).get("/api/carteira/extrato").status_code == 403
    assert api().get("/api/carteira").status_code == 401


def test_extrato_so_da_propria_conta_do_mais_novo_e_por_cursor(api, cliente, outro_cliente, operador, conta):
    aprovar(outro_cliente, operador)
    for valor in range(1, 26):
        servicos.depositar(cliente, valor, chave())
    servicos.depositar(outro_cliente, 999, chave())
    pagina = api(cliente).get("/api/carteira/extrato").json()
    assert [x["valor_centavos"] for x in pagina["results"]] == list(range(25, 5, -1))  # 20 por página
    assert pagina["results"][0]["tipo"] == "deposito"
    seguinte = api(cliente).get(pagina["next"]).json()
    assert [x["valor_centavos"] for x in seguinte["results"]] == list(range(5, 0, -1)) and seguinte["next"] is None
    outros = api(outro_cliente).get("/api/carteira/extrato").json()["results"]
    assert [x["valor_centavos"] for x in outros] == [999]  # nada da conta da Ana


def test_deposito_e_saque_entram_na_auditoria_da_compliance(api, cliente, compliance, conta):
    t = servicos.depositar(cliente, 4_200, chave()).transacao
    evento = EventoAuditoria.objects.get(transacao=t)
    assert (evento.acao, evento.ator, evento.verificacao) == ("deposito", cliente, None)
    acoes = [e["acao"] for e in api(compliance).get("/api/auditoria").json()["results"]]
    assert "deposito" in acoes and "kyc_aprovado" in acoes


def test_evento_de_auditoria_precisa_de_exatamente_um_alvo(cliente):
    with pytest.raises(DatabaseError), transaction.atomic():
        EventoAuditoria.objects.create(ator=cliente, acao="solto")


def test_transacao_e_lancamento_sao_somente_insercao(cliente, conta):
    t = servicos.depositar(cliente, 100, chave()).transacao
    with pytest.raises(DatabaseError, match="somente inserção"), transaction.atomic():
        Lancamento.objects.filter(transacao=t).update(valor_centavos=1_000_000)
    # DELETE em SQL direto: o delete() do ORM pararia antes, no PROTECT das chaves estrangeiras, e o
    # teste não chegaria ao trigger do banco.
    with pytest.raises(DatabaseError, match="somente inserção"), transaction.atomic(), connection.cursor() as c:
        c.execute("DELETE FROM carteira_transacao WHERE id = %s", [t.pk])


@pytest.mark.django_db(transaction=True)
def test_transacao_que_nao_fecha_em_zero_e_recusada_no_commit(cliente, operador):
    """O trigger de partidas dobradas é adiado: roda no COMMIT, quando os dois lados já deveriam existir."""
    conta = aprovar(cliente, operador)
    with pytest.raises(DatabaseError, match="não fecha"), transaction.atomic():
        t = Transacao.objects.create(conta=conta, tipo="deposito", valor_centavos=100, chave_idempotencia=chave(),
                                     criado_por=cliente)
        Lancamento.objects.create(transacao=t, conta=conta, valor_centavos=100)  # falta o lado do caixa
    assert not Transacao.objects.exists() and not Lancamento.objects.exists()


def em_paralelo(*funcoes):
    """Roda as funções em threads (uma conexão cada), largando juntas. Devolve os resultados na ordem."""
    largada = threading.Barrier(len(funcoes))
    resultados: list = [None] * len(funcoes)

    def rodar(i, f):
        try:
            largada.wait()
            resultados[i] = f()
        except Exception as erro:  # o teste decide o que é esperado
            resultados[i] = erro
        finally:
            connection.close()

    threads = [threading.Thread(target=rodar, args=(i, f)) for i, f in enumerate(funcoes)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return resultados


@pytest.mark.django_db(transaction=True)
def test_dois_saques_ao_mesmo_tempo_nao_deixam_saldo_negativo(cliente, operador):
    """Saldo 100, dois saques de 80 em paralelo. Sem a trava na conta, os dois leriam saldo 100 e
    passariam, deixando -60."""
    conta = aprovar(cliente, operador)
    servicos.depositar(cliente, 100, chave())
    resultados = em_paralelo(lambda: servicos.sacar(cliente, 80, chave()), lambda: servicos.sacar(cliente, 80, chave()))
    assert sorted(type(r).__name__ for r in resultados) == ["Resultado", "SaldoInsuficiente"]
    assert servicos.saldo(conta) == 20


@pytest.mark.django_db(transaction=True)
def test_mesma_chave_ao_mesmo_tempo_grava_uma_vez(cliente, operador):
    """Duas requisições com a mesma chave em paralelo (um clique duplo, ou um retry do cliente)."""
    conta = aprovar(cliente, operador)
    k = chave()
    resultados = em_paralelo(lambda: servicos.depositar(cliente, 300, k), lambda: servicos.depositar(cliente, 300, k))
    assert all(isinstance(r, servicos.Resultado) for r in resultados), resultados
    assert resultados[0].transacao.pk == resultados[1].transacao.pk
    assert sorted(r.repetida for r in resultados) == [False, True]
    assert Transacao.objects.count() == 1 and servicos.saldo(conta) == 300

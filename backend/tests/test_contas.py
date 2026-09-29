import pytest

from contas.models import Papel, Usuario

pytestmark = pytest.mark.django_db


def test_cadastro_cria_cliente_mesmo_se_pedir_outro_papel(api):
    r = api().post("/api/contas/cadastro", {"email": "Nova@Teste.local", "nome": "Nova", "senha": "uma-senha-boa-7731",
                                            "papel": "operador"}, format="json")
    assert r.status_code == 201
    assert r.json()["papel"] == "cliente" and r.json()["email"] == "nova@teste.local"
    assert Usuario.objects.get(email="nova@teste.local").papel == Papel.CLIENTE


def test_cadastro_rejeita_senha_fraca_e_email_repetido(api, cliente):
    fraca = api().post("/api/contas/cadastro", {"email": "x@teste.local", "nome": "X", "senha": "123"}, format="json")
    assert fraca.status_code == 400
    repetido = api().post("/api/contas/cadastro", {"email": "ANA@teste.local", "nome": "A", "senha": "uma-senha-boa-7731"},
                          format="json")
    assert repetido.status_code == 400 and "email" in repetido.json()


def test_login_devolve_token_e_eu_mostra_o_papel(api, operador):
    r = api(operador).get("/api/contas/eu")
    assert r.status_code == 200 and r.json()["papel"] == "operador"


def test_sem_token_e_401_e_senha_errada_nao_loga(api, cliente):
    assert api().get("/api/contas/eu").status_code == 401
    r = api().post("/api/token", {"email": cliente.email, "password": "errada"}, format="json")
    assert r.status_code == 401

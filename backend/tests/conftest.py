import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from contas.models import Papel, Usuario

SENHA = "senha-de-teste-9281"
PDF = b"%PDF-1.4\n% documento ficticio\n"


def gerar_cpf(base: str = "123456789") -> str:
    """CPF matematicamente válido (fictício) a partir de 9 dígitos."""
    numeros = [int(d) for d in base]
    for posicao in (9, 10):
        soma = sum(n * (posicao + 1 - i) for i, n in enumerate(numeros))
        numeros.append((soma * 10) % 11 % 10)
    return "".join(map(str, numeros))


@pytest.fixture(autouse=True)
def midia_temporaria(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}
    # O hash de senha padrão é lento de propósito (contra força bruta); nos testes só atrasa.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def criar_usuario(db):
    def criar(email: str, papel: str = Papel.CLIENTE) -> Usuario:
        return Usuario.objects.create_user(email, SENHA, nome=email.split("@")[0], papel=papel)
    return criar


@pytest.fixture
def cliente(criar_usuario):
    return criar_usuario("ana@teste.local")


@pytest.fixture
def outro_cliente(criar_usuario):
    return criar_usuario("bruno@teste.local")


@pytest.fixture
def operador(criar_usuario):
    return criar_usuario("op@teste.local", Papel.OPERADOR)


@pytest.fixture
def compliance(criar_usuario):
    return criar_usuario("comp@teste.local", Papel.COMPLIANCE)


@pytest.fixture
def api():
    def logado(usuario: Usuario | None = None) -> APIClient:
        c = APIClient()
        if usuario is not None:
            r = c.post("/api/token", {"email": usuario.email, "password": SENHA}, format="json")
            assert r.status_code == 200, r.content
            c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
        return c
    return logado


def documento(conteudo: bytes = PDF, tipo: str = "application/pdf", nome: str = "rg.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(nome, conteudo, content_type=tipo)


def dados_envio(**troca) -> dict:
    return {"nome_completo": "Ana Teste Ficticia", "cpf": gerar_cpf(), "data_nascimento": "1999-05-10",
            "documento": documento(), **troca}

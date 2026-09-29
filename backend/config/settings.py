"""Configuração do Django. Tudo que muda entre ambientes vem de variável de ambiente (.env local)."""
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")


def env_bool(nome: str, padrao: bool = False) -> bool:
    return os.environ.get(nome, str(padrao)).lower() in ("1", "true", "sim")


def env_lista(nome: str, padrao: str = "") -> list[str]:
    return [x.strip() for x in os.environ.get(nome, padrao).split(",") if x.strip()]


SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = env_bool("DJANGO_DEBUG")
ALLOWED_HOSTS = env_lista("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "contas",
    "kyc",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

_db = urlparse(os.environ["DATABASE_URL"])
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _db.path.lstrip("/"),
        "USER": _db.username,
        "PASSWORD": _db.password,
        "HOST": _db.hostname,
        "PORT": _db.port or 5432,
        "CONN_MAX_AGE": 60,
        # Parâmetros da URL (?sslmode=require&channel_binding=require no Neon) viram opções do driver.
        # prepare_threshold=None: o pooler do Neon (PgBouncer em modo transação) pode entregar cada
        # transação a uma conexão diferente, e comando preparado numa conexão não existe na outra.
        "OPTIONS": {**dict(parse_qsl(_db.query)), "prepare_threshold": None},
        # Cursor do lado do servidor vive além da transação; com pooler em modo transação ele se perde.
        "DISABLE_SERVER_SIDE_CURSORS": True,
    }
}

AUTH_USER_MODEL = "contas.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_ROOT = BASE_DIR / "media"  # documentos fictícios em disco local no desenvolvimento

# Na AWS, os documentos vão para um bucket S3 privado (criptografado, só HTTPS). O Lambda tem
# permissão só no prefixo kyc/; o navegador nunca acessa o bucket, só a API com o token.
BUCKET_DOCUMENTOS = os.environ.get("BUCKET_DOCUMENTOS")
if BUCKET_DOCUMENTOS:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            # file_overwrite=True: o nome já é um UUID (kyc/models.py), não há colisão a evitar. Com False
            # o storage faz HeadObject antes de gravar, e sem s3:ListBucket o S3 responde 403 (não 404)
            # para objeto inexistente; o upload quebrava. Assim o papel do Lambda segue sem ListBucket.
            "OPTIONS": {"bucket_name": BUCKET_DOCUMENTOS, "default_acl": None, "file_overwrite": True},
        },
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # Limite por minuto: a demo é pública. O contador fica na memória de cada instância do Lambda,
    # então é aproximado (cada instância conta separado); serve contra abuso casual, não contra ataque.
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle",
                                 "rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "30/min", "user": "60/min"},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
}

CORS_ALLOWED_ORIGINS = env_lista("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")

# Documento de KYC: tipos e tamanho aceitos
KYC_TIPOS_ACEITOS = {"application/pdf", "image/jpeg", "image/png"}
KYC_TAMANHO_MAXIMO = 2 * 1024 * 1024

"""Cria o .env local com segredos aleatórios. Não sobrescreve um .env existente."""
import secrets
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"

if ENV.exists():
    print(".env já existe; nada foi alterado.")
else:
    senha = secrets.token_urlsafe(24)
    ENV.write_text(
        f"POSTGRES_PASSWORD={senha}\n"
        f"DATABASE_URL=postgresql://carteira:{senha}@127.0.0.1:5434/carteira\n"
        f"DJANGO_SECRET_KEY={secrets.token_urlsafe(50)}\n"
        "DJANGO_DEBUG=true\n"
        f"DEMO_SENHA={secrets.token_urlsafe(12)}\n",
        encoding="utf-8",
    )
    print(f".env criado em {ENV}")

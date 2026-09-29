"""Grava os segredos de produção no SSM Parameter Store (SecureString, grátis no nível padrão).

Uso: python scripts/criar_segredos.py [--caminho /carteira-kyc] [--sobrescrever]

- DATABASE_URL vem de DATABASE_URL_PROD no .env (connection string do Neon, colada pelo Hugo).
- DJANGO_SECRET_KEY e DEMO_SENHA são gerados aqui. A DEMO_SENHA também vai para o .env local
  (DEMO_SENHA_PROD) para você conseguir entrar como operador e compliance na demo.
Nada é impresso nem passado na linha de comando: o valor vai para a AWS CLI por um arquivo
temporário que é apagado em seguida.
"""
import argparse
import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ENV = RAIZ / ".env"
AWS = os.environ.get("AWS_CLI", "aws")


def ler_env() -> dict[str, str]:
    valores = {}
    for linha in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            chave, _, valor = linha.partition("=")
            valores[chave.strip()] = valor.strip()
    return valores


def existe(nome: str) -> bool:
    r = subprocess.run([AWS, "ssm", "get-parameter", "--name", nome, "--query", "Parameter.Name", "--output", "text"],
                       capture_output=True, text=True)
    return r.returncode == 0


def gravar(nome: str, valor: str, sobrescrever: bool) -> str:
    if existe(nome) and not sobrescrever:
        return "já existia (mantido)"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"Name": nome, "Value": valor, "Type": "SecureString", "Overwrite": True, "Tier": "Standard"}, f)
    try:
        subprocess.run([AWS, "ssm", "put-parameter", "--cli-input-json", f"file://{f.name}"],
                       check=True, capture_output=True, text=True)
    finally:
        os.remove(f.name)
    return "gravado"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--caminho", default="/carteira-kyc")
    parser.add_argument("--sobrescrever", action="store_true")
    args = parser.parse_args()

    env = ler_env()
    if not env.get("DATABASE_URL_PROD", "").startswith("postgres"):
        raise SystemExit("DATABASE_URL_PROD ausente no .env")
    demo = env.get("DEMO_SENHA_PROD") or secrets.token_urlsafe(12)
    if "DEMO_SENHA_PROD" not in env:
        texto = ENV.read_text(encoding="utf-8")
        separador = "" if texto.endswith("\n") else "\n"  # sem isso a linha gruda na anterior (aconteceu)
        with ENV.open("a", encoding="utf-8") as f:
            f.write(f"{separador}DEMO_SENHA_PROD={demo}\n")

    segredos = {
        "DATABASE_URL": env["DATABASE_URL_PROD"],
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
        "DEMO_SENHA": demo,
    }
    for chave, valor in segredos.items():
        print(f"{args.caminho}/{chave}: {gravar(f'{args.caminho}/{chave}', valor, args.sobrescrever)}")


if __name__ == "__main__":
    main()

"""Empacota o backend, publica no Lambda, roda as migrações dentro da AWS e testa a API.

Uso: python scripts/deploy_api.py [--stack carteira-kyc] [--popular-demo]
Roda igual no Windows (dev) e no GitHub Actions (Linux). Precisa de credenciais da AWS (aws login ou OIDC).

O pacote é montado para Linux arm64 (a arquitetura do Lambda), não para a máquina que roda o script:
pip baixa só wheels binárias manylinux aarch64 do Python 3.13 (2014 e 2_28; o psycopg 3.3 só publica
2_28, que o Amazon Linux 2023 do Lambda aceita). Por isso dá para montar no Windows.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BACKEND = RAIZ / "backend"
BUILD = RAIZ / "build"
AWS = os.environ.get("AWS_CLI", "aws")
ARQUIVOS = ["lambda_handler.py", "manage.py"]


def pacotes_do_backend() -> list[str]:
    """Toda pasta do backend com __init__.py, menos os testes. Antes a lista era fixa, e o app carteira
    ficou de fora do primeiro deploy dele: o Lambda subiu sem o módulo e a API caiu até a correção."""
    return sorted(p.name for p in BACKEND.iterdir() if (p / "__init__.py").exists() and p.name != "tests")


def aws(*args: str) -> str:
    return subprocess.run([AWS, *args], check=True, capture_output=True, text=True).stdout


def saidas_da_stack(stack: str) -> dict[str, str]:
    dados = json.loads(aws("cloudformation", "describe-stacks", "--stack-name", stack, "--output", "json"))
    return {o["OutputKey"]: o["OutputValue"] for o in dados["Stacks"][0].get("Outputs", [])}


def montar_pacote() -> Path:
    pasta = BUILD / "lambda"
    shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir(parents=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                    "-r", str(BACKEND / "requirements-lambda.txt"), "--target", str(pasta),
                    "--platform", "manylinux2014_aarch64", "--platform", "manylinux_2_28_aarch64",
                    "--python-version", "3.13",
                    "--implementation", "cp", "--only-binary=:all:"], check=True)
    for nome in pacotes_do_backend() + ARQUIVOS:
        origem = BACKEND / nome
        destino = pasta / nome
        if origem.is_dir():
            shutil.copytree(origem, destino, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"))
        else:
            shutil.copy2(origem, destino)
    zip_base = BUILD / "lambda"
    arquivo = Path(shutil.make_archive(str(zip_base), "zip", pasta))
    print(f"pacote: {arquivo.stat().st_size / 1e6:.1f} MB compactado")
    return arquivo


def invocar(funcao: str, comando: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        saida = Path(tmp) / "saida.json"
        meta = json.loads(aws("lambda", "invoke", "--function-name", funcao, "--cli-binary-format",
                              "raw-in-base64-out", "--payload", json.dumps({"comando": comando}), str(saida)))
        resposta = json.loads(saida.read_text(encoding="utf-8"))
    if meta.get("FunctionError") or not resposta.get("ok"):
        raise SystemExit(f"{comando} falhou: {resposta}")
    print(f"{comando}: ok")


def testar(url_api: str) -> None:
    alvo = url_api.rstrip("/") + "/api/saude"
    for tentativa in range(5):
        try:
            with urllib.request.urlopen(alvo, timeout=15) as r:
                corpo = json.loads(r.read())
            if corpo.get("status") == "ok":
                print(f"saúde: ok ({alvo})")
                return
        except OSError as erro:
            print(f"saúde: tentativa {tentativa + 1} falhou ({erro})")
        time.sleep(3)
    raise SystemExit("a API não respondeu ao teste de saúde")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack", default="carteira-kyc")
    parser.add_argument("--popular-demo", action="store_true")
    args = parser.parse_args()

    saidas = saidas_da_stack(args.stack)
    funcao = saidas["FuncaoApi"]
    arquivo = montar_pacote()
    aws("lambda", "update-function-code", "--function-name", funcao, "--zip-file", f"fileb://{arquivo}")
    aws("lambda", "wait", "function-updated", "--function-name", funcao)
    print(f"código publicado em {funcao}")
    invocar(funcao, "migrate")
    if args.popular_demo:
        invocar(funcao, "popular_demo")
    testar(saidas["UrlApi"])


if __name__ == "__main__":
    main()

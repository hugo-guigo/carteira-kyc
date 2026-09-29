"""Teste de fumaça contra a API publicada: cadastro, KYC com upload, decisão, auditoria e documento.

Uso: python scripts/fumaca.py https://<function-url>
Lê DEMO_SENHA_PROD do .env (ou da variável de ambiente) para entrar como operador e compliance.
Cria um cliente novo a cada execução, com dados fictícios.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def senha_demo() -> str:
    if os.environ.get("DEMO_SENHA_PROD"):
        return os.environ["DEMO_SENHA_PROD"]
    for linha in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
        if linha.startswith("DEMO_SENHA_PROD="):
            return linha.split("=", 1)[1].strip()
    raise SystemExit("DEMO_SENHA_PROD não encontrada")


def pedir(base, metodo, caminho, token=None, json_corpo=None, multipart=None):
    cabecalhos = {"Origin": "https://hugo-guigo.github.io"}
    dados = None
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    if json_corpo is not None:
        dados = json.dumps(json_corpo).encode()
        cabecalhos["Content-Type"] = "application/json"
    if multipart is not None:
        fronteira = uuid.uuid4().hex
        partes = []
        for nome, valor in multipart.items():
            if isinstance(valor, tuple):
                arquivo, conteudo, tipo = valor
                partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"; filename="{arquivo}"\r\n'
                              f"Content-Type: {tipo}\r\n\r\n".encode() + conteudo + b"\r\n")
            else:
                partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n{valor}\r\n'.encode())
        dados = b"".join(partes) + f"--{fronteira}--\r\n".encode()
        cabecalhos["Content-Type"] = f"multipart/form-data; boundary={fronteira}"
    req = urllib.request.Request(base + caminho, data=dados, method=metodo, headers=cabecalhos)
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            corpo, status, h = r.read(), r.status, r.headers
    except urllib.error.HTTPError as erro:
        corpo, status, h = erro.read(), erro.code, erro.headers
    ms = 1000 * (time.perf_counter() - inicio)
    return status, corpo, h, ms


def main() -> None:
    base = sys.argv[1].rstrip("/")
    marca = uuid.uuid4().hex[:8]
    email = f"fumaca-{marca}@teste.local"
    checar = []

    s, _, h, ms = pedir(base, "POST", "/api/contas/cadastro", json_corpo={"email": email, "nome": f"Fumaca {marca}",
                                                                          "senha": "senha-ficticia-fumaca-8841"})
    checar.append(("cadastro 201", s == 201, ms))
    checar.append(("CORS libera o GitHub Pages", h.get("Access-Control-Allow-Origin") == "https://hugo-guigo.github.io", 0))
    s, c, _, ms = pedir(base, "POST", "/api/token", json_corpo={"email": email, "password": "senha-ficticia-fumaca-8841"})
    cliente = json.loads(c)["access"]
    checar.append(("login do cliente", s == 200, ms))
    s, c, _, ms = pedir(base, "POST", "/api/kyc/minha", cliente, multipart={
        "nome_completo": f"Fumaca {marca}", "cpf": "529.982.247-25", "data_nascimento": "1990-01-01",
        "documento": ("rg.pdf", b"%PDF-1.4\n% ficticio\n", "application/pdf")})
    vid = json.loads(c).get("id")
    checar.append(("envio do KYC com upload para o S3", s == 201, ms))

    senha = senha_demo()
    _, c, _, _ = pedir(base, "POST", "/api/token", json_corpo={"email": "operador@demo.local", "password": senha})
    operador = json.loads(c)["access"]
    s, c, _, ms = pedir(base, "GET", f"/api/kyc/{vid}/documento", operador)
    checar.append(("operador baixa o documento do S3", s == 200 and c.startswith(b"%PDF"), ms))
    s, c, _, ms = pedir(base, "POST", f"/api/kyc/{vid}/decisao", operador, json_corpo={"aprovar": True})
    checar.append(("operador aprova", s == 200 and json.loads(c)["status"] == "aprovada", ms))
    s, _, _, ms = pedir(base, "POST", f"/api/kyc/{vid}/decisao", operador, json_corpo={"aprovar": True})
    checar.append(("decidir de novo dá 409", s == 409, ms))

    _, c, _, _ = pedir(base, "POST", "/api/token", json_corpo={"email": "compliance@demo.local", "password": senha})
    compliance = json.loads(c)["access"]
    s, c, _, ms = pedir(base, "GET", "/api/auditoria", compliance)
    eventos = [e for e in json.loads(c)["results"] if e["verificacao"] == vid]
    checar.append(("auditoria registra envio e aprovação", s == 200 and len(eventos) == 2, ms))
    s, _, _, _ = pedir(base, "GET", "/api/auditoria", cliente)
    checar.append(("cliente não vê auditoria (403)", s == 403, 0))

    for nome, ok, ms in checar:
        print(f"{'OK  ' if ok else 'FALHOU'} {nome}" + (f" ({ms:.0f} ms)" if ms else ""))
    if not all(ok for _, ok, _ in checar):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

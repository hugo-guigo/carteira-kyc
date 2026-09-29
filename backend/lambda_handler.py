"""Entrada do AWS Lambda.

Na inicialização (uma vez por instância, no cold start), lê os segredos do SSM Parameter Store e os
coloca no ambiente antes de o Django carregar as configurações. Assim a senha do banco e a SECRET_KEY
não ficam em variável de ambiente visível no console do Lambda nem no template.

Duas formas de chamada:
- HTTP (Function URL, via CloudFront): o Mangum traduz o evento para ASGI e entrega ao Django.
- Invocação direta com {"comando": "migrate"} ou {"comando": "popular_demo"}: roda o comando de
  gerenciamento dentro da AWS. Só quem tem permissão IAM de invocar a função consegue; a Function URL
  pública não aceita esse formato.
"""
import os

import boto3

COMANDOS = {"migrate": ["migrate", "--noinput"], "popular_demo": ["popular_demo"]}


def carregar_segredos(prefixo: str) -> None:
    ssm = boto3.client("ssm")
    paginas = ssm.get_paginator("get_parameters_by_path").paginate(Path=prefixo, WithDecryption=True)
    for pagina in paginas:
        for p in pagina["Parameters"]:
            os.environ.setdefault(p["Name"].rsplit("/", 1)[-1], p["Value"])


if os.environ.get("SSM_PREFIXO"):
    carregar_segredos(os.environ["SSM_PREFIXO"])

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application  # noqa: E402  (depois dos segredos)
from django.core.management import call_command  # noqa: E402
from mangum import Mangum  # noqa: E402

app_http = Mangum(get_asgi_application(), lifespan="off")


def handler(evento, contexto):
    comando = evento.get("comando") if isinstance(evento, dict) else None
    if comando is not None:
        if comando not in COMANDOS:
            return {"ok": False, "erro": f"comando desconhecido: {comando}"}
        call_command(*COMANDOS[comando])
        return {"ok": True, "comando": comando}
    return app_http(evento, contexto)

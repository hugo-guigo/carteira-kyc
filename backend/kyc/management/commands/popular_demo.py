"""Cria os usuários da demonstração, com dados fictícios. A senha vem de DEMO_SENHA no .env.

Uso: python manage.py popular_demo
"""
import os

from django.core.management.base import BaseCommand

from contas.models import Papel, Usuario

USUARIOS = [
    ("cliente@demo.local", "Ana Cliente (fictícia)", Papel.CLIENTE),
    ("operador@demo.local", "Otávio Operador (fictício)", Papel.OPERADOR),
    ("compliance@demo.local", "Carla Compliance (fictícia)", Papel.COMPLIANCE),
]


class Command(BaseCommand):
    help = "Cria cliente, operador e compliance de demonstração"

    def handle(self, *args, **opcoes):
        senha = os.environ["DEMO_SENHA"]
        for email, nome, papel in USUARIOS:
            u, criado = Usuario.objects.get_or_create(email=email, defaults={"nome": nome, "papel": papel})
            u.set_password(senha)
            u.save()
            self.stdout.write(f"{'criado' if criado else 'atualizado'}: {email} ({papel})")

"""Migração de dados: quem já tinha o KYC aprovado antes da carteira existir ganha a conta agora.
Daqui em diante a conta nasce junto com a aprovação (kyc.servicos.decidir)."""
from django.db import migrations


def criar_contas(apps, schema_editor):
    Conta = apps.get_model("carteira", "Conta")
    Verificacao = apps.get_model("kyc", "Verificacao")
    aprovados = Verificacao.objects.filter(status="aprovada").values_list("cliente_id", flat=True).distinct()
    for cliente_id in aprovados:
        Conta.objects.get_or_create(dono_id=cliente_id, defaults={"tipo": "cliente"})


class Migration(migrations.Migration):
    dependencies = [("carteira", "0002_regras_no_banco"), ("kyc", "0002_auditoria_somente_insercao")]
    operations = [migrations.RunPython(criar_contas, migrations.RunPython.noop)]

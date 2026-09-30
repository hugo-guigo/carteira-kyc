"""Índice do extrato (medido em docs/explain-extrato.md).

Antes, a consulta do extrato achava as linhas da conta pelo índice simples da chave estrangeira e depois
ordenava o histórico inteiro da conta para devolver 21 linhas. O índice (conta, criado_em desc, id desc)
entrega as linhas já na ordem; o INCLUDE valor_centavos deixa o saldo ser somado só pelo índice.

Ordem das operações: primeiro cria o índice novo, depois apaga o simples da chave estrangeira, que fica
redundante (o novo começa pela conta). Assim a tabela nunca fica sem índice na conta.
CREATE INDEX CONCURRENTLY não trava as escritas enquanto o índice é construído, e por isso não pode rodar
dentro de uma transação (atomic = False).
"""
import django.db.models.deletion
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("carteira", "0003_contas_de_clientes_aprovados"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="lancamento",
            index=models.Index(fields=["conta", "-criado_em", "-id"], include=("valor_centavos",),
                               name="lancamento_extrato"),
        ),
        migrations.AlterField(
            model_name="lancamento",
            name="conta",
            field=models.ForeignKey(db_index=False, on_delete=django.db.models.deletion.PROTECT,
                                    related_name="lancamentos", to="carteira.conta"),
        ),
    ]

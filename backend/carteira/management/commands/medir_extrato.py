"""Mede com EXPLAIN ANALYZE as consultas do extrato e do saldo numa conta com muitos lançamentos.

Uso (só no Postgres local do docker compose):
  python manage.py medir_extrato --popular   # carga sintética: 1 conta com 100 mil lançamentos + 1.000 com 100
  python manage.py medir_extrato             # mede; rode antes e depois da migração 0004 (índice do extrato)

A carga usa generate_series direto no SQL e desliga os triggers só na própria sessão
(session_replication_role = replica); as linhas geradas fecham em zero do mesmo jeito.
"""
import re
import statistics
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from carteira.models import CAIXA_EXTERNO, Conta, Lancamento

PESADA = "carga-pesada@teste.local"
REPETICOES = 7

CARGA = """
SET LOCAL session_replication_role = replica;

INSERT INTO contas_usuario (password, is_superuser, first_name, last_name, is_staff, is_active, date_joined,
                            email, nome, papel)
SELECT '!', false, '', '', false, true, now(), 'carga-' || n || '@teste.local', 'Carga ' || n, 'cliente'
FROM generate_series(1, 1000) n
UNION ALL
SELECT '!', false, '', '', false, true, now(), %(pesada)s, 'Carga pesada', 'cliente';

INSERT INTO carteira_conta (dono_id, tipo, nome, criado_em)
SELECT id, 'cliente', '', now() FROM contas_usuario WHERE email LIKE 'carga-%%@teste.local';

-- 100 mil depósitos na conta pesada e 100 em cada uma das outras 1.000, em datas aleatórias de 2 anos
CREATE TEMP TABLE carga_tx ON COMMIT DROP AS
SELECT gen_random_uuid() AS id, c.id AS conta_id, c.dono_id, g.n,
       (1 + floor(random() * 50000))::bigint AS valor,
       now() - random() * interval '730 days' AS quando
FROM carteira_conta c
JOIN contas_usuario u ON u.id = c.dono_id
CROSS JOIN LATERAL generate_series(1, CASE WHEN u.email = %(pesada)s THEN 100000 ELSE 100 END) g(n)
WHERE u.email LIKE 'carga-%%@teste.local';

INSERT INTO carteira_transacao (id, conta_id, tipo, valor_centavos, chave_idempotencia, criado_por_id, criado_em)
SELECT id, conta_id, 'deposito', valor, 'carga-' || n, dono_id, quando FROM carga_tx;

INSERT INTO carteira_lancamento (transacao_id, conta_id, valor_centavos, criado_em)
SELECT id, conta_id, valor, quando FROM carga_tx
UNION ALL
SELECT id, %(caixa)s, -valor, quando FROM carga_tx;
"""


def tempo_de_execucao(plano: str) -> float:
    return float(re.search(r"Execution Time: ([\d.]+) ms", plano).group(1))


class Command(BaseCommand):
    help = "EXPLAIN ANALYZE do extrato e do saldo numa conta com 100 mil lançamentos"

    def add_arguments(self, parser):
        parser.add_argument("--popular", action="store_true", help="grava a carga sintética antes de medir")

    def handle(self, *args, popular: bool, **opcoes):
        host = connection.settings_dict.get("HOST") or ""
        if host not in ("127.0.0.1", "localhost"):
            raise CommandError(f"só roda no Postgres local (HOST={host!r})")
        if popular:
            self.popular()
        conta = Conta.objects.filter(dono__email=PESADA).first()
        if conta is None:
            raise CommandError("sem carga: rode com --popular primeiro")

        indices = [nome for nome, in connection.cursor().execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'carteira_lancamento' ORDER BY 1").fetchall()]
        total = Lancamento.objects.count()
        da_conta = Lancamento.objects.filter(conta=conta).count()
        self.stdout.write(f"lançamentos: {total} no total, {da_conta} na conta medida")
        self.stdout.write(f"índices em carteira_lancamento: {', '.join(indices)}\n")

        # As mesmas consultas da API: 1ª página do extrato (CursorPagination busca 21 linhas para saber se
        # há próxima), uma página do meio do histórico e o saldo.
        extrato = Lancamento.objects.filter(conta_id=conta.pk).select_related("transacao").order_by("-criado_em", "-id")
        meio = timezone.now() - timedelta(days=365)
        consultas = {
            "extrato, 1ª página": lambda: extrato[:21].explain(analyze=True, buffers=True),
            "extrato, página de 1 ano atrás": lambda: extrato.filter(criado_em__lt=meio)[:21].explain(
                analyze=True, buffers=True),
            "saldo": lambda: self.explicar_sql(
                "SELECT sum(valor_centavos) FROM carteira_lancamento WHERE conta_id = %s", [conta.pk]),
        }
        for nome, rodar in consultas.items():
            planos = [rodar() for _ in range(REPETICOES)]  # a 1ª aquece o cache; a mediana ignora o pior caso
            tempos = [tempo_de_execucao(p) for p in planos]
            self.stdout.write(f"== {nome}: mediana {statistics.median(tempos):.2f} ms "
                              f"(mín {min(tempos):.2f}, máx {max(tempos):.2f}, {REPETICOES} execuções)")
            self.stdout.write(planos[-1] + "\n")

    @staticmethod
    def explicar_sql(sql: str, parametros: list) -> str:
        with connection.cursor() as c:
            c.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql, parametros)
            return "\n".join(linha for linha, in c.fetchall())

    def popular(self):
        if Conta.objects.filter(dono__email=PESADA).exists():
            self.stdout.write("carga já existe; nada foi gravado")
            return
        caixa = Conta.objects.get_or_create(tipo=Conta.Tipo.SISTEMA, nome=CAIXA_EXTERNO)[0]
        with transaction.atomic(), connection.cursor() as c:
            c.execute(CARGA, {"pesada": PESADA, "caixa": caixa.pk})
        with connection.cursor() as c:
            c.execute("VACUUM ANALYZE carteira_lancamento")
            c.execute("VACUUM ANALYZE carteira_transacao")
        self.stdout.write("carga gravada e estatísticas atualizadas (VACUUM ANALYZE)")

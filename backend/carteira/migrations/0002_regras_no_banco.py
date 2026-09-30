"""Regras da carteira que valem no banco, não só no código:

1. Partidas dobradas: os lançamentos de cada transação somam zero. É um CONSTRAINT TRIGGER adiado
   (DEFERRABLE INITIALLY DEFERRED): roda no COMMIT, depois que os dois lançamentos já foram inseridos.
   Se só um entrar (bug, ou alguém inserindo à mão), o COMMIT falha e nada fica gravado.
2. Transações e lançamentos só aceitam INSERT. Corrigir um erro é fazer uma transação nova, como num
   extrato de banco; o histórico não é reescrito.
3. A conta de sistema "caixa externo" é a contrapartida de depósitos e saques.
"""
from django.db import migrations

CRIAR = """
CREATE FUNCTION carteira_partidas_dobradas() RETURNS trigger AS $$
DECLARE
    soma bigint;
BEGIN
    SELECT coalesce(sum(valor_centavos), 0) INTO soma
    FROM carteira_lancamento WHERE transacao_id = NEW.transacao_id;
    IF soma <> 0 THEN
        RAISE EXCEPTION 'transação % não fecha: os lançamentos somam % centavos', NEW.transacao_id, soma
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER carteira_partidas_dobradas
    AFTER INSERT ON carteira_lancamento
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION carteira_partidas_dobradas();

CREATE FUNCTION carteira_somente_insercao() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% é somente inserção (% bloqueado)', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER carteira_transacao_imutavel BEFORE UPDATE OR DELETE ON carteira_transacao
    FOR EACH ROW EXECUTE FUNCTION carteira_somente_insercao();
CREATE TRIGGER carteira_lancamento_imutavel BEFORE UPDATE OR DELETE ON carteira_lancamento
    FOR EACH ROW EXECUTE FUNCTION carteira_somente_insercao();
"""

DESFAZER = """
DROP TRIGGER IF EXISTS carteira_lancamento_imutavel ON carteira_lancamento;
DROP TRIGGER IF EXISTS carteira_transacao_imutavel ON carteira_transacao;
DROP FUNCTION IF EXISTS carteira_somente_insercao();
DROP TRIGGER IF EXISTS carteira_partidas_dobradas ON carteira_lancamento;
DROP FUNCTION IF EXISTS carteira_partidas_dobradas();
"""


def criar_caixa_externo(apps, schema_editor):
    Conta = apps.get_model("carteira", "Conta")
    Conta.objects.get_or_create(tipo="sistema", nome="caixa-externo")


class Migration(migrations.Migration):
    dependencies = [("carteira", "0001_initial")]
    operations = [
        migrations.RunSQL(CRIAR, DESFAZER),
        migrations.RunPython(criar_caixa_externo, migrations.RunPython.noop),
    ]

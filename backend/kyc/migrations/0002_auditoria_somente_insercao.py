"""A trilha de auditoria só aceita INSERT. Um trigger no Postgres recusa UPDATE e DELETE, então nem um
bug na aplicação nem alguém com acesso ao ORM consegue reescrever o histórico."""
from django.db import migrations

CRIAR = """
CREATE FUNCTION kyc_auditoria_imutavel() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'auditoria é somente inserção (% bloqueado)', TG_OP USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER kyc_auditoria_imutavel
    BEFORE UPDATE OR DELETE ON kyc_eventoauditoria
    FOR EACH ROW EXECUTE FUNCTION kyc_auditoria_imutavel();
"""

DESFAZER = """
DROP TRIGGER IF EXISTS kyc_auditoria_imutavel ON kyc_eventoauditoria;
DROP FUNCTION IF EXISTS kyc_auditoria_imutavel();
"""


class Migration(migrations.Migration):
    dependencies = [("kyc", "0001_initial")]
    operations = [migrations.RunSQL(CRIAR, DESFAZER)]

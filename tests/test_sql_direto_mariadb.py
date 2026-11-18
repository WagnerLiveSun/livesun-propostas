from pathlib import Path


def test_sql_direto_mariadb_matches_delivery_schema():
    root = Path(__file__).resolve().parents[1]
    sql = (root / 'deploy/mariadb/ATUALIZAR_PROPOSTAS_ENTREGAS_1_2.sql').read_text(encoding='utf-8')
    assert 'USE u951548013_propostas;' in sql
    for forbidden in ('REGEXP_LIKE', 'SIGNAL SQLSTATE', 'CREATE PROCEDURE', 'DELIMITER',
                      '@ls_', 'DROP TABLE', 'DELETE FROM'):
        assert forbidden not in sql
    for table in ('cadastros_publicos', 'tentativas_confirmacao_email', 'solicitacoes_central'):
        assert f'CREATE TABLE {table}' in sql
    for name in ('documento_normalizado', 'email_normalizado', 'razao_social_pendente',
                 'uq_usuarios_email_normalizado', 'uq_empresas_documento_normalizado'):
        assert name in sql
    assert 'REGEXP_REPLACE' in sql
    assert sql.index("version_num = 'd20261118a'") < sql.index("version_num = 'd20261118b'")
    assert sql.index("version_num = 'd20261118b'") < sql.index("version_num = 'e20261118a'")
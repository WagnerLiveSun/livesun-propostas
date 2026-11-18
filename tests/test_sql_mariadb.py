"""Regressão da exportação MariaDB sem conexão a bancos."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mariadb_export_uses_supported_syntax_and_revision_guards(tmp_path):
    spec = importlib.util.spec_from_file_location('sql_export_test', ROOT / 'scripts/gerar_sql_cadastro_mysql.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_sql = module.migration_sql
    module.ROOT = tmp_path
    module.TARGET = tmp_path / 'mysql'
    module.migration_sql = original_sql
    # Carregar migrations reais, mas gravar somente no diretório temporário.
    def real_migration(filename):
        current = module.ROOT
        module.ROOT = ROOT
        try:
            return original_sql(filename)
        finally:
            module.ROOT = current
    module.migration_sql = real_migration
    module.generate(mariadb=True)
    folder = tmp_path / 'deploy/mariadb/cadastro_entregas_1_2'
    files = sorted(folder.glob('*.sql'))
    assert len(files) == 6
    for path in files:
        sql = path.read_text(encoding='utf-8')
        assert 'REGEXP_LIKE' not in sql
        if path.name[:2] in ('01', '02', '03', '04'):
            assert "VERSION() NOT LIKE '%MariaDB%'" in sql
            assert "@ls_banco_esperado = 'u951548013_propostas'" in sql
            assert '@ls_backup_confirmado = 0' in sql
            assert "SIGNAL SQLSTATE '45000'" in sql
            assert sql.index('revisao incorreta') < sql.index('UPDATE alembic_version')
    uniqueness = (folder / '03_UNICIDADE_d20261118b.sql').read_text(encoding='utf-8')
    assert "email REGEXP '[^ -~]'" in uniqueness
    assert '@ls_unicidade_aprovada = 0' in uniqueness
    assert uniqueness.index('emails duplicados') < uniqueness.index('UPDATE usuarios SET')
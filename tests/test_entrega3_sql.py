"""Confere equivalência dos SQLs de produção com as migrations aditivas."""
import importlib.util
from io import StringIO
from pathlib import Path
import re
from alembic.operations import Operations
from alembic.migration import MigrationContext

ROOT = Path(__file__).resolve().parents[1]


def normalized(value):
    return re.sub(r'\s+', ' ', value).strip()


def test_mariadb_script_matches_migration_and_has_no_database_lock():
    path = ROOT / 'migrations/versions/f20261118a_trial_usage.py'
    spec = importlib.util.spec_from_file_location('trial_migration_test', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    out = StringIO()
    ctx = MigrationContext.configure(dialect_name='mysql', opts={'as_sql': True, 'output_buffer': out})
    with Operations.context(ctx):
        module.upgrade()
    expected = normalized(out.getvalue())
    actual = (ROOT / 'deploy/mariadb/ENTREGA_3_TRIAL.sql').read_text(encoding='utf-8')
    actual = re.sub(r' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci', '', actual)
    assert expected in normalized(actual)
    assert 'USE ' not in actual and 'CREATE PROCEDURE' not in actual and 'SIGNAL ' not in actual
    assert "SET version_num='f20261118a' WHERE version_num='e20261118a'" in actual
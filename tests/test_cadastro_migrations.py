from pathlib import Path
import pytest
from flask_migrate import upgrade
from sqlalchemy import inspect, text
from src.app import create_app
from src.extensions import db
from src.services.central_migration import migrate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def database(tmp_path):
    app = create_app('testing', {'UPLOAD_FOLDER': str(tmp_path / 'uploads'),
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(tmp_path / 'migration.sqlite'),
        'PUBLIC_REGISTRATION_ENABLED': False, 'CENTRAL_ENABLED': False, 'CENTRAL_ALLOW_LOCAL_HTTP': False})
    with app.app_context():
        assert db.engine.dialect.name == 'sqlite'
        upgrade(directory=str(ROOT / 'migrations'), revision='c20261112')
        yield app
        db.session.remove()
        db.engine.dispose()


def apply(revision):
    from alembic import command
    from flask import current_app
    command.upgrade(current_app.extensions['migrate'].migrate.get_config(str(ROOT / 'migrations')), revision)


def test_additive_preserves_data_and_hook_accepts_revision(database, tmp_path):
    with db.engine.begin() as conn:
        conn.execute(text("INSERT INTO empresas(id,nome,ativo) VALUES (1,'PRESERVAR',1)"))
    apply('d20261118a')
    migrate(database, tmp_path / 'snapshots')
    with db.engine.connect() as conn:
        assert conn.execute(text('SELECT nome FROM empresas WHERE id=1')).scalar_one() == 'PRESERVAR'
        assert conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == 'd20261118a'
    assert not inspect(db.engine).get_unique_constraints('empresas')


def test_uniqueness_requires_explicit_approval(database, monkeypatch):
    apply('d20261118a')
    monkeypatch.delenv('REGISTRATION_UNIQUENESS_APPROVED', raising=False)
    with pytest.raises(RuntimeError, match='autorize'):
        apply('d20261118b')
    assert not inspect(db.engine).get_unique_constraints('empresas')


def test_registration_refuses_schema_without_global_constraints(database):
    apply('d20261118a')
    database.config['PUBLIC_REGISTRATION_ENABLED'] = True
    assert database.test_client().get('/cadastro').status_code == 503


def test_read_only_diagnostic_script_with_explicit_temporary_database(database, monkeypatch):
    import importlib.util
    path = ROOT / 'scripts' / 'diagnosticar_cadastro.py'
    spec = importlib.util.spec_from_file_location('diagnosticar_cadastro_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('REGISTRATION_DIAGNOSTIC_DATABASE_URL', str(db.engine.url))
    monkeypatch.setattr('sys.argv', [str(path), '--banco-autorizado', db.engine.url.database])
    assert module.main() == 0


def test_reviewed_migration_normalizes_and_matches_models(database, monkeypatch, tmp_path):
    with db.engine.begin() as conn:
        conn.execute(text("INSERT INTO empresas(id,nome,cnpj_cpf) VALUES (1,'TESTE','529.982.247-25')"))
        conn.execute(text("INSERT INTO usuarios(id,empresa_id,nome,email,usuario,senha_hash) VALUES (1,1,'TESTE',' TEST@EXAMPLE.COM ','teste','hash-teste')"))
    apply('d20261118a')
    monkeypatch.setenv('REGISTRATION_UNIQUENESS_APPROVED', 'true')
    apply('d20261118b')
    apply('e20261118a')
    apply('f20261118a')
    migrate(database, tmp_path / 'snapshots')
    with db.engine.connect() as conn:
        assert conn.execute(text('SELECT email_normalizado FROM usuarios')).scalar_one() == 'test@example.com'
        assert conn.execute(text('SELECT documento_normalizado FROM empresas')).scalar_one() == '52998224725'
    from alembic.migration import MigrationContext
    from alembic.autogenerate import compare_metadata
    with db.engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), db.metadata) == []


@pytest.mark.parametrize('documents', [False, True])
def test_duplicates_refuse_migration_without_changes(database, monkeypatch, documents):
    with db.engine.begin() as conn:
        for i in (1, 2):
            conn.execute(text('INSERT INTO empresas(id,nome,cnpj_cpf) VALUES (:id,:nome,:doc)'),
                         {'id': i, 'nome': 'TESTE', 'doc': ('529.982.247-25' if i == 1 else '52998224725') if documents else None})
            conn.execute(text('INSERT INTO usuarios(id,empresa_id,nome,email,usuario,senha_hash) VALUES (:id,:id,:nome,:email,:usuario,:hash)'),
                         {'id': i, 'nome': 'TESTE', 'email': f'teste{i}@example.com' if documents else (' Teste@example.com ' if i == 1 else 'teste@example.com'),
                          'usuario': f'teste{i}', 'hash': 'hash-teste'})
    apply('d20261118a')
    monkeypatch.setenv('REGISTRATION_UNIQUENESS_APPROVED', 'true')
    with pytest.raises(RuntimeError, match='duplicadas'):
        apply('d20261118b')
    with db.engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM empresas')).scalar_one() == 2
        assert conn.execute(text('SELECT count(*) FROM usuarios WHERE email_normalizado IS NOT NULL')).scalar_one() == 0


def test_ddl_compiles_mysql_and_postgresql():
    from sqlalchemy.dialects import mysql, postgresql
    from sqlalchemy.schema import CreateTable
    for dialect in (mysql.dialect(), postgresql.dialect()):
        for name in ('cadastros_publicos', 'tentativas_confirmacao_email', 'usuarios', 'empresas', 'solicitacoes_central'):
            assert str(CreateTable(db.metadata.tables[name]).compile(dialect=dialect))


def test_delivery_two_preserves_existing_registration_without_activation(database, monkeypatch, tmp_path):
    apply('d20261118a')
    monkeypatch.setenv('REGISTRATION_UNIQUENESS_APPROVED', 'true')
    apply('d20261118b')
    with db.engine.begin() as conn:
        conn.execute(text("INSERT INTO empresas(id,nome,ativo) VALUES (1,'PRESERVAR',0)"))
        conn.execute(text("INSERT INTO usuarios(id,empresa_id,nome,email,usuario,senha_hash,ativo) VALUES (1,1,'TESTE','test@example.com','teste','hash-teste',0)"))
        conn.execute(text("INSERT INTO cadastros_publicos(id,empresa_id,usuario_id,tipo_pessoa,status,termos_versao,privacidade_versao,aceite_em,criado_em) VALUES (1,1,1,'PJ','DADOS_COMPLETOS','v1','v1',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    apply('e20261118a')
    migrate(database, tmp_path / 'snapshots')
    with db.engine.connect() as conn:
        assert conn.execute(text('SELECT ativo,razao_social_pendente FROM empresas')).one() == (0, 0)
        assert conn.execute(text('SELECT ativo FROM usuarios')).scalar_one() == 0
        assert conn.execute(text('SELECT status FROM cadastros_publicos')).scalar_one() == 'DADOS_COMPLETOS'
        assert conn.execute(text('SELECT count(*) FROM solicitacoes_central')).scalar_one() == 0
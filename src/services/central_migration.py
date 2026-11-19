"""Migração aditiva delimitada, executada uma vez pelo master Gunicorn."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateTable

BASE_REVISION = 'b8215bc35a91'
TARGET_REVISION = 'c20261112'
COMPATIBLE_REVISIONS = {TARGET_REVISION, 'd20261118a', 'd20261118b', 'e20261118a', 'f20261118a'}
CENTRAL_TABLES = {'central_tenants', 'central_eventos_recebidos'}


class CentralMigrationError(RuntimeError):
    """Somente mensagens fixas, sem URL/senha/SQL do driver."""


def validate_schema(engine):
    from src.models.central import CentralTenant, CentralEventoRecebido
    schema = inspect(engine)
    for model in (CentralTenant, CentralEventoRecebido):
        columns = {column['name'] for column in schema.get_columns(model.__tablename__)}
        if columns != set(model.__table__.columns.keys()):
            raise CentralMigrationError('Estrutura Central divergente. Não recrie tabelas; revise a migration.')
    if schema.get_pk_constraint('central_tenants')['constrained_columns'] != ['empresa_id']:
        raise CentralMigrationError('Chave de empresa divergente na estrutura Central.')
    constraints = schema.get_unique_constraints('central_tenants')
    if not any(item['column_names'] == ['central_cliente_id'] for item in constraints):
        raise CentralMigrationError('Unicidade do vínculo não confirmada.')
    if schema.get_pk_constraint('central_eventos_recebidos')['constrained_columns'] != ['evento_id']:
        raise CentralMigrationError('Idempotência dos eventos não confirmada.')
    if not any(item['constrained_columns'] == ['empresa_id'] and item['referred_table'] == 'empresas'
               for item in schema.get_foreign_keys('central_tenants')):
        raise CentralMigrationError('Integridade do vínculo com empresas não confirmada.')


def save_schema_snapshot(engine, folder):
    """Somente DDL: não é backup dos registros, logos ou uploads."""
    from sqlalchemy import MetaData
    metadata = MetaData()
    metadata.reflect(bind=engine)
    snapshot = {'kind': 'schema_only', 'revision': BASE_REVISION,
        'ddl': [str(CreateTable(table).compile(dialect=engine.dialect))
                for table in metadata.sorted_tables]}
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = 'propostas-schema-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'
    fd = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(snapshot, stream, ensure_ascii=False)


def migrate(app, snapshot_folder=None):
    from src.extensions import db
    from flask_migrate import upgrade
    root = Path(__file__).resolve().parents[2]
    with app.app_context():
        lock = None
        lock_name = None
        pg_key = None
        acquired = False
        try:
            lock = db.engine.connect()
            dialect = db.engine.dialect.name
            identity = str(db.engine.url.database).encode()
            if dialect == 'mysql':
                lock_name = 'propostas-central-' + hashlib.sha256(identity).hexdigest()[:32]
                if lock.execute(text('SELECT GET_LOCK(:name, 30)'), {'name':lock_name}).scalar_one() != 1:
                    raise CentralMigrationError('Outra migração do Propostas está em execução.')
                acquired = True
            elif dialect == 'postgresql':
                pg_key = int.from_bytes(hashlib.sha256(identity).digest()[:8], 'big', signed=True)
                if not lock.execute(text('SELECT pg_try_advisory_lock(:key)'), {'key':pg_key}).scalar_one():
                    raise CentralMigrationError('Outra migração do Propostas está em execução.')
                acquired = True
            elif dialect != 'sqlite':
                raise CentralMigrationError('Banco não suportado para migração Central.')
            tables = set(inspect(db.engine).get_table_names())
            if 'alembic_version' not in tables or 'empresas' not in tables:
                raise CentralMigrationError('Banco sem histórico Alembic/empresas. Migração automática recusada.')
            revisions = list(lock.execute(text('SELECT version_num FROM alembic_version')).scalars())
            lock.commit()
            if len(revisions) == 1 and revisions[0] in COMPATIBLE_REVISIONS:
                validate_schema(db.engine)
                print(json.dumps({'event':'central_schema_ready', 'revision':revisions[0]}), flush=True)
                return
            if revisions != [BASE_REVISION] or tables & CENTRAL_TABLES:
                raise CentralMigrationError('Revisão inesperada ou migração parcial. Não apague tabelas; revise o histórico.')
            if 'logo_dados' not in {item['name'] for item in inspect(db.engine).get_columns('empresas')}:
                raise CentralMigrationError('Estrutura anterior incompatível com a revisão Alembic.')
            folder = snapshot_folder or Path(app.config['UPLOAD_FOLDER']).parent/'migration-snapshots'
            save_schema_snapshot(db.engine, folder)
            print(json.dumps({'event':'central_migration_started', 'from':BASE_REVISION,
                              'to':TARGET_REVISION, 'snapshot':'schema_only'}), flush=True)
            upgrade(directory=str(root/'migrations'), revision=TARGET_REVISION)
            validate_schema(db.engine)
            print(json.dumps({'event':'central_schema_ready', 'revision':TARGET_REVISION}), flush=True)
        except CentralMigrationError:
            raise
        except Exception:
            raise CentralMigrationError('Falha na migração Central. Confira conexão, permissões DDL e histórico; dados não devem ser apagados.') from None
        finally:
            try:
                if lock is not None:
                    try:
                        if acquired and lock_name is not None:
                            lock.execute(text('SELECT RELEASE_LOCK(:name)'), {'name':lock_name})
                        elif acquired and pg_key is not None:
                            lock.execute(text('SELECT pg_advisory_unlock(:key)'), {'key':pg_key})
                    finally:
                        lock.close()
            finally:
                db.session.remove()
                db.engine.dispose()


def before_server_start(server):
    try:
        from src.app import create_app
        migrate(create_app())
    except CentralMigrationError as error:
        server.log.error('%s', str(error))
        raise SystemExit(1) from None
    except Exception:
        server.log.error('Preparação Central recusada. Confira central_migration_started, revisão Alembic e permissões do banco.')
        raise SystemExit(1) from None
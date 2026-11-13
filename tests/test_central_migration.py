import json
from pathlib import Path
import tempfile
import unittest

from flask_migrate import upgrade
from sqlalchemy import inspect, text
from src.app import create_app
from src.extensions import db
from src.services.central_migration import migrate, CentralMigrationError


ROOT = Path(__file__).resolve().parents[1]


class CentralMigrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app('testing', {'UPLOAD_FOLDER': self.folder.name,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(Path(self.folder.name)/'database.sqlite'),
            'CENTRAL_ENABLED': False, 'CENTRAL_ALLOW_LOCAL_HTTP': False})
        self.context = self.app.app_context()
        self.context.push()
        upgrade(directory=str(ROOT/'migrations'), revision='b8215bc35a91')
        with db.engine.begin() as connection:
            connection.execute(text("INSERT INTO empresas (id,nome,logo_dados) VALUES (1,'PRESERVAR',:logo)"),
                {'logo':b'logo-before-central'})
        self.snapshots = Path(self.folder.name)/'snapshots'

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        self.folder.cleanup()

    def test_upgrade_and_repeat_preserve_existing_company_and_logo(self):
        migrate(self.app, self.snapshots)
        migrate(self.app, self.snapshots)
        with db.engine.connect() as connection:
            self.assertEqual(connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one(), 'c20261112')
            self.assertEqual(connection.execute(text('SELECT nome,logo_dados FROM empresas WHERE id=1')).one(),
                ('PRESERVAR', b'logo-before-central'))
            self.assertEqual(connection.execute(text('SELECT count(*) FROM central_tenants')).scalar_one(), 0)
        files = list(self.snapshots.glob('*.json'))
        self.assertEqual(len(files), 1)
        backup = json.loads(files[0].read_text(encoding='utf-8'))
        self.assertEqual(backup['kind'], 'schema_only')
        self.assertNotIn('PRESERVAR', files[0].read_text(encoding='utf-8'))
        self.assertFalse(self.app.config['CENTRAL_ENABLED'])

    def test_unexpected_revision_does_not_create_tables(self):
        with db.engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num='unknown_revision'"))
        with self.assertRaises(CentralMigrationError):
            migrate(self.app, self.snapshots)
        self.assertNotIn('central_tenants', inspect(db.engine).get_table_names())

    def test_partial_migration_requires_review(self):
        with db.engine.begin() as connection:
            connection.execute(text('CREATE TABLE central_tenants (unexpected INTEGER)'))
        with self.assertRaises(CentralMigrationError):
            migrate(self.app, self.snapshots)
        self.assertNotIn('central_eventos_recebidos', inspect(db.engine).get_table_names())

    def test_head_with_invalid_structure_is_not_silently_accepted(self):
        migrate(self.app, self.snapshots)
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE central_tenants ADD COLUMN unexpected INTEGER'))
        with self.assertRaises(CentralMigrationError):
            migrate(self.app, self.snapshots)
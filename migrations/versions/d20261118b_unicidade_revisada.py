"""Unicidade global: exige revisão autorizada, sem limpar dados automaticamente."""
import os
from alembic import op, context
import sqlalchemy as sa
from src.services.identidades import email_key, document_key

revision = 'd20261118b'
down_revision = 'd20261118a'
branch_labels = None
depends_on = None


def upgrade():
    if context.is_offline_mode():
        raise RuntimeError('Esta migration exige diagnóstico online autorizado; não execute SQL exportado sem revisão.')
    if os.getenv('REGISTRATION_UNIQUENESS_APPROVED') != 'true':
        raise RuntimeError('Execute diagnóstico e autorize REGISTRATION_UNIQUENESS_APPROVED antes desta migration.')
    connection = op.get_bind()
    snapshots = []
    for table, source, destination, normalize in (
            ('usuarios', 'email', 'email_normalizado', email_key),
            ('empresas', 'cnpj_cpf', 'documento_normalizado', document_key)):
        rows = list(connection.execute(sa.text(f'SELECT id, {source} FROM {table}')))
        seen = set()
        for _, value in rows:
            key = normalize(value)
            if table == 'usuarios' and not key:
                raise RuntimeError('Existem e-mails vazios. Revise os dados antes da migration.')
            if key and key in seen:
                raise RuntimeError('Existem identidades duplicadas. Nenhum registro foi corrigido automaticamente.')
            seen.add(key)
        snapshots.append((table, destination, normalize, rows))
    # Aplicar em janela sem escritas; MySQL não reverte todo DDL em caso de falha.
    for table, destination, normalize, rows in snapshots:
        for identifier, value in rows:
            connection.execute(sa.text(f'UPDATE {table} SET {destination}=:value WHERE id=:id'),
                               {'value': normalize(value) or None, 'id': identifier})
    with op.batch_alter_table('usuarios') as batch:
        batch.create_unique_constraint('uq_usuarios_email_normalizado', ['email_normalizado'])
    with op.batch_alter_table('empresas') as batch:
        batch.create_unique_constraint('uq_empresas_documento_normalizado', ['documento_normalizado'])


def downgrade():
    raise RuntimeError('Downgrade destrutivo desabilitado. Preserve identidades e auditoria.')
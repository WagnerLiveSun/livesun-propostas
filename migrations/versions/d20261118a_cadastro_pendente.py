"""Estrutura aditiva de cadastro pendente, sem liberação de acesso."""
from alembic import op
import sqlalchemy as sa

revision = 'd20261118a'
down_revision = 'c20261112'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('empresas', sa.Column('documento_normalizado', sa.String(14)))
    op.add_column('usuarios', sa.Column('email_normalizado', sa.String(120)))
    op.create_table('cadastros_publicos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('empresa_id', sa.Integer(), sa.ForeignKey('empresas.id'), nullable=False, unique=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False, unique=True),
        sa.Column('tipo_pessoa', sa.String(2), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('token_hash', sa.String(64), unique=True),
        sa.Column('expira_em', sa.DateTime()),
        sa.Column('confirmado_em', sa.DateTime()),
        sa.Column('proximo_envio_em', sa.DateTime()),
        sa.Column('termos_versao', sa.String(100), nullable=False),
        sa.Column('privacidade_versao', sa.String(100), nullable=False),
        sa.Column('aceite_em', sa.DateTime(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False))
    op.create_table('tentativas_confirmacao_email',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cadastro_id', sa.Integer(), sa.ForeignKey('cadastros_publicos.id'), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('criada_em', sa.DateTime(), nullable=False),
        sa.Column('concluida_em', sa.DateTime()))
    op.create_index('ix_tentativas_confirmacao_email_cadastro_id', 'tentativas_confirmacao_email', ['cadastro_id'])


def downgrade():
    raise RuntimeError('Downgrade destrutivo desabilitado. Preserve cadastros e auditoria.')
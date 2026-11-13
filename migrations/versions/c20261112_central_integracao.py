"""Cache comercial e idempotência do LiveSun Central, sem alterar RBAC."""
from alembic import op
import sqlalchemy as sa

revision = 'c20261112'
down_revision = 'b8215bc35a91'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('central_tenants',
        sa.Column('empresa_id', sa.Integer(), sa.ForeignKey('empresas.id'), primary_key=True),
        sa.Column('central_cliente_id', sa.Integer(), nullable=False, unique=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('assinatura_id', sa.Integer(), nullable=False),
        sa.Column('versao', sa.Integer(), nullable=False),
        sa.Column('valido_ate', sa.DateTime()),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False))
    op.create_table('central_eventos_recebidos',
        sa.Column('evento_id', sa.String(50), primary_key=True),
        sa.Column('cliente_id', sa.Integer(), nullable=False),
        sa.Column('assinatura_id', sa.Integer(), nullable=False),
        sa.Column('versao', sa.Integer(), nullable=False),
        sa.Column('recebido_em', sa.DateTime(), nullable=False))


def downgrade():
    raise RuntimeError('Downgrade destrutivo desabilitado: preserve cache e histórico de eventos.')
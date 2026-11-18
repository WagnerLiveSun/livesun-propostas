"""Solicitação ao Central e pendência de razão social; sem ativar cadastros antigos."""
from alembic import op
import sqlalchemy as sa

revision = 'e20261118a'
down_revision = 'd20261118b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('empresas', sa.Column('razao_social_pendente', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table('solicitacoes_central',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cadastro_id', sa.Integer(), sa.ForeignKey('cadastros_publicos.id'), nullable=False, unique=True),
        sa.Column('empresa_id', sa.Integer(), sa.ForeignKey('empresas.id'), nullable=False, unique=True),
        sa.Column('evento_id', sa.String(36), nullable=False, unique=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('tentativas', sa.Integer(), nullable=False),
        sa.Column('ultima_tentativa_em', sa.DateTime()),
        sa.Column('proxima_tentativa_em', sa.DateTime()),
        sa.Column('lease_id', sa.String(32)),
        sa.Column('lease_ate', sa.DateTime()),
        sa.Column('erro_categoria', sa.String(40)),
        sa.Column('central_solicitacao_id', sa.Integer()),
        sa.Column('criada_em', sa.DateTime(), nullable=False),
        sa.Column('recebida_em', sa.DateTime()))


def downgrade():
    raise RuntimeError('Downgrade destrutivo desabilitado: preserve solicitações e auditoria.')
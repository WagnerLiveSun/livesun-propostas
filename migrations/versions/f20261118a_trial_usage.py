"""Cache comercial, quota trial e preferência de boas-vindas."""
from alembic import op
import sqlalchemy as sa

revision = 'f20261118a'
down_revision = 'e20261118a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('commercial_usage',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('empresa_id', sa.Integer(), sa.ForeignKey('empresas.id'), nullable=False),
        sa.Column('assinatura_id', sa.Integer(), nullable=False),
        sa.Column('versao', sa.Integer(), nullable=False),
        sa.Column('data_inicio', sa.Date(), nullable=False),
        sa.Column('trial_ate', sa.Date()), sa.Column('data_fim', sa.Date()),
        sa.Column('suspensa_inadimplencia', sa.Boolean(), nullable=False),
        sa.Column('valido_ate', sa.DateTime(), nullable=False),
        sa.Column('criadas', sa.Integer(), nullable=False),
        sa.Column('inicializado', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('empresa_id', 'assinatura_id', name='uq_usage_empresa_assinatura'))
    op.create_table('trial_proposals',
        sa.Column('proposta_id', sa.Integer(), sa.ForeignKey('propostas.id'), primary_key=True),
        sa.Column('empresa_id', sa.Integer(), sa.ForeignKey('empresas.id'), nullable=False),
        sa.Column('usage_id', sa.Integer(), sa.ForeignKey('commercial_usage.id'), primary_key=True))
    op.create_index('ix_trial_proposals_empresa_id', 'trial_proposals', ['empresa_id'])
    op.create_table('welcome_preferences',
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), primary_key=True),
        sa.Column('empresa_id', sa.Integer(), sa.ForeignKey('empresas.id'), nullable=False),
        sa.Column('oculto', sa.Boolean(), nullable=False))


def downgrade():
    raise RuntimeError('Preserve contadores e histórico; rollback de código sem apagar consumo.')
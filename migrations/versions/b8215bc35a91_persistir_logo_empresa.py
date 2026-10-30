"""Persistir logo no banco sem depender do filesystem do servidor."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMBLOB

revision = 'b8215bc35a91'
down_revision = '73bd0d15d1db'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('empresas', sa.Column('logo_dados', sa.LargeBinary().with_variant(MEDIUMBLOB(), 'mysql'), nullable=True))


def downgrade():
    op.drop_column('empresas', 'logo_dados')
"""sahalara aktif/pasif durumu

Rezervasyon geçmişi olan saha silinmek yerine pasife alınır; böylece geçmiş
rezervasyonlar ve raporlar kaybolmaz. Mevcut tüm sahalar aktif başlar.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-10-25 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pitches') as batch_op:
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False,
                                      server_default=sa.true()))


def downgrade():
    with op.batch_alter_table('pitches') as batch_op:
        batch_op.drop_column('is_active')

"""aktif slot UNIQUE kuralı sadece bekleyen/onaylı rezervasyonlara uygulanır

Önceki UNIQUE (pitch_id, date, time_slot) kuralı tüm kayıtları kapsıyordu;
reddedilen bir rezervasyonun saati bir daha kiralanamıyordu. Yerine yalnızca
status IN ('Pending', 'Approved') olan kayıtlar için kısmi UNIQUE index konur.

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-10-25 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None

NAME  = 'uq_reservation_active_slot'
COLS  = ['pitch_id', 'date', 'time_slot']
WHERE = "status IN ('Pending', 'Approved')"


def upgrade():
    with op.batch_alter_table('reservations') as batch_op:
        batch_op.drop_constraint(NAME, type_='unique')
    op.create_index(NAME, 'reservations', COLS, unique=True,
                    postgresql_where=sa.text(WHERE),
                    sqlite_where=sa.text(WHERE))


def downgrade():
    # Not: aynı slot için hem reddedilmiş hem aktif kayıt varsa geri alma başarısız olur.
    op.drop_index(NAME, table_name='reservations')
    with op.batch_alter_table('reservations') as batch_op:
        batch_op.create_unique_constraint(NAME, COLS)

"""kayıt zamanlarını UTC'den Türkiye saatine (UTC+3) taşı

Bu sürüme kadar created_at / attempted_at değerleri UTC olarak yazılıyordu;
artık Türkiye yerel saati yazılıyor (utils/timeutil.py). Mevcut kayıtlar
+3 saat kaydırılır. Türkiye 2016'dan beri sabit UTC+3 (yaz saati yok).

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
Create Date: 2026-10-04 17:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


COLUMNS = [
    ('reservations',   'created_at'),
    ('audit_logs',     'created_at'),
    ('login_attempts', 'attempted_at'),
    ('pitch_images',   'created_at'),
    ('blocked_slots',  'created_at'),
    ('customer_types', 'created_at'),
]


def _shift(hours):
    conn = op.get_bind()
    for table, col in COLUMNS:
        if conn.dialect.name == 'sqlite':
            expr = f"strftime('%Y-%m-%d %H:%M:%f000', {col}, '{hours:+d} hours')"
        else:
            expr = f"{col} + INTERVAL '{hours} hours'"
        conn.execute(sa.text(f'UPDATE {table} SET {col} = {expr} WHERE {col} IS NOT NULL'))


def upgrade():
    _shift(3)


def downgrade():
    _shift(-3)

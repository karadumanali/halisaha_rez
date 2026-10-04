"""müşteri tipleri ve saha × tip fiyatlandırması

- customer_types tablosu (Öğrenci, İdari Personel / Akademisyen varsayılan)
- pitch_pricing tablosu (pitch_id, customer_type_id, price)
- reservations.customer_type_id + reservations.price (rezervasyon anındaki ücret)
- pitches.price kaldırılır; mevcut fiyat her varsayılan tipe kopyalanır

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-10-04 18:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c8d9e0f1a2'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


DEFAULT_TYPES = ['Öğrenci', 'İdari Personel / Akademisyen']


def upgrade():
    op.create_table('customer_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_customer_types')),
        sa.UniqueConstraint('name', name=op.f('uq_customer_types_name'))
    )
    op.create_table('pitch_pricing',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pitch_id', sa.Integer(), nullable=False),
        sa.Column('customer_type_id', sa.Integer(), nullable=False),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['customer_type_id'], ['customer_types.id'],
                                name=op.f('fk_pitch_pricing_customer_type_id_customer_types')),
        sa.ForeignKeyConstraint(['pitch_id'], ['pitches.id'],
                                name=op.f('fk_pitch_pricing_pitch_id_pitches')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_pitch_pricing')),
        sa.UniqueConstraint('pitch_id', 'customer_type_id', name='uq_pitch_pricing')
    )

    with op.batch_alter_table('reservations') as batch_op:
        batch_op.add_column(sa.Column('customer_type_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('price', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            op.f('fk_reservations_customer_type_id_customer_types'),
            'customer_types', ['customer_type_id'], ['id'])

    # ── Veri taşıma ──────────────────────────────────────────────
    conn = op.get_bind()
    for name in DEFAULT_TYPES:
        conn.execute(sa.text('INSERT INTO customer_types (name) VALUES (:name)'), {'name': name})

    # Mevcut saha fiyatı → her varsayılan tip için başlangıç fiyatı
    conn.execute(sa.text(
        'INSERT INTO pitch_pricing (pitch_id, customer_type_id, price) '
        'SELECT p.id, ct.id, p.price FROM pitches p CROSS JOIN customer_types ct'
    ))
    # Eski rezervasyonlara o anki saha fiyatını yaz (tip bilinmiyor → NULL kalır)
    conn.execute(sa.text(
        'UPDATE reservations SET price = '
        '(SELECT p.price FROM pitches p WHERE p.id = reservations.pitch_id)'
    ))

    with op.batch_alter_table('pitches') as batch_op:
        batch_op.drop_column('price')


def downgrade():
    with op.batch_alter_table('pitches') as batch_op:
        batch_op.add_column(sa.Column('price', sa.Integer(), nullable=False, server_default='0'))

    conn = op.get_bind()
    conn.execute(sa.text(
        'UPDATE pitches SET price = COALESCE('
        '(SELECT MAX(pp.price) FROM pitch_pricing pp WHERE pp.pitch_id = pitches.id), 0)'
    ))

    with op.batch_alter_table('reservations') as batch_op:
        batch_op.drop_constraint(op.f('fk_reservations_customer_type_id_customer_types'),
                                 type_='foreignkey')
        batch_op.drop_column('price')
        batch_op.drop_column('customer_type_id')

    op.drop_table('pitch_pricing')
    op.drop_table('customer_types')

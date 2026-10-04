"""add pitch_time_slots table

Revision ID: a1b2c3d4e5f6
Revises: 62e16ed372a5
Create Date: 2026-10-04 15:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '62e16ed372a5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('pitch_time_slots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pitch_id', sa.Integer(), nullable=False),
        sa.Column('start_hour', sa.Integer(), nullable=False),
        sa.Column('end_hour', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['pitch_id'], ['pitches.id'], name=op.f('fk_pitch_time_slots_pitch_id_pitches')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_pitch_time_slots')),
        sa.UniqueConstraint('pitch_id', 'start_hour', name='uq_pitch_time_slot')
    )


def downgrade():
    op.drop_table('pitch_time_slots')

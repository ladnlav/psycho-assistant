"""Анамнез, источник и дата диагноза, лабораторные исследования

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-27 08:52:15
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('anamneses',
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('complaints', sa.Text(), nullable=True),
    sa.Column('history', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['patient_id'], ['patient_profiles.user_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('patient_id')
    )
    op.create_table('lab_results',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('patient_id', sa.Uuid(), nullable=False),
    sa.Column('analyte', sa.String(length=30), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('unit', sa.String(length=30), nullable=True),
    sa.Column('taken_on', sa.Date(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('source_note', sa.Text(), nullable=True),
    sa.Column('entered_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['entered_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['patient_id'], ['patient_profiles.user_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lab_results_created_at'), 'lab_results', ['created_at'], unique=False)
    op.create_index(op.f('ix_lab_results_patient_id'), 'lab_results', ['patient_id'], unique=False)
    op.add_column('diagnoses', sa.Column('source', sa.String(length=20), nullable=True))
    op.add_column('diagnoses', sa.Column('source_note', sa.Text(), nullable=True))
    op.add_column('diagnoses', sa.Column('diagnosed_on', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('diagnoses', 'diagnosed_on')
    op.drop_column('diagnoses', 'source_note')
    op.drop_column('diagnoses', 'source')
    op.drop_index(op.f('ix_lab_results_patient_id'), table_name='lab_results')
    op.drop_index(op.f('ix_lab_results_created_at'), table_name='lab_results')
    op.drop_table('lab_results')
    op.drop_table('anamneses')

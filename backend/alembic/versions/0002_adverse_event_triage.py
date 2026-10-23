"""Разметка триажа у описаний нежелательных явлений (результат ml/triage)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23 21:07:06.808790
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('adverse_events', sa.Column('triage', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))


def downgrade() -> None:
    op.drop_column('adverse_events', 'triage')

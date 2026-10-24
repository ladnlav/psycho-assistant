"""Вид сообщения: chat — обычное, help — просьба пациента о срочной помощи с причиной

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24 22:30:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('messages', sa.Column('kind', sa.String(length=20), server_default='chat', nullable=False))


def downgrade() -> None:
    op.drop_column('messages', 'kind')

"""add module_requests indexes

Revision ID: 8271adeb5f08
Revises: da688772331e
Create Date: 2026-05-10 02:52:07.641937

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8271adeb5f08'
down_revision: Union[str, None] = 'da688772331e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_module_requests_key_fulfilled",
        "module_requests",
        ["module_key", "fulfilled"],
    )


def downgrade() -> None:
    op.drop_index("ix_module_requests_key_fulfilled", table_name="module_requests")

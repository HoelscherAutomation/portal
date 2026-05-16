"""add ask_docs_migration_state

Revision ID: 72aa95c0b171
Revises: 855b799ab614
Create Date: 2026-05-15 01:48:33.237894

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '72aa95c0b171'
down_revision: Union[str, None] = '855b799ab614'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('ask_docs_migration_state',
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('name')
    )


def downgrade() -> None:
    op.drop_table('ask_docs_migration_state')

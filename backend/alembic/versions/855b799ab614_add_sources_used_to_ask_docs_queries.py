"""add sources_used to ask_docs_queries

Revision ID: 855b799ab614
Revises: 33b5d7116fec
Create Date: 2026-05-10 18:48:45.446193

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '855b799ab614'
down_revision: Union[str, None] = '33b5d7116fec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ask_docs_queries', sa.Column('sources_used', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))


def downgrade() -> None:
    op.drop_column('ask_docs_queries', 'sources_used')

"""create ask_docs_documents

Revision ID: 02949884443e
Revises: 8271adeb5f08
Create Date: 2026-05-10 13:34:11.772047

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '02949884443e'
down_revision: Union[str, None] = '8271adeb5f08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ask_docs_documents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column(
            'status',
            sa.Enum('pending', 'indexing', 'indexed', 'failed', name='ask_docs_status'),
            nullable=False,
        ),
        sa.Column('chunk_count', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('storage_path', sa.String(length=512), nullable=False),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_ask_docs_documents_status'),
        'ask_docs_documents',
        ['status'],
        unique=False,
    )
    op.create_index(
        op.f('ix_ask_docs_documents_uploaded_by'),
        'ask_docs_documents',
        ['uploaded_by'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_ask_docs_documents_uploaded_by'), table_name='ask_docs_documents')
    op.drop_index(op.f('ix_ask_docs_documents_status'), table_name='ask_docs_documents')
    op.drop_table('ask_docs_documents')
    sa.Enum(name='ask_docs_status').drop(op.get_bind(), checkfirst=False)

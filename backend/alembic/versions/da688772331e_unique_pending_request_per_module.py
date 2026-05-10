"""unique pending request per module

Revision ID: da688772331e
Revises: a83438d92e50
Create Date: 2026-05-10 02:49:18.698478

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da688772331e'
down_revision: Union[str, None] = 'a83438d92e50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX uq_module_requests_pending_per_module "
        "ON module_requests (module_key) WHERE NOT fulfilled"
    )


def downgrade() -> None:
    op.execute("DROP INDEX uq_module_requests_pending_per_module")

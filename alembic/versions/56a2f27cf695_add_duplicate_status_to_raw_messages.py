"""add_duplicate_status_to_raw_messages

Revision ID: 56a2f27cf695
Revises: a7e8099bdbfc
Create Date: 2026-03-22 00:04:36.083086

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56a2f27cf695'
down_revision: Union[str, Sequence[str], None] = 'a7e8099bdbfc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'duplicate' to raw_messages status CHECK constraint."""
    with op.batch_alter_table("raw_messages") as batch_op:
        batch_op.drop_constraint("ck_message_status", type_="check")
        batch_op.create_check_constraint(
            "ck_message_status",
            "status IN ('pending', 'parsed', 'approved', 'rejected', 'failed', 'duplicate')",
        )


def downgrade() -> None:
    """Remove 'duplicate' from raw_messages status CHECK constraint."""
    with op.batch_alter_table("raw_messages") as batch_op:
        batch_op.drop_constraint("ck_message_status", type_="check")
        batch_op.create_check_constraint(
            "ck_message_status",
            "status IN ('pending', 'parsed', 'approved', 'rejected', 'failed')",
        )

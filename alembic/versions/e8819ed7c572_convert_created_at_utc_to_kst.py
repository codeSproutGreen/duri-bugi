"""convert_created_at_utc_to_kst

Revision ID: e8819ed7c572
Revises: 56a2f27cf695
Create Date: 2026-03-22 00:48:23.455123

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8819ed7c572'
down_revision: Union[str, Sequence[str], None] = '56a2f27cf695'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add +9 hours to all created_at timestamps (UTC -> KST).

    SQLite datetime() adds hours and returns ISO format.
    Only converts rows that look like ISO datetime with 'T' separator.
    """
    for table in ("journal_entries", "raw_messages"):
        op.execute(sa.text(
            f"UPDATE {table} SET created_at = datetime(created_at, '+9 hours') "
            f"WHERE created_at LIKE '%T%'"
        ))


def downgrade() -> None:
    """Subtract 9 hours (KST -> UTC)."""
    for table in ("journal_entries", "raw_messages"):
        op.execute(sa.text(
            f"UPDATE {table} SET created_at = datetime(created_at, '-9 hours') "
            f"WHERE created_at LIKE '%T%'"
        ))

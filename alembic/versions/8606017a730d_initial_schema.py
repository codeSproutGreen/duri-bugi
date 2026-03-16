"""initial schema

Revision ID: 8606017a730d
Revises:
Create Date: 2026-03-16 14:35:36.866382

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8606017a730d'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables from scratch."""
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('parent_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=True),
        sa.Column('is_group', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_deleted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        sa.CheckConstraint("type IN ('asset', 'liability', 'equity', 'income', 'expense')", name='ck_account_type'),
    )

    op.create_table(
        'raw_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source_type', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('source_name', sa.Text(), nullable=False),
        sa.Column('device_name', sa.Text(), nullable=False, server_default=''),
        sa.Column('title', sa.Text(), nullable=False, server_default=''),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.Integer(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('ai_result', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("status IN ('pending', 'parsed', 'approved', 'rejected', 'failed')", name='ck_message_status'),
    )
    op.create_index('idx_raw_messages_status', 'raw_messages', ['status'])
    op.create_index('idx_raw_messages_timestamp', 'raw_messages', ['timestamp'])

    op.create_table(
        'journal_entries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('entry_date', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('memo', sa.Text(), nullable=False, server_default=''),
        sa.Column('raw_message_id', sa.Integer(), sa.ForeignKey('raw_messages.id'), nullable=True),
        sa.Column('source', sa.Text(), nullable=False, server_default='web'),
        sa.Column('created_by', sa.Text(), nullable=False, server_default=''),
        sa.Column('is_confirmed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_journal_entries_date', 'journal_entries', ['entry_date'])
    op.create_index('idx_journal_entries_confirmed', 'journal_entries', ['is_confirmed'])

    op.create_table(
        'journal_lines',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('entry_id', sa.Integer(), sa.ForeignKey('journal_entries.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('debit', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('credit', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('debit >= 0 AND credit >= 0', name='ck_line_positive'),
        sa.CheckConstraint('NOT (debit > 0 AND credit > 0)', name='ck_line_one_side'),
    )
    op.create_index('idx_journal_lines_entry', 'journal_lines', ['entry_id'])
    op.create_index('idx_journal_lines_account', 'journal_lines', ['account_id'])

    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('table_name', sa.Text(), nullable=False),
        sa.Column('record_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('old_data', sa.Text(), nullable=True),
        sa.Column('new_data', sa.Text(), nullable=True),
        sa.Column('user', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("action IN ('create', 'update', 'delete')", name='ck_audit_action'),
    )
    op.create_index('idx_audit_log_table_record', 'audit_log', ['table_name', 'record_id'])

    op.create_table(
        'category_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('merchant_pattern', sa.Text(), nullable=False),
        sa.Column('debit_account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=True),
        sa.Column('credit_account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=True),
        sa.Column('hit_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_category_rules_merchant', 'category_rules', ['merchant_pattern'])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table('category_rules')
    op.drop_table('audit_log')
    op.drop_table('journal_lines')
    op.drop_table('journal_entries')
    op.drop_table('raw_messages')
    op.drop_table('accounts')

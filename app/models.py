from datetime import datetime

from sqlalchemy import (
    Column, Integer, Text, ForeignKey, CheckConstraint, Index, event
)
from sqlalchemy.orm import relationship

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False)
    type = Column(Text, nullable=False)  # asset, liability, equity, income, expense
    parent_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    is_group = Column(Integer, nullable=False, default=0)
    is_active = Column(Integer, nullable=False, default=1)
    is_deleted = Column(Integer, nullable=False, default=0)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(Text, nullable=False, default=lambda: datetime.now().isoformat())

    __table_args__ = (
        CheckConstraint(
            "type IN ('asset', 'liability', 'equity', 'income', 'expense')",
            name="ck_account_type",
        ),
    )


class RawMessage(Base):
    __tablename__ = "raw_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(Text, nullable=False)  # SMS / NOTIFICATION
    source = Column(Text, nullable=False)
    source_name = Column(Text, nullable=False)
    title = Column(Text, nullable=False, default="")
    content = Column(Text, nullable=False)
    timestamp = Column(Integer, nullable=False)  # epoch millis
    status = Column(Text, nullable=False, default="pending")
    ai_result = Column(Text, nullable=True)
    created_at = Column(Text, nullable=False, default=lambda: datetime.now().isoformat())

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'parsed', 'approved', 'rejected', 'failed')",
            name="ck_message_status",
        ),
        Index("idx_raw_messages_status", "status"),
        Index("idx_raw_messages_timestamp", "timestamp"),
    )


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_date = Column(Text, nullable=False)  # YYYY-MM-DD
    description = Column(Text, nullable=False)
    memo = Column(Text, nullable=False, default="")
    raw_message_id = Column(Integer, ForeignKey("raw_messages.id"), nullable=True)
    source = Column(Text, nullable=False, default="web")  # web, webhook, api
    created_by = Column(Text, nullable=False, default="")  # user name from PIN login
    is_confirmed = Column(Integer, nullable=False, default=0)
    created_at = Column(Text, nullable=False, default=lambda: datetime.now().isoformat())
    updated_at = Column(Text, nullable=False, default=lambda: datetime.now().isoformat())

    lines = relationship("JournalLine", back_populates="entry", cascade="all, delete-orphan")
    raw_message = relationship("RawMessage", lazy="joined")

    __table_args__ = (
        Index("idx_journal_entries_date", "entry_date"),
        Index("idx_journal_entries_confirmed", "is_confirmed"),
    )


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(Integer, ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    debit = Column(Integer, nullable=False, default=0)
    credit = Column(Integer, nullable=False, default=0)

    entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account", lazy="joined")

    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0", name="ck_line_positive"),
        CheckConstraint("NOT (debit > 0 AND credit > 0)", name="ck_line_one_side"),
        Index("idx_journal_lines_entry", "entry_id"),
        Index("idx_journal_lines_account", "account_id"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_name = Column(Text, nullable=False)
    record_id = Column(Integer, nullable=False)
    action = Column(Text, nullable=False)  # create, update, delete
    old_data = Column(Text, nullable=True)  # JSON
    new_data = Column(Text, nullable=True)  # JSON
    user = Column(Text, nullable=False, default="")
    created_at = Column(Text, nullable=False, default=lambda: datetime.now().isoformat())

    __table_args__ = (
        CheckConstraint("action IN ('create', 'update', 'delete')", name="ck_audit_action"),
        Index("idx_audit_log_table_record", "table_name", "record_id"),
    )


class CategoryRule(Base):
    __tablename__ = "category_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_pattern = Column(Text, nullable=False)
    debit_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    credit_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    hit_count = Column(Integer, nullable=False, default=1)
    updated_at = Column(Text, nullable=False, default=lambda: datetime.now().isoformat())

    debit_account = relationship("Account", foreign_keys=[debit_account_id], lazy="joined")
    credit_account = relationship("Account", foreign_keys=[credit_account_id], lazy="joined")

    __table_args__ = (
        Index("idx_category_rules_merchant", "merchant_pattern"),
    )

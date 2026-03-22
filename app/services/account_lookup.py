"""Account lookup helpers — finding accounts by code, name, type."""

import logging

from sqlalchemy.orm import Session

from app.models import Account, JournalEntry, JournalLine

log = logging.getLogger(__name__)

# Account type → default account code prefix mapping
TYPE_DEFAULTS = {
    "expense": "5006",     # 기타비용
    "asset": "1004",       # 현금
    "liability": "2001",   # KB국민카드
    "income": "4003",      # 기타수입
}


def find_account_by_code(db: Session, code: str | None) -> Account | None:
    """Find an active, non-group account by code."""
    if not code:
        return None
    return db.query(Account).filter(
        Account.code == code, Account.is_active == 1,
        Account.is_group == 0, Account.is_deleted == 0
    ).first()


def find_account_by_name(db: Session, name: str, parent_id: int | None = None) -> Account | None:
    """Find an active, non-group account by name, optionally under a specific parent."""
    q = db.query(Account).filter(
        Account.name == name, Account.is_active == 1,
        Account.is_group == 0, Account.is_deleted == 0,
    )
    if parent_id is not None:
        q = q.filter(Account.parent_id == parent_id)
    return q.first()


def find_account_by_type(db: Session, acct_type: str) -> Account | None:
    """Find the first active account of the given type, preferring default codes."""
    default_code = TYPE_DEFAULTS.get(acct_type)
    if default_code:
        acct = db.query(Account).filter(
            Account.code == default_code, Account.is_active == 1,
            Account.is_group == 0, Account.is_deleted == 0
        ).first()
        if acct:
            return acct
    return db.query(Account).filter(
        Account.type == acct_type, Account.is_active == 1,
        Account.is_group == 0, Account.is_deleted == 0
    ).first()


def build_accounts_context(db: Session) -> str:
    """Build a text list of available accounts for AI context, including group info."""
    accounts = db.query(Account).filter(
        Account.is_active == 1, Account.is_deleted == 0
    ).order_by(Account.type, Account.code).all()

    acct_map = {a.id: a for a in accounts}
    type_label = {"asset": "자산", "liability": "부채", "equity": "자본",
                  "income": "수입", "expense": "비용"}

    lines = []
    for a in accounts:
        if a.is_group:
            continue
        label = type_label.get(a.type, a.type)
        group_name = ""
        if a.parent_id and a.parent_id in acct_map:
            parent = acct_map[a.parent_id]
            while parent.parent_id and parent.parent_id in acct_map:
                parent = acct_map[parent.parent_id]
            group_name = f" [그룹:{parent.name}]"
        lines.append(f"{a.code} {a.name} ({label}){group_name}")
    return "\n".join(lines)


def build_history_context(db: Session, limit: int = 30) -> str:
    """Build recent confirmed transaction history for AI context."""
    recent = db.query(JournalEntry).filter(
        JournalEntry.is_confirmed == 1,
        JournalEntry.source.in_(["webhook", "web"]),
    ).order_by(JournalEntry.id.desc()).limit(limit).all()

    lines = []
    for entry in recent:
        debit_line = next((l for l in entry.lines if l.debit > 0), None)
        credit_line = next((l for l in entry.lines if l.credit > 0), None)
        if debit_line and credit_line:
            lines.append(
                f"{entry.description} → "
                f"debit:{debit_line.account.code}({debit_line.account.name}) "
                f"credit:{credit_line.account.code}({credit_line.account.name})"
            )
    return "\n".join(lines)

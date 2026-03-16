import json
import logging
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Account, RawMessage, JournalEntry, JournalLine, CategoryRule
)
from app.services.ai_parser import parse_message

log = logging.getLogger(__name__)

# Account type → default account code prefix mapping
TYPE_DEFAULTS = {
    "expense": "5006",     # 기타비용
    "asset": "1004",       # 현금
    "liability": "2001",   # KB국민카드
    "income": "4003",      # 기타수입
}


def _find_account_by_code(db: Session, code: str | None) -> Account | None:
    """Find an active, non-group account by code."""
    if not code:
        return None
    return db.query(Account).filter(
        Account.code == code, Account.is_active == 1,
        Account.is_group == 0, Account.is_deleted == 0
    ).first()


def _build_accounts_context(db: Session) -> str:
    """Build a text list of available accounts for AI context."""
    accounts = db.query(Account).filter(
        Account.is_active == 1, Account.is_group == 0, Account.is_deleted == 0
    ).order_by(Account.type, Account.code).all()

    lines = []
    for a in accounts:
        type_label = {"asset": "자산", "liability": "부채", "equity": "자본",
                      "income": "수입", "expense": "비용"}.get(a.type, a.type)
        lines.append(f"{a.code} {a.name} ({type_label})")
    return "\n".join(lines)


def _build_history_context(db: Session, limit: int = 30) -> str:
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


def check_category_rules(db: Session, content: str) -> CategoryRule | None:
    """Check if any category rule matches the message content."""
    rules = db.query(CategoryRule).all()
    for rule in rules:
        if rule.merchant_pattern and rule.merchant_pattern.lower() in content.lower():
            return rule
    return None


def process_message(db: Session, msg: RawMessage) -> JournalEntry | None:
    """Process a raw message: check rules, then AI parse, create journal entry."""

    # 1. Check category rules first (free, no API call)
    rule = check_category_rules(db, msg.content)
    if rule and rule.debit_account_id and rule.credit_account_id:
        log.info("Rule matched: %s", rule.merchant_pattern)
        rule.hit_count += 1
        rule.updated_at = datetime.now().isoformat()

        # Extract amount with simple regex
        import re
        amount_match = re.search(r"(\d{1,3}(?:,\d{3})*)\s*원", msg.content)
        amount = int(amount_match.group(1).replace(",", "")) if amount_match else 0

        if amount <= 0:
            msg.status = "failed"
            msg.ai_result = json.dumps({"error": "rule matched but amount=0"}, ensure_ascii=False)
            db.commit()
            return None

        entry = JournalEntry(
            entry_date=datetime.fromtimestamp(msg.timestamp / 1000).strftime("%Y-%m-%d"),
            description=f"{rule.merchant_pattern} ({msg.source_name})",
            raw_message_id=msg.id,
            source="webhook",
            is_confirmed=0,
        )
        db.add(entry)
        db.flush()

        db.add(JournalLine(entry_id=entry.id, account_id=rule.debit_account_id, debit=amount, credit=0))
        db.add(JournalLine(entry_id=entry.id, account_id=rule.credit_account_id, debit=0, credit=amount))

        msg.status = "parsed"
        msg.ai_result = json.dumps({"source": "rule", "rule_id": rule.id, "amount": amount}, ensure_ascii=False)
        db.commit()
        return entry

    # 2. Build context for AI
    accounts_context = _build_accounts_context(db)
    history_context = _build_history_context(db)

    # 3. Call AI parser with context
    parsed = parse_message(msg.source_name, msg.content,
                           accounts_context=accounts_context,
                           history_context=history_context,
                           device_name=getattr(msg, 'device_name', '') or '')
    if not parsed:
        msg.status = "failed"
        msg.ai_result = json.dumps({"error": "AI parse returned None"}, ensure_ascii=False)
        db.commit()
        return None

    msg.ai_result = json.dumps(parsed, ensure_ascii=False)

    amount = parsed.get("amount", 0)
    if not amount or amount <= 0:
        msg.status = "failed"
        db.commit()
        return None

    tx_type = parsed.get("transaction_type", "unknown")
    if tx_type == "unknown":
        msg.status = "failed"
        db.commit()
        return None

    # Find accounts by code (AI now suggests specific codes)
    debit_acct = _find_account_by_code(db, parsed.get("suggested_debit_code"))
    credit_acct = _find_account_by_code(db, parsed.get("suggested_credit_code"))

    # Fallback to type-based matching
    if not debit_acct:
        debit_acct = find_account_by_type(db, parsed.get("suggested_debit_type", "expense"))
    if not credit_acct:
        credit_acct = find_account_by_type(db, parsed.get("suggested_credit_type", "liability"))

    if not debit_acct or not credit_acct:
        msg.status = "failed"
        msg.ai_result = json.dumps({**parsed, "error": "no matching accounts"}, ensure_ascii=False)
        db.commit()
        return None

    # Determine entry date
    entry_date = parsed.get("date")
    if not entry_date:
        entry_date = datetime.fromtimestamp(msg.timestamp / 1000).strftime("%Y-%m-%d")

    merchant = parsed.get("merchant", "")
    description = merchant if merchant else msg.source_name

    entry = JournalEntry(
        entry_date=entry_date,
        description=description,
        memo=parsed.get("memo", ""),
        raw_message_id=msg.id,
        source="webhook",
        is_confirmed=0,
    )
    db.add(entry)
    db.flush()

    db.add(JournalLine(entry_id=entry.id, account_id=debit_acct.id, debit=amount, credit=0))
    db.add(JournalLine(entry_id=entry.id, account_id=credit_acct.id, debit=0, credit=amount))

    msg.status = "parsed"
    db.commit()
    return entry


def get_account_balance(db: Session, account_id: int) -> int:
    """Calculate account balance. Assets/expenses: debit-credit. Others: credit-debit."""
    acct = db.query(Account).get(account_id)
    if not acct:
        return 0

    result = db.query(
        func.coalesce(func.sum(JournalLine.debit), 0).label("total_debit"),
        func.coalesce(func.sum(JournalLine.credit), 0).label("total_credit"),
    ).join(JournalEntry).filter(
        JournalLine.account_id == account_id,
        JournalEntry.is_confirmed == 1,
    ).first()

    total_debit = result.total_debit if result else 0
    total_credit = result.total_credit if result else 0

    if acct.type in ("asset", "expense"):
        return total_debit - total_credit
    else:
        return total_credit - total_debit


def validate_entry_balance(lines: list[dict]) -> bool:
    """Check that sum(debit) == sum(credit) for a set of journal lines."""
    total_debit = sum(line.get("debit", 0) for line in lines)
    total_credit = sum(line.get("credit", 0) for line in lines)
    return total_debit == total_credit and total_debit > 0

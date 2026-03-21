import json
import logging
import re
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Account, RawMessage, JournalEntry, JournalLine, CategoryRule
)
from app.services.ai_parser import parse_message

log = logging.getLogger(__name__)

# ── Duplicate detection ──
# Source priority: higher = better quality (keep this one)
_SOURCE_PRIORITY = {
    "카드": 3,      # 카드사 알림 (신한카드, KB국민카드 등)
    "카카오페이": 2,
    "카카오톡": 1,
}
_DUPLICATE_WINDOW_MS = 10 * 60 * 1000  # 10분


def _source_priority(source_name: str) -> int:
    """Return priority for a notification source. Higher = better quality."""
    for keyword, priority in _SOURCE_PRIORITY.items():
        if keyword in source_name:
            return priority
    return 0


def _check_duplicate(db: Session, msg: RawMessage, amount: int) -> bool:
    """Check for duplicate transaction within time window.

    If a duplicate is found, mark the lower-priority one as 'duplicate'
    and delete its journal entries. Returns True if THIS message should
    be skipped (it's the lower-priority duplicate).
    """
    window_start = msg.timestamp - _DUPLICATE_WINDOW_MS
    window_end = msg.timestamp + _DUPLICATE_WINDOW_MS

    # Find recent parsed messages in the time window (not already duplicate/failed)
    candidates = db.query(RawMessage).filter(
        RawMessage.id != msg.id,
        RawMessage.status.in_(["parsed", "approved"]),
        RawMessage.timestamp >= window_start,
        RawMessage.timestamp <= window_end,
    ).all()

    my_priority = _source_priority(msg.source_name)

    for candidate in candidates:
        # Check if amount matches by inspecting ai_result or journal entries
        candidate_amount = _extract_amount(db, candidate)
        if candidate_amount is None or candidate_amount != amount:
            continue

        # Found a match — compare priorities
        other_priority = _source_priority(candidate.source_name)

        if my_priority <= other_priority:
            # This message is lower or equal priority → skip it
            msg.status = "duplicate"
            msg.ai_result = json.dumps({
                "duplicate_of": candidate.id,
                "reason": f"같은 금액({amount}원) 중복 알림 — {candidate.source_name} 우선",
            }, ensure_ascii=False)
            db.commit()
            log.info("Duplicate: msg %d (%s) → duplicate of msg %d (%s), amount=%d",
                     msg.id, msg.source_name, candidate.id, candidate.source_name, amount)
            return True
        else:
            # This message is higher priority → replace the other one
            _mark_as_duplicate(db, candidate, msg.id, amount)
            log.info("Duplicate: msg %d (%s) replaced by msg %d (%s), amount=%d",
                     candidate.id, candidate.source_name, msg.id, msg.source_name, amount)
            return False

    return False


def _extract_amount(db: Session, msg: RawMessage) -> int | None:
    """Extract transaction amount from a processed message."""
    if msg.ai_result:
        try:
            result = json.loads(msg.ai_result)
            amt = result.get("amount")
            if amt:
                return int(amt)
        except (json.JSONDecodeError, ValueError):
            pass
    # Fallback: check journal entry lines
    entry = db.query(JournalEntry).filter(
        JournalEntry.raw_message_id == msg.id
    ).first()
    if entry and entry.lines:
        debit_line = next((l for l in entry.lines if l.debit > 0), None)
        if debit_line:
            return debit_line.debit
    return None


def _mark_as_duplicate(db: Session, msg: RawMessage, replaced_by_id: int, amount: int):
    """Mark a message as duplicate and delete its journal entries."""
    # Delete associated journal entries
    entries = db.query(JournalEntry).filter(
        JournalEntry.raw_message_id == msg.id,
        JournalEntry.is_confirmed == 0,  # Only remove unconfirmed
    ).all()
    for entry in entries:
        db.query(JournalLine).filter(JournalLine.entry_id == entry.id).delete()
        db.delete(entry)

    msg.status = "duplicate"
    msg.ai_result = json.dumps({
        "duplicate_of": replaced_by_id,
        "reason": f"같은 금액({amount}원) 중복 알림 — 더 높은 우선순위 소스로 교체됨",
    }, ensure_ascii=False)
    db.commit()

# 온통대전 SMS 패턴
_ONTONG_RE = re.compile(
    r'온통대전\s*체크카드.*?승인\s*([\d,]+)\s*원\s*캐시백적립\s*([\d,]+)\s*원\s*'
    r'(\d{2}/\d{2})\s*\d{2}:\d{2}\s*(.+?)\s*잔액'
)

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
            continue  # Groups are shown as context for their children
        label = type_label.get(a.type, a.type)
        # Include parent group name for disambiguation
        group_name = ""
        if a.parent_id and a.parent_id in acct_map:
            parent = acct_map[a.parent_id]
            # Walk up to root group
            while parent.parent_id and parent.parent_id in acct_map:
                parent = acct_map[parent.parent_id]
            group_name = f" [그룹:{parent.name}]"
        lines.append(f"{a.code} {a.name} ({label}){group_name}")
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


def _find_account_by_name(db: Session, name: str, parent_id: int | None = None) -> Account | None:
    """Find an active, non-group account by name, optionally under a specific parent."""
    q = db.query(Account).filter(
        Account.name == name, Account.is_active == 1,
        Account.is_group == 0, Account.is_deleted == 0,
    )
    if parent_id is not None:
        q = q.filter(Account.parent_id == parent_id)
    return q.first()


def _handle_ontong(db: Session, msg: RawMessage) -> list[JournalEntry] | None:
    """Handle 온통대전 체크카드 SMS — creates 2 entries (purchase + cashback).

    Uses AI to determine expense account AND the correct 온통대전(충전액)
    account (AI picks the right group based on device_name).
    Then finds sibling 온통대전(캐시백) under the same parent group.
    """
    m = _ONTONG_RE.search(msg.content)
    if not m:
        return None

    amount = int(m.group(1).replace(",", ""))
    cashback = int(m.group(2).replace(",", ""))
    date_mm_dd = m.group(3)  # "03/16"
    merchant = m.group(4).strip()

    year = datetime.now().year
    month, day = date_mm_dd.split("/")
    entry_date = f"{year}-{month}-{day}"

    # Use AI to determine both expense (debit) and 온통대전 충전액 (credit) accounts
    # AI already handles device_name → group preference
    accounts_ctx = _build_accounts_context(db)
    history_ctx = _build_history_context(db)
    device_name = getattr(msg, "device_name", "") or ""
    parsed = parse_message(msg.source_name, msg.content,
                           accounts_context=accounts_ctx,
                           history_context=history_ctx,
                           device_name=device_name)

    expense_acct = None
    charge_acct = None  # 온통대전(충전액)

    if parsed:
        msg.ai_result = json.dumps(parsed, ensure_ascii=False)
        expense_acct = _find_account_by_code(db, parsed.get("suggested_debit_code"))
        charge_acct = _find_account_by_code(db, parsed.get("suggested_credit_code"))

    # Fallback: find 온통대전(충전액) by name
    if not charge_acct:
        charge_acct = _find_account_by_name(db, "온통대전(충전액)")
    if not expense_acct:
        expense_acct = find_account_by_type(db, "expense")

    if not expense_acct or not charge_acct:
        log.warning("온통대전: expense or 충전액 account not found")
        return None

    # Find 캐시백 account under the same parent group as 충전액
    cashback_acct = None
    if charge_acct.parent_id:
        cashback_acct = _find_account_by_name(db, "온통대전(캐시백)", parent_id=charge_acct.parent_id)
    if not cashback_acct:
        cashback_acct = _find_account_by_name(db, "온통대전(캐시백)")

    # Find 캐시백수입 income account
    cb_income = _find_account_by_name(db, "캐시백수입")
    if not cb_income:
        cb_income = find_account_by_type(db, "income")

    entries = []

    # Entry 1: 차변 비용 / 대변 온통대전(충전액)
    e1 = JournalEntry(
        entry_date=entry_date, description=merchant,
        memo="온통대전 체크카드",
        raw_message_id=msg.id, source="webhook", is_confirmed=0,
    )
    db.add(e1)
    db.flush()
    db.add(JournalLine(entry_id=e1.id, account_id=expense_acct.id, debit=amount, credit=0))
    db.add(JournalLine(entry_id=e1.id, account_id=charge_acct.id, debit=0, credit=amount))
    entries.append(e1)

    # Entry 2: 차변 온통대전(캐시백) / 대변 캐시백수입
    if cashback > 0 and cashback_acct and cb_income:
        e2 = JournalEntry(
            entry_date=entry_date, description=f"캐시백 - {merchant}",
            memo="온통대전 캐시백적립",
            raw_message_id=msg.id, source="webhook", is_confirmed=0,
        )
        db.add(e2)
        db.flush()
        db.add(JournalLine(entry_id=e2.id, account_id=cashback_acct.id, debit=cashback, credit=0))
        db.add(JournalLine(entry_id=e2.id, account_id=cb_income.id, debit=0, credit=cashback))
        entries.append(e2)

    msg.status = "parsed"
    msg.ai_result = json.dumps({
        "source": "ontong", "amount": amount, "cashback": cashback,
        "merchant": merchant, "date": entry_date,
        "charge_account": charge_acct.code,
        "cashback_account": cashback_acct.code if cashback_acct else None,
    }, ensure_ascii=False)
    db.commit()

    # Duplicate check after commit (so ai_result with amount is saved)
    if _check_duplicate(db, msg, amount):
        return None

    log.info("온통대전: %s %d원, 캐시백 %d원 → %d entries (device=%s)",
             merchant, amount, cashback, len(entries), device_name)
    return entries


def process_message(db: Session, msg: RawMessage) -> JournalEntry | None:
    """Process a raw message: check rules, then AI parse, create journal entry."""

    # 0. Special handlers (온통대전 etc.)
    ontong_result = _handle_ontong(db, msg)
    if ontong_result is not None:
        return ontong_result[0] if ontong_result else None

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

        # Duplicate check before creating entry
        msg.ai_result = json.dumps({"source": "rule", "rule_id": rule.id, "amount": amount}, ensure_ascii=False)
        if _check_duplicate(db, msg, amount):
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

    # Duplicate check before creating entry
    if _check_duplicate(db, msg, amount):
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

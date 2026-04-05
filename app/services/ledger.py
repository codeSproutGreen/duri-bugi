"""Core ledger service — message processing pipeline and balance calculations."""

import json
import logging
import re
from datetime import datetime, timezone, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Account, RawMessage, JournalEntry, JournalLine, CategoryRule
)
from app.services.ai_parser import parse_message
from app.services.account_lookup import (
    find_account_by_code, find_account_by_name, find_account_by_type,
    build_accounts_context, build_history_context,
)
from app.services.duplicate_detection import check_duplicate

log = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))


def _msg_created_at(msg: "RawMessage") -> str:
    """Convert message epoch millis timestamp to KST ISO string."""
    return datetime.fromtimestamp(msg.timestamp / 1000, tz=_KST).strftime("%Y-%m-%dT%H:%M:%S")


# 온통대전 SMS 패턴
_ONTONG_RE = re.compile(
    r'온통대전\s*체크카드.*?승인\s*([\d,]+)\s*원\s*캐시백적립\s*([\d,]+)\s*원\s*'
    r'(\d{2}/\d{2})\s*\d{2}:\d{2}\s*(.+?)\s*잔액'
)
_ONTONG_CANCEL_RE = re.compile(
    r'온통대전\s*체크카드.*?승인취소\s*([\d,]+)\s*원\s*캐시백적립취소\s*([\d,]+)\s*원\s*'
    r'(\d{2}/\d{2})\s*\d{2}:\d{2}\s*(.+?)\s*잔액'
)


def _handle_ontong_cancel(db: Session, msg: RawMessage) -> list[JournalEntry] | None:
    """Handle 온통대전 체크카드 승인취소 SMS — creates 2 reversing entries (purchase + cashback)."""
    m = _ONTONG_CANCEL_RE.search(msg.content)
    if not m:
        return None

    amount = int(m.group(1).replace(",", ""))
    cashback = int(m.group(2).replace(",", ""))
    date_mm_dd = m.group(3)
    merchant = m.group(4).strip()

    year = datetime.now().year
    month, day = date_mm_dd.split("/")
    entry_date = f"{year}-{month}-{day}"

    device_name = getattr(msg, "device_name", "") or ""

    # 계좌 조회: charge_acct → parent 기준으로 같은 그룹의 cashback_acct 찾기
    charge_acct = find_account_by_name(db, "온통대전(충전액)")
    cashback_acct = None
    if charge_acct and charge_acct.parent_id:
        cashback_acct = find_account_by_name(db, "온통대전(캐시백)", parent_id=charge_acct.parent_id)
    if not cashback_acct:
        cashback_acct = find_account_by_name(db, "온통대전(캐시백)")

    cb_income = find_account_by_name(db, "캐시백수입")
    if not cb_income:
        cb_income = find_account_by_type(db, "income")

    # 원거래 비용 계정: 히스토리에서 같은 가맹점 온통대전 항목 조회, 없으면 기본 비용 계정
    expense_acct = None
    from app.models import JournalEntry as JE, JournalLine as JL
    original = (
        db.query(JE)
        .filter(JE.description == merchant, JE.memo == "온통대전 체크카드", JE.is_confirmed == 1)
        .order_by(JE.id.desc())
        .first()
    )
    if original:
        debit_line = next((l for l in original.lines if l.debit > 0 and l.account.type == "expense"), None)
        if debit_line:
            expense_acct = debit_line.account
    if not expense_acct:
        expense_acct = find_account_by_type(db, "expense")

    if not expense_acct or not charge_acct:
        log.warning("온통대전 취소: expense or 충전액 account not found")
        return None

    msg_time = _msg_created_at(msg)
    entries = []

    # 역분개 1: 매입 취소 (차변=충전액, 대변=비용)
    e1 = JournalEntry(
        entry_date=entry_date, description=f"{merchant} 승인취소",
        memo="온통대전 승인취소",
        raw_message_id=msg.id, source="webhook", is_confirmed=0,
        created_at=msg_time,
    )
    db.add(e1)
    db.flush()
    db.add(JournalLine(entry_id=e1.id, account_id=charge_acct.id, debit=amount, credit=0))
    db.add(JournalLine(entry_id=e1.id, account_id=expense_acct.id, debit=0, credit=amount))
    entries.append(e1)

    # 역분개 2: 캐시백 적립 취소 (차변=캐시백수입, 대변=캐시백)
    if cashback > 0 and cashback_acct and cb_income:
        e2 = JournalEntry(
            entry_date=entry_date, description=f"캐시백 취소 - {merchant}",
            memo="온통대전 캐시백적립취소",
            raw_message_id=msg.id, source="webhook", is_confirmed=0,
            created_at=msg_time,
        )
        db.add(e2)
        db.flush()
        db.add(JournalLine(entry_id=e2.id, account_id=cb_income.id, debit=cashback, credit=0))
        db.add(JournalLine(entry_id=e2.id, account_id=cashback_acct.id, debit=0, credit=cashback))
        entries.append(e2)

    msg.status = "parsed"
    msg.ai_result = json.dumps({
        "source": "ontong_cancel", "amount": amount, "cashback": cashback,
        "merchant": merchant, "date": entry_date,
        "charge_account": charge_acct.code,
        "cashback_account": cashback_acct.code if cashback_acct else None,
    }, ensure_ascii=False)
    db.commit()

    log.info("온통대전 취소: %s %d원, 캐시백취소 %d원 → %d entries (device=%s)",
             merchant, amount, cashback, len(entries), device_name)
    return entries


def _handle_ontong(db: Session, msg: RawMessage) -> list[JournalEntry] | None:
    """Handle 온통대전 체크카드 SMS — creates 2 entries (purchase + cashback)."""
    m = _ONTONG_RE.search(msg.content)
    if not m:
        return None

    amount = int(m.group(1).replace(",", ""))
    cashback = int(m.group(2).replace(",", ""))
    date_mm_dd = m.group(3)
    merchant = m.group(4).strip()

    year = datetime.now().year
    month, day = date_mm_dd.split("/")
    entry_date = f"{year}-{month}-{day}"

    accounts_ctx = build_accounts_context(db)
    history_ctx = build_history_context(db)
    device_name = getattr(msg, "device_name", "") or ""
    parsed = parse_message(msg.source_name, msg.content,
                           accounts_context=accounts_ctx,
                           history_context=history_ctx,
                           device_name=device_name)

    expense_acct = None
    charge_acct = None

    if parsed:
        msg.ai_result = json.dumps(parsed, ensure_ascii=False)
        expense_acct = find_account_by_code(db, parsed.get("suggested_debit_code"))
        charge_acct = find_account_by_code(db, parsed.get("suggested_credit_code"))

    if not charge_acct:
        charge_acct = find_account_by_name(db, "온통대전(충전액)")
    if not expense_acct:
        expense_acct = find_account_by_type(db, "expense")

    if not expense_acct or not charge_acct:
        log.warning("온통대전: expense or 충전액 account not found")
        return None

    cashback_acct = None
    if charge_acct.parent_id:
        cashback_acct = find_account_by_name(db, "온통대전(캐시백)", parent_id=charge_acct.parent_id)
    if not cashback_acct:
        cashback_acct = find_account_by_name(db, "온통대전(캐시백)")

    cb_income = find_account_by_name(db, "캐시백수입")
    if not cb_income:
        cb_income = find_account_by_type(db, "income")

    entries = []
    msg_time = _msg_created_at(msg)

    e1 = JournalEntry(
        entry_date=entry_date, description=merchant,
        memo="온통대전 체크카드",
        raw_message_id=msg.id, source="webhook", is_confirmed=0,
        created_at=msg_time,
    )
    db.add(e1)
    db.flush()
    db.add(JournalLine(entry_id=e1.id, account_id=expense_acct.id, debit=amount, credit=0))
    db.add(JournalLine(entry_id=e1.id, account_id=charge_acct.id, debit=0, credit=amount))
    entries.append(e1)

    if cashback > 0 and cashback_acct and cb_income:
        e2 = JournalEntry(
            entry_date=entry_date, description=f"캐시백 - {merchant}",
            memo="온통대전 캐시백적립",
            raw_message_id=msg.id, source="webhook", is_confirmed=0,
            created_at=msg_time,
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

    if check_duplicate(db, msg, amount):
        return None

    log.info("온통대전: %s %d원, 캐시백 %d원 → %d entries (device=%s)",
             merchant, amount, cashback, len(entries), device_name)
    return entries


def process_message(db: Session, msg: RawMessage) -> JournalEntry | None:
    """Process a raw message: check rules, then AI parse, create journal entry."""

    # 0-a. Auto-reject corporate messages
    if re.search(r"기업공용|법인카드|법인계좌", msg.content):
        msg.status = "rejected"
        msg.ai_result = json.dumps({"reason": "법인/기업공용 자동 거절"}, ensure_ascii=False)
        db.commit()
        log.info("Auto-rejected corporate message: %s", msg.id)
        return None

    # 0-b. Special handlers (온통대전 etc.) — 취소 먼저 체크
    ontong_result = _handle_ontong_cancel(db, msg)
    if ontong_result is not None:
        return ontong_result[0] if ontong_result else None

    ontong_result = _handle_ontong(db, msg)
    if ontong_result is not None:
        return ontong_result[0] if ontong_result else None

    # 1. Check category rules first (free, no API call)
    rule = check_category_rules(db, msg.content)
    if rule and rule.debit_account_id and rule.credit_account_id:
        log.info("Rule matched: %s", rule.merchant_pattern)
        rule.hit_count += 1
        rule.updated_at = datetime.now().isoformat()

        amount_match = re.search(r"(\d{1,3}(?:,\d{3})*)\s*원", msg.content)
        amount = int(amount_match.group(1).replace(",", "")) if amount_match else 0

        if amount <= 0:
            msg.status = "failed"
            msg.ai_result = json.dumps({"error": "rule matched but amount=0"}, ensure_ascii=False)
            db.commit()
            return None

        msg.ai_result = json.dumps({"source": "rule", "rule_id": rule.id, "amount": amount}, ensure_ascii=False)
        if check_duplicate(db, msg, amount):
            return None

        entry = JournalEntry(
            entry_date=datetime.fromtimestamp(msg.timestamp / 1000, tz=_KST).strftime("%Y-%m-%d"),
            description=f"{rule.merchant_pattern} ({msg.source_name})",
            raw_message_id=msg.id,
            source="webhook",
            is_confirmed=0,
            created_at=_msg_created_at(msg),
        )
        db.add(entry)
        db.flush()

        db.add(JournalLine(entry_id=entry.id, account_id=rule.debit_account_id, debit=amount, credit=0))
        db.add(JournalLine(entry_id=entry.id, account_id=rule.credit_account_id, debit=0, credit=amount))

        msg.status = "parsed"
        db.commit()
        return entry

    # 2. Build context for AI
    accounts_context = build_accounts_context(db)
    history_context = build_history_context(db)

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

    if check_duplicate(db, msg, amount):
        return None

    debit_acct = find_account_by_code(db, parsed.get("suggested_debit_code"))
    credit_acct = find_account_by_code(db, parsed.get("suggested_credit_code"))

    if not debit_acct:
        debit_acct = find_account_by_type(db, parsed.get("suggested_debit_type", "expense"))
    if not credit_acct:
        credit_acct = find_account_by_type(db, parsed.get("suggested_credit_type", "liability"))

    if not debit_acct or not credit_acct:
        msg.status = "failed"
        msg.ai_result = json.dumps({**parsed, "error": "no matching accounts"}, ensure_ascii=False)
        db.commit()
        return None

    entry_date = parsed.get("date")
    if not entry_date:
        entry_date = datetime.fromtimestamp(msg.timestamp / 1000, tz=_KST).strftime("%Y-%m-%d")

    merchant = parsed.get("merchant", "")
    description = merchant if merchant else msg.source_name

    entry = JournalEntry(
        entry_date=entry_date,
        description=description,
        memo=parsed.get("memo", ""),
        raw_message_id=msg.id,
        source="webhook",
        is_confirmed=0,
        created_at=_msg_created_at(msg),
    )
    db.add(entry)
    db.flush()

    db.add(JournalLine(entry_id=entry.id, account_id=debit_acct.id, debit=amount, credit=0))
    db.add(JournalLine(entry_id=entry.id, account_id=credit_acct.id, debit=0, credit=amount))

    msg.status = "parsed"
    db.commit()
    return entry


def check_category_rules(db: Session, content: str) -> CategoryRule | None:
    """Check if any category rule matches the message content."""
    rules = db.query(CategoryRule).all()
    for rule in rules:
        if rule.merchant_pattern and rule.merchant_pattern.lower() in content.lower():
            return rule
    return None


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

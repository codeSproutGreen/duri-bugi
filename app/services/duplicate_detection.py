"""Duplicate notification detection — identifies and marks duplicate transactions."""

import json
import logging

from sqlalchemy.orm import Session

from app.models import RawMessage, JournalEntry, JournalLine

log = logging.getLogger(__name__)

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


def check_duplicate(db: Session, msg: RawMessage, amount: int) -> bool:
    """Check for duplicate transaction within time window.

    If a duplicate is found, mark the lower-priority one as 'duplicate'
    and delete its journal entries. Returns True if THIS message should
    be skipped (it's the lower-priority duplicate).
    """
    window_start = msg.timestamp - _DUPLICATE_WINDOW_MS
    window_end = msg.timestamp + _DUPLICATE_WINDOW_MS

    candidates = db.query(RawMessage).filter(
        RawMessage.id != msg.id,
        RawMessage.status.in_(["parsed", "approved"]),
        RawMessage.timestamp >= window_start,
        RawMessage.timestamp <= window_end,
    ).all()

    my_priority = _source_priority(msg.source_name)

    for candidate in candidates:
        candidate_amount = extract_amount(db, candidate)
        if candidate_amount is None or candidate_amount != amount:
            continue

        other_priority = _source_priority(candidate.source_name)

        if my_priority <= other_priority:
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
            _mark_as_duplicate(db, candidate, msg.id, amount)
            log.info("Duplicate: msg %d (%s) replaced by msg %d (%s), amount=%d",
                     candidate.id, candidate.source_name, msg.id, msg.source_name, amount)
            return False

    return False


def extract_amount(db: Session, msg: RawMessage) -> int | None:
    """Extract transaction amount from a processed message."""
    if msg.ai_result:
        try:
            result = json.loads(msg.ai_result)
            amt = result.get("amount")
            if amt:
                return int(amt)
        except (json.JSONDecodeError, ValueError):
            pass
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
    entries = db.query(JournalEntry).filter(
        JournalEntry.raw_message_id == msg.id,
        JournalEntry.is_confirmed == 0,
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

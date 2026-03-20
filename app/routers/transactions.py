import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import JournalEntry, JournalLine, RawMessage, CategoryRule, Account
from app.schemas import EntryCreate, EntryUpdate, EntryOut, JournalLineOut
from app.services.ledger import validate_entry_balance
from app.services.audit import log_audit, entry_to_dict
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api", tags=["transactions"])
log = logging.getLogger(__name__)


def _entry_to_out(entry: JournalEntry) -> dict:
    lines = []
    for line in entry.lines:
        lines.append(JournalLineOut(
            id=line.id,
            account_id=line.account_id,
            account_name=line.account.name if line.account else "",
            account_code=line.account.code if line.account else "",
            debit=line.debit,
            credit=line.credit,
        ))
    return EntryOut(
        id=entry.id,
        entry_date=entry.entry_date,
        description=entry.description,
        memo=entry.memo,
        raw_message_id=entry.raw_message_id,
        is_confirmed=entry.is_confirmed,
        created_at=entry.created_at,
        lines=lines,
        raw_content=entry.raw_message.content if entry.raw_message else None,
    )


@router.get("/entries")
def list_entries(
    confirmed: int | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    search: str | None = Query(None),
    debit_accounts: str | None = Query(None),
    credit_accounts: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    q = db.query(JournalEntry).order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
    if confirmed is not None:
        q = q.filter(JournalEntry.is_confirmed == confirmed)
    if date_from:
        q = q.filter(JournalEntry.entry_date >= date_from)
    if date_to:
        q = q.filter(JournalEntry.entry_date <= date_to)
    if search:
        q = q.filter(JournalEntry.description.ilike(f"%{search}%"))
    if debit_accounts:
        ids = [int(x) for x in debit_accounts.split(",") if x.strip().isdigit()]
        if ids:
            q = q.filter(JournalEntry.lines.any(
                (JournalLine.debit > 0) & (JournalLine.account_id.in_(ids))
            ))
    if credit_accounts:
        ids = [int(x) for x in credit_accounts.split(",") if x.strip().isdigit()]
        if ids:
            q = q.filter(JournalEntry.lines.any(
                (JournalLine.credit > 0) & (JournalLine.account_id.in_(ids))
            ))

    entries = q.offset(offset).limit(limit).all()
    return [_entry_to_out(e) for e in entries]


@router.get("/entries/{entry_id}")
def get_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(JournalEntry).get(entry_id)
    if not entry:
        raise HTTPException(404, "Entry not found")
    return _entry_to_out(entry)


@router.post("/entries")
def create_entry(data: EntryCreate, request: Request, db: Session = Depends(get_db)):
    line_dicts = [l.model_dump() for l in data.lines]
    if not validate_entry_balance(line_dicts):
        raise HTTPException(400, "Debit and credit totals must match and be > 0")

    # Block group accounts from journal entries
    for line in data.lines:
        acct = db.query(Account).get(line.account_id)
        if acct and acct.is_group:
            raise HTTPException(400, f"그룹 계정 '{acct.name}'에는 거래를 입력할 수 없습니다.")

    entry = JournalEntry(
        entry_date=data.entry_date,
        description=data.description,
        memo=data.memo,
        source="web",
        created_by=get_current_user(request),
        is_confirmed=1,  # Manual entries are confirmed immediately
    )
    db.add(entry)
    db.flush()

    for line in data.lines:
        db.add(JournalLine(
            entry_id=entry.id,
            account_id=line.account_id,
            debit=line.debit,
            credit=line.credit,
        ))

    log_audit(db, "journal_entries", entry.id, "create",
             new_data=entry_to_dict(entry), user=get_current_user(request))
    db.commit()
    db.refresh(entry)
    return _entry_to_out(entry)


@router.put("/entries/{entry_id}")
def update_entry(entry_id: int, data: EntryUpdate, request: Request, db: Session = Depends(get_db)):
    entry = db.query(JournalEntry).get(entry_id)
    if not entry:
        raise HTTPException(404, "Entry not found")
    old = entry_to_dict(entry)

    if data.entry_date is not None:
        entry.entry_date = data.entry_date
    if data.description is not None:
        entry.description = data.description
    if data.memo is not None:
        entry.memo = data.memo

    if data.lines is not None:
        line_dicts = [l.model_dump() for l in data.lines]
        if not validate_entry_balance(line_dicts):
            raise HTTPException(400, "Debit and credit totals must match and be > 0")

        # Block group accounts
        for line in data.lines:
            acct = db.query(Account).get(line.account_id)
            if acct and acct.is_group:
                raise HTTPException(400, f"그룹 계정 '{acct.name}'에는 거래를 입력할 수 없습니다.")

        # Replace all lines
        db.query(JournalLine).filter(JournalLine.entry_id == entry_id).delete()
        for line in data.lines:
            db.add(JournalLine(
                entry_id=entry.id,
                account_id=line.account_id,
                debit=line.debit,
                credit=line.credit,
            ))

    entry.updated_at = datetime.now().isoformat()
    log_audit(db, "journal_entries", entry.id, "update",
             old_data=old, new_data=entry_to_dict(entry), user=get_current_user(request))
    db.commit()
    db.refresh(entry)
    return _entry_to_out(entry)


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: int, request: Request, db: Session = Depends(get_db)):
    entry = db.query(JournalEntry).get(entry_id)
    if not entry:
        raise HTTPException(404, "Entry not found")

    log_audit(db, "journal_entries", entry.id, "delete",
             old_data=entry_to_dict(entry), user=get_current_user(request))

    # Reset raw message status if linked
    if entry.raw_message_id:
        msg = db.query(RawMessage).get(entry.raw_message_id)
        if msg:
            msg.status = "pending"

    db.delete(entry)
    db.commit()
    return {"status": "deleted"}


@router.post("/entries/{entry_id}/confirm")
def confirm_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(JournalEntry).get(entry_id)
    if not entry:
        raise HTTPException(404, "Entry not found")

    entry.is_confirmed = 1
    entry.updated_at = datetime.now().isoformat()

    # Update raw message status
    if entry.raw_message_id:
        msg = db.query(RawMessage).get(entry.raw_message_id)
        if msg:
            msg.status = "approved"

    # Learn category rule from this confirmation
    if entry.lines and len(entry.lines) >= 2:
        merchant = entry.description
        if merchant:
            _upsert_category_rule(db, merchant, entry.lines)

    db.commit()
    return {"status": "confirmed"}


@router.post("/entries/{entry_id}/reject")
def reject_entry(entry_id: int, request: Request, db: Session = Depends(get_db)):
    entry = db.query(JournalEntry).get(entry_id)
    if not entry:
        raise HTTPException(404, "Entry not found")

    log_audit(db, "journal_entries", entry.id, "delete",
             old_data={**entry_to_dict(entry), "reason": "rejected"},
             user=get_current_user(request))

    if entry.raw_message_id:
        msg = db.query(RawMessage).get(entry.raw_message_id)
        if msg:
            msg.status = "rejected"

    db.delete(entry)
    db.commit()
    return {"status": "rejected"}


def _upsert_category_rule(db: Session, merchant: str, lines: list[JournalLine]):
    """Create or update a category rule based on confirmed entry."""
    if merchant.endswith("카드"):
        return
    debit_line = next((l for l in lines if l.debit > 0), None)
    credit_line = next((l for l in lines if l.credit > 0), None)
    if not debit_line or not credit_line:
        return

    existing = db.query(CategoryRule).filter(
        CategoryRule.merchant_pattern == merchant
    ).first()

    if existing:
        existing.debit_account_id = debit_line.account_id
        existing.credit_account_id = credit_line.account_id
        existing.hit_count += 1
        existing.updated_at = datetime.now().isoformat()
    else:
        db.add(CategoryRule(
            merchant_pattern=merchant,
            debit_account_id=debit_line.account_id,
            credit_account_id=credit_line.account_id,
        ))

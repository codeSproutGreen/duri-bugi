import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RawMessage
from app.schemas import MessageOut
from app.services.ledger import process_message

router = APIRouter(prefix="/api", tags=["messages"])
log = logging.getLogger(__name__)


@router.get("/messages", response_model=list[MessageOut])
def list_messages(
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    q = db.query(RawMessage).order_by(RawMessage.timestamp.desc())
    if status:
        q = q.filter(RawMessage.status == status)
    return q.offset(offset).limit(limit).all()


@router.get("/messages/{msg_id}", response_model=MessageOut)
def get_message(msg_id: int, db: Session = Depends(get_db)):
    msg = db.query(RawMessage).get(msg_id)
    if not msg:
        from fastapi import HTTPException
        raise HTTPException(404, "Message not found")
    return msg


@router.post("/messages/{msg_id}/reparse")
def reparse_message(msg_id: int, db: Session = Depends(get_db)):
    msg = db.query(RawMessage).get(msg_id)
    if not msg:
        from fastapi import HTTPException
        raise HTTPException(404, "Message not found")

    msg.status = "pending"
    msg.ai_result = None
    db.commit()

    entry = process_message(db, msg)
    return {
        "status": msg.status,
        "entry_id": entry.id if entry else None,
        "ai_result": msg.ai_result,
    }

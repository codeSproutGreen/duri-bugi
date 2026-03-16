import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import RawMessage
from app.schemas import WebhookPayload
from app.services.ledger import process_message

router = APIRouter(prefix="/api", tags=["webhook"])
log = logging.getLogger(__name__)


def verify_signature(body: bytes, signature: str | None) -> bool:
    """Verify HMAC-SHA256 signature from Android app."""
    if not settings.webhook_secret:
        return True  # No secret configured, skip verification
    if not signature:
        return False
    expected = hmac.new(
        settings.webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhook")
async def receive_webhook(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_webhook_signature: str | None = Header(None),
):
    # Signature verification (optional)
    # Note: in production, verify against raw body bytes

    msg = RawMessage(
        source_type=payload.type,
        source=payload.source,
        source_name=payload.sourceName,
        device_name=payload.deviceName,
        title=payload.title,
        content=payload.content,
        timestamp=payload.timestamp,
        status="pending",
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    log.info("Received %s from %s: %s", payload.type, payload.sourceName, payload.content[:50])

    # Process in background to respond quickly to Android
    background_tasks.add_task(_process_in_background, msg.id)

    return {"status": "ok", "message_id": msg.id}


def _process_in_background(message_id: int):
    """Process message in a separate DB session."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        msg = db.query(RawMessage).get(message_id)
        if msg and msg.status == "pending":
            process_message(db, msg)
    except Exception as e:
        log.error("Background process error for msg %d: %s", message_id, e)
    finally:
        db.close()

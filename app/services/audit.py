import json
from sqlalchemy.orm import Session
from app.models import AuditLog


def log_audit(
    db: Session,
    table_name: str,
    record_id: int,
    action: str,
    old_data: dict | None = None,
    new_data: dict | None = None,
    user: str = "",
):
    db.add(AuditLog(
        table_name=table_name,
        record_id=record_id,
        action=action,
        old_data=json.dumps(old_data, ensure_ascii=False) if old_data else None,
        new_data=json.dumps(new_data, ensure_ascii=False) if new_data else None,
        user=user,
    ))


def acct_to_dict(acct) -> dict:
    return {
        "id": acct.id,
        "code": acct.code,
        "name": acct.name,
        "type": acct.type,
        "parent_id": acct.parent_id,
        "is_group": acct.is_group,
        "is_active": acct.is_active,
    }


def entry_to_dict(entry) -> dict:
    return {
        "id": entry.id,
        "entry_date": entry.entry_date,
        "description": entry.description,
        "memo": entry.memo,
        "source": entry.source,
        "created_by": getattr(entry, "created_by", ""),
        "is_confirmed": entry.is_confirmed,
    }

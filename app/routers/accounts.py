from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, JournalLine
from app.schemas import AccountCreate, AccountUpdate, AccountOut
from app.services.ledger import get_account_balance
from app.services.audit import log_audit, acct_to_dict
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api", tags=["accounts"])


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db)):
    accounts = db.query(Account).filter(Account.is_deleted == 0).order_by(Account.sort_order, Account.code).all()
    acct_map = {a.id: a for a in accounts}

    def get_depth(a):
        depth = 0
        cur = a
        while cur.parent_id and cur.parent_id in acct_map and depth < 3:
            depth += 1
            cur = acct_map[cur.parent_id]
        return depth

    def get_children_ids(parent_id):
        return {a.id for a in accounts if a.parent_id == parent_id}

    result = {}
    for acct in accounts:
        if acct.type not in result:
            result[acct.type] = []
        children = get_children_ids(acct.id)
        child_balance = sum(get_account_balance(db, cid) for cid in children)
        own_balance = 0 if acct.is_group else get_account_balance(db, acct.id)
        result[acct.type].append(AccountOut(
            id=acct.id,
            code=acct.code,
            name=acct.name,
            type=acct.type,
            parent_id=acct.parent_id,
            is_group=acct.is_group,
            is_active=acct.is_active,
            sort_order=acct.sort_order,
            balance=own_balance + child_balance,
            depth=get_depth(acct),
            children_count=len(children),
        ))
    return result


TYPE_PREFIX = {"asset": "1", "liability": "2", "equity": "3", "income": "4", "expense": "5"}


def _next_code(db: Session, acct_type: str) -> str:
    """Generate next available code for a given account type (includes deleted codes to avoid reuse)."""
    prefix = TYPE_PREFIX.get(acct_type, "9")
    existing = (
        db.query(Account.code)
        .filter(Account.type == acct_type, Account.code.like(f"{prefix}%"))
        .all()  # includes is_deleted accounts to prevent code reuse
    )
    existing_nums = []
    for (code,) in existing:
        try:
            existing_nums.append(int(code))
        except ValueError:
            pass
    # Start from prefix*1000+1 (e.g. 1001 for asset), increment by 1
    base = int(prefix) * 1000
    next_num = base + 1
    if existing_nums:
        next_num = max(existing_nums) + 1
    return str(next_num)


@router.get("/accounts/next-code")
def get_next_code(type: str, db: Session = Depends(get_db)):
    """Get the next available code for a given account type."""
    if type not in TYPE_PREFIX:
        raise HTTPException(400, "Invalid account type")
    return {"code": _next_code(db, type)}


@router.post("/accounts", response_model=AccountOut)
def create_account(data: AccountCreate, request: Request, db: Session = Depends(get_db)):
    if data.type not in ("asset", "liability", "equity", "income", "expense"):
        raise HTTPException(400, "Invalid account type")

    # Auto-generate code if not provided or empty
    code = data.code.strip() if data.code else ""
    if not code:
        code = _next_code(db, data.type)

    existing = db.query(Account).filter(Account.code == code).first()  # includes deleted
    if existing:
        raise HTTPException(400, f"Account code '{code}' already exists")

    # Set sort_order to end of list
    max_order = db.query(func.max(Account.sort_order)).filter(
        Account.type == data.type
    ).scalar() or 0

    acct = Account(
        code=code,
        name=data.name,
        type=data.type,
        parent_id=data.parent_id,
        is_group=data.is_group,
        sort_order=max_order + 1,
    )
    db.add(acct)
    db.flush()

    # Auto-set parent as group if adding a child
    if data.parent_id:
        parent = db.query(Account).get(data.parent_id)
        if parent and not parent.is_group:
            parent.is_group = 1

    log_audit(db, "accounts", acct.id, "create",
             new_data=acct_to_dict(acct), user=get_current_user(request))
    db.commit()
    db.refresh(acct)
    return AccountOut(
        id=acct.id, code=acct.code, name=acct.name,
        type=acct.type, parent_id=acct.parent_id,
        is_group=acct.is_group, is_active=acct.is_active,
    )


@router.put("/accounts/reorder")
def reorder_accounts(data: list[dict] = Body(...), db: Session = Depends(get_db)):
    """Batch update sort_order and parent_id. data: [{id, sort_order, parent_id}]"""
    for item in data:
        acct = db.query(Account).filter(Account.id == item["id"], Account.is_deleted == 0).first()
        if acct:
            acct.sort_order = item.get("sort_order", acct.sort_order)
            if "parent_id" in item:
                acct.parent_id = item["parent_id"]
    db.commit()
    return {"ok": True}


@router.put("/accounts/{acct_id}", response_model=AccountOut)
def update_account(acct_id: int, data: AccountUpdate, request: Request, db: Session = Depends(get_db)):
    acct = db.query(Account).filter(Account.id == acct_id, Account.is_deleted == 0).first()
    if not acct:
        raise HTTPException(404, "Account not found")

    old = acct_to_dict(acct)
    provided = data.model_fields_set
    if 'code' in provided:
        acct.code = data.code
    if 'name' in provided:
        acct.name = data.name
    if 'type' in provided:
        acct.type = data.type
    if 'parent_id' in provided:
        acct.parent_id = data.parent_id
    if 'is_group' in provided:
        acct.is_group = data.is_group
    if 'is_active' in provided:
        acct.is_active = data.is_active
    if 'sort_order' in provided:
        acct.sort_order = data.sort_order

    log_audit(db, "accounts", acct.id, "update",
             old_data=old, new_data=acct_to_dict(acct), user=get_current_user(request))
    db.commit()
    db.refresh(acct)
    return AccountOut(
        id=acct.id, code=acct.code, name=acct.name,
        type=acct.type, parent_id=acct.parent_id,
        is_group=acct.is_group, is_active=acct.is_active,
        balance=get_account_balance(db, acct.id),
    )


@router.delete("/accounts/{acct_id}")
def delete_account(acct_id: int, request: Request, db: Session = Depends(get_db)):
    acct = db.query(Account).filter(Account.id == acct_id, Account.is_deleted == 0).first()
    if not acct:
        raise HTTPException(404, "Account not found")

    # Block if account has active children
    children = db.query(Account).filter(
        Account.parent_id == acct_id, Account.is_deleted == 0
    ).first()
    if children:
        raise HTTPException(400, "하위 계정이 있는 계정은 삭제할 수 없습니다.")

    # Soft delete
    old = acct_to_dict(acct)
    acct.is_deleted = 1
    acct.is_active = 0
    log_audit(db, "accounts", acct.id, "delete",
             old_data=old, user=get_current_user(request))
    db.commit()
    return {"ok": True}

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account
from app.schemas import AccountCreate, AccountUpdate, AccountOut
from app.services.ledger import get_account_balance

router = APIRouter(prefix="/api", tags=["accounts"])


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db)):
    accounts = db.query(Account).order_by(Account.code).all()
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
        result[acct.type].append(AccountOut(
            id=acct.id,
            code=acct.code,
            name=acct.name,
            type=acct.type,
            parent_id=acct.parent_id,
            is_active=acct.is_active,
            balance=get_account_balance(db, acct.id) + child_balance,
            depth=get_depth(acct),
            children_count=len(children),
        ))
    return result


@router.post("/accounts", response_model=AccountOut)
def create_account(data: AccountCreate, db: Session = Depends(get_db)):
    if data.type not in ("asset", "liability", "equity", "income", "expense"):
        raise HTTPException(400, "Invalid account type")

    existing = db.query(Account).filter(Account.code == data.code).first()
    if existing:
        raise HTTPException(400, f"Account code '{data.code}' already exists")

    acct = Account(
        code=data.code,
        name=data.name,
        type=data.type,
        parent_id=data.parent_id,
    )
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return AccountOut(
        id=acct.id, code=acct.code, name=acct.name,
        type=acct.type, parent_id=acct.parent_id, is_active=acct.is_active,
    )


@router.put("/accounts/{acct_id}", response_model=AccountOut)
def update_account(acct_id: int, data: AccountUpdate, db: Session = Depends(get_db)):
    acct = db.query(Account).get(acct_id)
    if not acct:
        raise HTTPException(404, "Account not found")

    provided = data.model_fields_set
    if 'code' in provided:
        acct.code = data.code
    if 'name' in provided:
        acct.name = data.name
    if 'type' in provided:
        acct.type = data.type
    if 'parent_id' in provided:
        acct.parent_id = data.parent_id
    if 'is_active' in provided:
        acct.is_active = data.is_active

    db.commit()
    db.refresh(acct)
    return AccountOut(
        id=acct.id, code=acct.code, name=acct.name,
        type=acct.type, parent_id=acct.parent_id, is_active=acct.is_active,
        balance=get_account_balance(db, acct.id),
    )

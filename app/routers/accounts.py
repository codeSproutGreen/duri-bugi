from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, JournalLine
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


TYPE_PREFIX = {"asset": "1", "liability": "2", "equity": "3", "income": "4", "expense": "5"}


def _next_code(db: Session, acct_type: str) -> str:
    """Generate next available code for a given account type."""
    prefix = TYPE_PREFIX.get(acct_type, "9")
    existing = (
        db.query(Account.code)
        .filter(Account.type == acct_type, Account.code.like(f"{prefix}%"))
        .all()
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
def create_account(data: AccountCreate, db: Session = Depends(get_db)):
    if data.type not in ("asset", "liability", "equity", "income", "expense"):
        raise HTTPException(400, "Invalid account type")

    # Auto-generate code if not provided or empty
    code = data.code.strip() if data.code else ""
    if not code:
        code = _next_code(db, data.type)

    existing = db.query(Account).filter(Account.code == code).first()
    if existing:
        raise HTTPException(400, f"Account code '{code}' already exists")

    acct = Account(
        code=code,
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


@router.delete("/accounts/{acct_id}")
def delete_account(acct_id: int, db: Session = Depends(get_db)):
    acct = db.query(Account).get(acct_id)
    if not acct:
        raise HTTPException(404, "Account not found")

    # Block if account has transactions
    used = db.query(JournalLine).filter(JournalLine.account_id == acct_id).first()
    if used:
        raise HTTPException(400, "거래 내역이 있는 계정은 삭제할 수 없습니다.")

    # Block if account has children
    children = db.query(Account).filter(Account.parent_id == acct_id).first()
    if children:
        raise HTTPException(400, "하위 계정이 있는 계정은 삭제할 수 없습니다.")

    db.delete(acct)
    db.commit()
    return {"ok": True}

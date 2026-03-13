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
    result = {}
    for acct in accounts:
        if acct.type not in result:
            result[acct.type] = []
        result[acct.type].append(AccountOut(
            id=acct.id,
            code=acct.code,
            name=acct.name,
            type=acct.type,
            parent_id=acct.parent_id,
            is_active=acct.is_active,
            balance=get_account_balance(db, acct.id),
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

    if data.code is not None:
        acct.code = data.code
    if data.name is not None:
        acct.name = data.name
    if data.type is not None:
        acct.type = data.type
    if data.parent_id is not None:
        acct.parent_id = data.parent_id
    if data.is_active is not None:
        acct.is_active = data.is_active

    db.commit()
    db.refresh(acct)
    return AccountOut(
        id=acct.id, code=acct.code, name=acct.name,
        type=acct.type, parent_id=acct.parent_id, is_active=acct.is_active,
        balance=get_account_balance(db, acct.id),
    )

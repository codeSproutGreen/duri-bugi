"""Asset summary — combined net worth calculation."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, RealEstate, StockAccount, StockPerson
from app.services.ledger import get_account_balance
from app.routers.assets._helpers import _person_to_out

router = APIRouter(prefix="/api/assets", tags=["assets-summary"])


@router.get("/summary")
def asset_summary(db: Session = Depends(get_db)):
    # Cash/bank from ledger — exclude accounts linked to stock accounts and investment tracking
    linked_ids = {
        sa.linked_account_id
        for sa in db.query(StockAccount).filter(StockAccount.linked_account_id.isnot(None)).all()
    }
    invest_acct = db.query(Account).filter(Account.code == "1100").first()
    if invest_acct:
        linked_ids.add(invest_acct.id)

    cash_bank = 0
    total_liability = 0
    accounts = db.query(Account).filter(
        Account.type.in_(["asset", "liability"]),
    ).all()
    for acct in accounts:
        if acct.is_group:
            continue
        if acct.id in linked_ids:
            continue
        bal = get_account_balance(db, acct.id)
        if acct.type == "asset":
            cash_bank += bal
        else:
            total_liability += bal

    # Stocks
    persons = db.query(StockPerson).order_by(StockPerson.sort_order, StockPerson.id).all()
    persons_out = [_person_to_out(p, db) for p in persons]
    stocks_total = sum(p["total_value"] for p in persons_out)

    # Real estate
    re_items = db.query(RealEstate).order_by(RealEstate.sort_order, RealEstate.id).all()
    re_out = [{"id": r.id, "name": r.name, "value": r.value, "memo": r.memo, "updated_at": r.updated_at} for r in re_items]
    re_total = sum(r.value for r in re_items)

    total_assets = cash_bank + stocks_total + re_total
    net_worth = total_assets - total_liability

    return {
        "cash_bank": cash_bank,
        "total_liability": total_liability,
        "stocks_total": stocks_total,
        "stocks_by_person": persons_out,
        "realestate_total": re_total,
        "realestate_items": re_out,
        "total_assets": total_assets,
        "net_worth": net_worth,
    }

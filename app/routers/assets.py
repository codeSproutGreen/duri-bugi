import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Account, JournalEntry, JournalLine,
    StockPerson, StockAccount, StockHolding, RealEstate,
)
from app.schemas import (
    StockPersonCreate, StockPersonOut, StockAccountCreate, StockAccountOut,
    StockHoldingCreate, StockHoldingUpdate, StockHoldingOut,
    RealEstateCreate, RealEstateUpdate, RealEstateOut,
    AssetSummaryOut,
)
from app.services.stock_price import fetch_prices

router = APIRouter(prefix="/api/assets", tags=["assets"])
log = logging.getLogger(__name__)


def _holding_to_out(h: StockHolding) -> dict:
    mv = h.quantity * h.current_price
    cost = h.quantity * h.avg_price
    gl = mv - cost
    gl_pct = (gl / cost * 100) if cost else 0.0
    return {
        "id": h.id, "account_id": h.account_id,
        "ticker": h.ticker, "name": h.name,
        "quantity": h.quantity, "avg_price": h.avg_price,
        "current_price": h.current_price,
        "market_value": mv, "gain_loss": gl,
        "gain_loss_pct": round(gl_pct, 2),
        "price_updated_at": h.price_updated_at,
    }


def _account_to_out(a: StockAccount) -> dict:
    holdings = [_holding_to_out(h) for h in a.holdings]
    return {
        "id": a.id, "person_id": a.person_id, "name": a.name,
        "holdings": holdings,
        "total_value": sum(h["market_value"] for h in holdings),
    }


def _person_to_out(p: StockPerson) -> dict:
    accounts = [_account_to_out(a) for a in p.accounts]
    return {
        "id": p.id, "name": p.name, "sort_order": p.sort_order,
        "accounts": accounts,
        "total_value": sum(a["total_value"] for a in accounts),
    }


# ── Stock Persons ──
@router.get("/stock/persons")
def list_persons(db: Session = Depends(get_db)):
    persons = db.query(StockPerson).order_by(StockPerson.sort_order, StockPerson.id).all()
    return [_person_to_out(p) for p in persons]


@router.post("/stock/persons")
def create_person(data: StockPersonCreate, db: Session = Depends(get_db)):
    p = StockPerson(name=data.name)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _person_to_out(p)


@router.put("/stock/persons/{pid}")
def update_person(pid: int, data: StockPersonCreate, db: Session = Depends(get_db)):
    p = db.query(StockPerson).get(pid)
    if not p:
        raise HTTPException(404)
    p.name = data.name
    db.commit()
    return _person_to_out(p)


@router.delete("/stock/persons/{pid}")
def delete_person(pid: int, db: Session = Depends(get_db)):
    p = db.query(StockPerson).get(pid)
    if not p:
        raise HTTPException(404)
    db.delete(p)
    db.commit()
    return {"ok": True}


# ── Stock Accounts ──
@router.post("/stock/accounts")
def create_account(data: StockAccountCreate, db: Session = Depends(get_db)):
    a = StockAccount(person_id=data.person_id, name=data.name)
    db.add(a)
    db.commit()
    db.refresh(a)
    return _account_to_out(a)


@router.put("/stock/accounts/{aid}")
def update_account(aid: int, data: StockAccountCreate, db: Session = Depends(get_db)):
    a = db.query(StockAccount).get(aid)
    if not a:
        raise HTTPException(404)
    a.name = data.name
    db.commit()
    return _account_to_out(a)


@router.delete("/stock/accounts/{aid}")
def delete_account(aid: int, db: Session = Depends(get_db)):
    a = db.query(StockAccount).get(aid)
    if not a:
        raise HTTPException(404)
    db.delete(a)
    db.commit()
    return {"ok": True}


# ── Stock Holdings ──
@router.post("/stock/holdings")
def create_holding(data: StockHoldingCreate, db: Session = Depends(get_db)):
    h = StockHolding(
        account_id=data.account_id, ticker=data.ticker, name=data.name,
        quantity=data.quantity, avg_price=data.avg_price,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return _holding_to_out(h)


@router.put("/stock/holdings/{hid}")
def update_holding(hid: int, data: StockHoldingUpdate, db: Session = Depends(get_db)):
    h = db.query(StockHolding).get(hid)
    if not h:
        raise HTTPException(404)
    if data.ticker is not None:
        h.ticker = data.ticker
    if data.name is not None:
        h.name = data.name
    if data.quantity is not None:
        h.quantity = data.quantity
    if data.avg_price is not None:
        h.avg_price = data.avg_price
    db.commit()
    return _holding_to_out(h)


@router.delete("/stock/holdings/{hid}")
def delete_holding(hid: int, db: Session = Depends(get_db)):
    h = db.query(StockHolding).get(hid)
    if not h:
        raise HTTPException(404)
    db.delete(h)
    db.commit()
    return {"ok": True}


# ── Refresh Prices ──
@router.post("/stock/refresh-prices")
def refresh_prices(db: Session = Depends(get_db)):
    holdings = db.query(StockHolding).filter(StockHolding.quantity > 0).all()
    tickers = list({h.ticker for h in holdings})
    if not tickers:
        return {"updated": 0}

    prices = fetch_prices(tickers)
    now = datetime.now().isoformat()
    updated = 0
    for h in holdings:
        if h.ticker in prices:
            h.current_price = prices[h.ticker]
            h.price_updated_at = now
            updated += 1
    db.commit()
    log.info("Refreshed %d/%d stock prices", updated, len(holdings))
    return {"updated": updated}


# ── Real Estate ──
@router.get("/realestate")
def list_realestate(db: Session = Depends(get_db)):
    items = db.query(RealEstate).order_by(RealEstate.sort_order, RealEstate.id).all()
    return [{"id": r.id, "name": r.name, "value": r.value, "memo": r.memo, "updated_at": r.updated_at} for r in items]


@router.post("/realestate")
def create_realestate(data: RealEstateCreate, db: Session = Depends(get_db)):
    r = RealEstate(name=data.name, value=data.value, memo=data.memo)
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "name": r.name, "value": r.value, "memo": r.memo, "updated_at": r.updated_at}


@router.put("/realestate/{rid}")
def update_realestate(rid: int, data: RealEstateUpdate, db: Session = Depends(get_db)):
    r = db.query(RealEstate).get(rid)
    if not r:
        raise HTTPException(404)
    if data.name is not None:
        r.name = data.name
    if data.value is not None:
        r.value = data.value
    if data.memo is not None:
        r.memo = data.memo
    r.updated_at = datetime.now().isoformat()
    db.commit()
    return {"id": r.id, "name": r.name, "value": r.value, "memo": r.memo, "updated_at": r.updated_at}


@router.delete("/realestate/{rid}")
def delete_realestate(rid: int, db: Session = Depends(get_db)):
    r = db.query(RealEstate).get(rid)
    if not r:
        raise HTTPException(404)
    db.delete(r)
    db.commit()
    return {"ok": True}


# ── Asset Summary ──
@router.get("/summary")
def asset_summary(db: Session = Depends(get_db)):
    # Cash/bank from ledger
    cash_bank = 0
    total_liability = 0
    accounts = db.query(Account).filter(
        Account.is_active == 1, Account.is_group == 0, Account.is_deleted == 0,
        Account.type.in_(["asset", "liability"]),
    ).all()
    for acct in accounts:
        result = db.query(
            func.coalesce(func.sum(JournalLine.debit), 0).label("d"),
            func.coalesce(func.sum(JournalLine.credit), 0).label("c"),
        ).join(JournalEntry).filter(
            JournalLine.account_id == acct.id, JournalEntry.is_confirmed == 1,
        ).first()
        bal = (result.d - result.c) if acct.type == "asset" else (result.c - result.d)
        if acct.type == "asset":
            cash_bank += bal
        else:
            total_liability += bal

    # Stocks
    persons = db.query(StockPerson).order_by(StockPerson.sort_order, StockPerson.id).all()
    persons_out = [_person_to_out(p) for p in persons]
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

"""Stock management — persons, accounts, holdings, sell, price refresh."""

import logging
import time
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, StockAccount, StockHolding, StockPerson
from app.schemas import (
    StockPersonCreate, StockAccountCreate,
    StockHoldingCreate, StockHoldingUpdate, StockHoldingSell,
)
from app.services.stock_price import fetch_price, fetch_prices, lookup_ticker
from app.routers.assets._helpers import (
    _holding_to_out, _account_to_out, _person_to_out,
    _get_invest_accounts, _create_journal,
)

router = APIRouter(prefix="/api/assets", tags=["assets-stock"])
log = logging.getLogger(__name__)


# ── Stock Persons ──
@router.get("/stock/persons")
def list_persons(db: Session = Depends(get_db)):
    persons = db.query(StockPerson).order_by(StockPerson.sort_order, StockPerson.id).all()
    return [_person_to_out(p, db) for p in persons]


@router.post("/stock/persons")
def create_person(data: StockPersonCreate, db: Session = Depends(get_db)):
    p = StockPerson(name=data.name)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _person_to_out(p, db)


@router.put("/stock/persons/{pid}")
def update_person(pid: int, data: StockPersonCreate, db: Session = Depends(get_db)):
    p = db.query(StockPerson).get(pid)
    if not p:
        raise HTTPException(404)
    p.name = data.name
    db.commit()
    return _person_to_out(p, db)


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
    a = StockAccount(person_id=data.person_id, brokerage=data.brokerage, name=data.name, account_type=data.account_type, linked_account_id=data.linked_account_id)
    db.add(a)
    db.commit()
    db.refresh(a)
    return _account_to_out(a, db)


@router.put("/stock/accounts/{aid}")
def update_account(aid: int, data: StockAccountCreate, db: Session = Depends(get_db)):
    a = db.query(StockAccount).get(aid)
    if not a:
        raise HTTPException(404)
    a.brokerage = data.brokerage
    a.name = data.name
    a.account_type = data.account_type
    a.linked_account_id = data.linked_account_id
    db.commit()
    return _account_to_out(a, db)


@router.delete("/stock/accounts/{aid}")
def delete_account(aid: int, db: Session = Depends(get_db)):
    a = db.query(StockAccount).get(aid)
    if not a:
        raise HTTPException(404)
    db.delete(a)
    db.commit()
    return {"ok": True}


# ── Ticker Lookup ──
@router.get("/stock/lookup/{ticker}")
def stock_lookup(ticker: str, exchange: str | None = None):
    result = lookup_ticker(ticker, exchange)
    if not result:
        raise HTTPException(404, "종목을 찾을 수 없습니다")
    return result


# ── Stock Holdings ──
@router.put("/stock/holdings/reorder")
def reorder_holdings(data: list[dict] = Body(...), db: Session = Depends(get_db)):
    for item in data:
        h = db.query(StockHolding).get(item["id"])
        if h:
            h.sort_order = item.get("sort_order", 0)
    db.commit()
    return {"ok": True}


@router.post("/stock/holdings")
def create_holding(data: StockHoldingCreate, db: Session = Depends(get_db)):
    h = StockHolding(
        account_id=data.account_id, ticker=data.ticker, name=data.name,
        exchange=data.exchange, quantity=data.quantity, avg_price=data.avg_price,
    )
    db.add(h)
    db.flush()

    # Auto journal: 차변 투자자산 / 대변 예수금
    acct = db.query(StockAccount).get(data.account_id)
    if acct and acct.linked_account_id:
        invest, _ = _get_invest_accounts(db)
        if invest:
            cost = data.quantity * data.avg_price
            _create_journal(db, f"주식매수 {data.name}", [
                (invest.id, cost, 0),          # 차변: 투자자산
                (acct.linked_account_id, 0, cost),  # 대변: 예수금
            ])

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
    if data.exchange is not None:
        h.exchange = data.exchange
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


# ── Sell Holding ──
@router.get("/stock/sell-test")
def sell_test():
    return {"ok": True, "msg": "sell route works"}

@router.put("/stock/sell")
def sell_holding(data: StockHoldingSell, db: Session = Depends(get_db)):
    h = db.query(StockHolding).get(data.holding_id)
    if not h:
        raise HTTPException(404)
    if data.quantity <= 0 or data.quantity > h.quantity:
        raise HTTPException(400, "매도 수량이 유효하지 않습니다")
    if data.sell_price <= 0:
        raise HTTPException(400, "매도 단가가 유효하지 않습니다")

    proceeds = data.quantity * data.sell_price      # 매도대금
    fee = data.fee or 0                              # 수수료+세금
    net_proceeds = proceeds - fee                    # 실수령액
    cost_basis = data.quantity * h.avg_price         # 취득원가
    realized_gl = net_proceeds - cost_basis          # 실현손익 (수수료 차감 후)

    # Auto journal if linked account exists
    acct = db.query(StockAccount).get(h.account_id)
    if acct and acct.linked_account_id:
        invest, gain_loss = _get_invest_accounts(db)
        fee_acct = db.query(Account).filter(Account.code == "5007").first()
        if invest and gain_loss:
            journal_lines = [
                (acct.linked_account_id, net_proceeds, 0),  # 차변: 예수금 (실수령액)
                (invest.id, 0, cost_basis),                  # 대변: 투자자산 (취득원가)
            ]
            if fee > 0 and fee_acct:
                journal_lines.append((fee_acct.id, fee, 0))  # 차변: 투자수수료
            gl_amount = proceeds - cost_basis  # 손익은 수수료 차감 전 (수수료는 별도 비용)
            if gl_amount > 0:
                journal_lines.append((gain_loss.id, 0, gl_amount))   # 대변: 투자손익 (이익)
            elif gl_amount < 0:
                journal_lines.append((gain_loss.id, -gl_amount, 0))  # 차변: 투자손익 (손실)
            _create_journal(db, f"주식매도 {h.name}", journal_lines)

    # Update holding
    h.quantity -= data.quantity
    if h.quantity == 0:
        db.delete(h)

    db.commit()

    result = {
        "sold_quantity": data.quantity,
        "sell_price": data.sell_price,
        "fee": fee,
        "proceeds": proceeds,
        "net_proceeds": net_proceeds,
        "cost_basis": cost_basis,
        "realized_gain_loss": realized_gl,
        "remaining_quantity": h.quantity if h.quantity > 0 else 0,
    }
    log.info("Sold %d x %s @ %d, fee=%d, P&L: %d", data.quantity, h.name, data.sell_price, fee, realized_gl)
    return result


# ── Refresh Prices ──
@router.post("/stock/refresh-prices")
def refresh_prices(db: Session = Depends(get_db)):
    holdings = db.query(StockHolding).filter(StockHolding.quantity > 0).all()
    if not holdings:
        return {"updated": 0}

    # Split domestic vs foreign
    domestic = [h for h in holdings if not h.exchange]
    foreign = [h for h in holdings if h.exchange]

    # Batch fetch domestic
    domestic_tickers = list({h.ticker for h in domestic})
    prices = fetch_prices(domestic_tickers) if domestic_tickers else {}

    now = datetime.now().isoformat()
    updated = 0
    for h in domestic:
        if h.ticker in prices:
            h.current_price = prices[h.ticker]
            h.price_updated_at = now
            updated += 1

    # Fetch foreign one by one (different exchange per ticker)
    for h in foreign:
        price = fetch_price(h.ticker, h.exchange)
        if price is not None:
            h.current_price = price
            h.price_updated_at = now
            updated += 1
        time.sleep(0.2)
    db.commit()
    log.info("Refreshed %d/%d stock prices", updated, len(holdings))
    return {"updated": updated}

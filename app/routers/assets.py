import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Account, JournalEntry, JournalLine,
    StockPerson, StockAccount, StockHolding, RealEstate,
)
from app.services.ledger import get_account_balance
from app.schemas import (
    StockPersonCreate, StockPersonOut, StockAccountCreate, StockAccountOut,
    StockHoldingCreate, StockHoldingUpdate, StockHoldingSell, StockHoldingOut,
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


def _account_to_out(a: StockAccount, db: Session = None) -> dict:
    holdings = [_holding_to_out(h) for h in a.holdings]
    holdings_value = sum(h["market_value"] for h in holdings)
    cash_balance = 0
    linked_name = None
    if a.linked_account_id and db:
        cash_balance = get_account_balance(db, a.linked_account_id)
        linked = db.query(Account).get(a.linked_account_id)
        linked_name = linked.name if linked else None
    return {
        "id": a.id, "person_id": a.person_id,
        "brokerage": a.brokerage or "", "name": a.name,
        "account_type": a.account_type or "cash",
        "linked_account_id": a.linked_account_id,
        "linked_account_name": linked_name,
        "cash_balance": cash_balance,
        "holdings": holdings,
        "total_value": holdings_value + cash_balance,
    }


def _person_to_out(p: StockPerson, db: Session = None) -> dict:
    accounts = [_account_to_out(a, db) for a in p.accounts]
    return {
        "id": p.id, "name": p.name, "sort_order": p.sort_order,
        "accounts": accounts,
        "total_value": sum(a["total_value"] for a in accounts),
    }


def _get_invest_accounts(db: Session) -> tuple[Account | None, Account | None]:
    """Return (투자자산, 투자손익) accounts."""
    invest = db.query(Account).filter(Account.code == "1100").first()
    gain_loss = db.query(Account).filter(Account.code == "4100").first()
    return invest, gain_loss


def _create_journal(db: Session, description: str, lines: list[tuple[int, int, int]]):
    """Create a confirmed journal entry. lines = [(account_id, debit, credit), ...]"""
    entry = JournalEntry(
        entry_date=datetime.now().strftime("%Y-%m-%d"),
        description=description,
        source="asset",
        is_confirmed=1,
    )
    db.add(entry)
    db.flush()
    for account_id, debit, credit in lines:
        db.add(JournalLine(entry_id=entry.id, account_id=account_id, debit=debit, credit=credit))
    return entry


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


# ── Stock Holdings ──
@router.post("/stock/holdings")
def create_holding(data: StockHoldingCreate, db: Session = Depends(get_db)):
    h = StockHolding(
        account_id=data.account_id, ticker=data.ticker, name=data.name,
        quantity=data.quantity, avg_price=data.avg_price,
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
    # Cash/bank from ledger (same logic as dashboard)
    # Exclude accounts linked to stock accounts and investment tracking accounts
    linked_ids = {
        sa.linked_account_id
        for sa in db.query(StockAccount).filter(StockAccount.linked_account_id.isnot(None)).all()
    }
    # 투자자산(1100) is tracked via asset management, not ledger summary
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
            continue  # counted under stock account's cash_balance
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

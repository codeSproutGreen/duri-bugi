import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, JournalEntry, JournalLine, RawMessage, StockPerson, StockAccount, StockHolding, RealEstate, TagMemo
from app.schemas import DashboardOut, AccountBalance, MonthlyRow
from app.services.ledger import get_account_balance

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db)):
    accounts = db.query(Account).order_by(Account.code).all()

    totals = {"asset": 0, "liability": 0, "income": 0, "expense": 0}
    account_balances = []

    for acct in accounts:
        balance = get_account_balance(db, acct.id)
        # Skip deleted accounts with zero balance
        if acct.is_deleted and balance == 0:
            continue
        account_balances.append(AccountBalance(
            id=acct.id, code=acct.code, name=acct.name,
            type=acct.type, is_group=acct.is_group,
            parent_id=acct.parent_id, balance=balance,
        ))
        # Only non-group accounts contribute to totals (groups have no transactions)
        if acct.type in totals and not acct.is_group:
            totals[acct.type] += balance

    pending_count = db.query(func.count(JournalEntry.id)).filter(
        JournalEntry.is_confirmed == 0
    ).scalar() or 0

    # Stocks total (exclude linked account balances already counted in totals)
    stocks_total = 0
    for h in db.query(StockHolding).filter(StockHolding.quantity > 0).all():
        stocks_total += h.quantity * h.current_price
    # Add cash in stock accounts (예수금)
    linked_ids = {
        sa.linked_account_id
        for sa in db.query(StockAccount).filter(StockAccount.linked_account_id.isnot(None)).all()
    }
    stock_cash = sum(get_account_balance(db, lid) for lid in linked_ids)
    stocks_total += stock_cash

    # Real estate total
    realestate_total = db.query(func.coalesce(func.sum(RealEstate.value), 0)).scalar()

    total_asset_all = totals["asset"] + stocks_total + realestate_total
    # Subtract linked accounts already counted in totals["asset"] to avoid double counting
    total_asset_all -= stock_cash

    return DashboardOut(
        total_asset=total_asset_all,
        total_liability=totals["liability"],
        total_income=totals["income"],
        total_expense=totals["expense"],
        net_worth=total_asset_all - totals["liability"],
        stocks_total=stocks_total,
        realestate_total=realestate_total,
        accounts=account_balances,
        pending_count=pending_count,
    )


@router.get("/dashboard/pending-count")
def get_pending_count(db: Session = Depends(get_db)):
    count = db.query(func.count(JournalEntry.id)).filter(
        JournalEntry.is_confirmed == 0
    ).scalar() or 0
    return {"count": count}


@router.get("/dashboard/monthly", response_model=list[MonthlyRow])
def get_monthly(
    months: int = Query(6, le=24),
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Get monthly income and expense totals."""
    q = db.query(
        func.substr(JournalEntry.entry_date, 1, 7).label("month"),
        Account.type,
        func.sum(JournalLine.debit).label("total_debit"),
        func.sum(JournalLine.credit).label("total_credit"),
    ).join(JournalLine, JournalLine.entry_id == JournalEntry.id
    ).join(Account, Account.id == JournalLine.account_id
    ).filter(
        JournalEntry.is_confirmed == 1,
        Account.type.in_(["income", "expense"]),
        Account.is_group == 0,
    )
    if start:
        q = q.filter(JournalEntry.entry_date >= start)
    if end:
        q = q.filter(JournalEntry.entry_date <= end)
    rows = q.group_by("month", Account.type
    ).order_by(func.substr(JournalEntry.entry_date, 1, 7).desc()
    ).all()

    monthly = {}
    for row in rows:
        if row.month not in monthly:
            monthly[row.month] = {"income": 0, "expense": 0}
        if row.type == "income":
            monthly[row.month]["income"] += (row.total_credit or 0) - (row.total_debit or 0)
        elif row.type == "expense":
            monthly[row.month]["expense"] += (row.total_debit or 0) - (row.total_credit or 0)

    result = [
        MonthlyRow(month=m, income=v["income"], expense=v["expense"])
        for m, v in sorted(monthly.items(), reverse=True)
    ]
    if not start and not end:
        return result[:months]
    return result


@router.get("/dashboard/income-expense")
def get_income_expense(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Per-account expense and income totals for a date range."""
    rows = db.query(
        Account.id,
        Account.code,
        Account.name,
        Account.type,
        Account.parent_id,
        func.sum(JournalLine.debit).label("total_debit"),
        func.sum(JournalLine.credit).label("total_credit"),
    ).join(JournalLine, JournalLine.account_id == Account.id
    ).join(JournalEntry, JournalEntry.id == JournalLine.entry_id
    ).filter(
        JournalEntry.is_confirmed == 1,
        JournalEntry.entry_date >= start,
        JournalEntry.entry_date <= end,
        Account.type.in_(["income", "expense"]),
    ).group_by(Account.id).all()

    # Also get accounts with zero balance in range
    all_accts = db.query(Account).filter(
        Account.type.in_(["income", "expense"]),
    ).all()

    acct_totals = {}
    for row in rows:
        if row.type == "expense":
            amount = (row.total_debit or 0) - (row.total_credit or 0)
        else:  # income
            amount = (row.total_credit or 0) - (row.total_debit or 0)
        acct_totals[row.id] = amount

    result = {"expense": [], "income": []}
    for acct in all_accts:
        amount = acct_totals.get(acct.id, 0)
        if acct.is_deleted and amount == 0:
            continue
        result[acct.type].append({
            "id": acct.id,
            "code": acct.code,
            "name": acct.name,
            "parent_id": acct.parent_id,
            "is_group": acct.is_group,
            "amount": amount,
        })

    # Sort by code
    for t in result:
        result[t].sort(key=lambda a: a["code"])

    # Totals: sum only non-group (leaf) accounts to avoid double-counting
    result["total_expense"] = sum(a["amount"] for a in result["expense"] if not a["is_group"])
    result["total_income"] = sum(a["amount"] for a in result["income"] if not a["is_group"])
    result["net_income"] = result["total_income"] - result["total_expense"]

    return result


@router.get("/dashboard/trend")
def get_trend(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Daily cumulative asset and liability balances over a date range."""
    # Get all confirmed entries in range, grouped by date and account type
    rows = db.query(
        JournalEntry.entry_date,
        Account.type,
        func.sum(JournalLine.debit).label("total_debit"),
        func.sum(JournalLine.credit).label("total_credit"),
    ).join(JournalLine, JournalLine.entry_id == JournalEntry.id
    ).join(Account, Account.id == JournalLine.account_id
    ).filter(
        JournalEntry.is_confirmed == 1,
        JournalEntry.entry_date <= end,
        Account.type.in_(["asset", "liability"]),
        Account.is_group == 0,
    ).group_by(JournalEntry.entry_date, Account.type
    ).order_by(JournalEntry.entry_date).all()

    # Build cumulative daily balances
    daily = {}  # date -> {asset, liability}
    for row in rows:
        d = row.entry_date
        if d not in daily:
            daily[d] = {"asset": 0, "liability": 0}
        if row.type == "asset":
            daily[d]["asset"] += (row.total_debit or 0) - (row.total_credit or 0)
        elif row.type == "liability":
            daily[d]["liability"] += (row.total_credit or 0) - (row.total_debit or 0)

    # Fill in cumulative values and aggregate by month
    all_dates = sorted(daily.keys())
    if not all_dates:
        return []

    cum_asset = 0
    cum_liability = 0

    # Pre-accumulate everything before start
    for dd in all_dates:
        if dd < start:
            cum_asset += daily[dd]["asset"]
            cum_liability += daily[dd]["liability"]

    # Walk day by day, keep last value per month
    d = date.fromisoformat(max(start, all_dates[0]))
    end_date = date.fromisoformat(min(end, all_dates[-1]))
    monthly = {}  # "YYYY-MM" -> {date, asset, liability, net_worth}

    while d <= end_date:
        ds = d.isoformat()
        if ds in daily:
            cum_asset += daily[ds]["asset"]
            cum_liability += daily[ds]["liability"]
        month_key = ds[:7]  # "YYYY-MM"
        monthly[month_key] = {
            "date": ds,
            "asset": cum_asset,
            "liability": cum_liability,
            "net_worth": cum_asset - cum_liability,
        }
        d += timedelta(days=1)

    return list(monthly.values())


@router.get("/dashboard/tags")
def get_tags(
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Extract unique #tags from memo fields with aggregated amounts."""
    q = db.query(JournalEntry).filter(
        JournalEntry.is_confirmed == 1,
        JournalEntry.memo.like("%#%"),
    )
    if start:
        q = q.filter(JournalEntry.entry_date >= start)
    if end:
        q = q.filter(JournalEntry.entry_date <= end)

    tag_re = re.compile(r"#([^\s#,/]+)")
    tags: dict[str, dict] = {}

    for entry in q.all():
        found = tag_re.findall(entry.memo)
        if not found:
            continue
        amount = sum(l.debit for l in entry.lines)
        for tag in found:
            if tag not in tags:
                tags[tag] = {"tag": tag, "count": 0, "total": 0}
            tags[tag]["count"] += 1
            tags[tag]["total"] += amount

    result = sorted(tags.values(), key=lambda t: t["total"], reverse=True)
    return result


@router.get("/dashboard/tag-entries")
def get_tag_entries(
    tag: str = Query(...),
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Get entries that have a specific #tag in memo."""
    q = db.query(JournalEntry).filter(
        JournalEntry.is_confirmed == 1,
        JournalEntry.memo.like(f"%#{tag}%"),
    ).order_by(JournalEntry.entry_date.desc())
    if start:
        q = q.filter(JournalEntry.entry_date >= start)
    if end:
        q = q.filter(JournalEntry.entry_date <= end)

    from app.routers.transactions import _entry_to_out
    return [_entry_to_out(e) for e in q.all()]


@router.get("/dashboard/tag-memo")
def get_tag_memo(tag: str = Query(...), db: Session = Depends(get_db)):
    row = db.query(TagMemo).filter(TagMemo.tag == tag).first()
    return {"tag": tag, "memo": row.memo if row else ""}


@router.put("/dashboard/tag-memo")
def update_tag_memo(tag: str = Query(...), memo: str = Query(""), db: Session = Depends(get_db)):
    from datetime import datetime
    row = db.query(TagMemo).filter(TagMemo.tag == tag).first()
    if row:
        row.memo = memo
        row.updated_at = datetime.now().isoformat()
    else:
        db.add(TagMemo(tag=tag, memo=memo))
    db.commit()
    return {"tag": tag, "memo": memo}

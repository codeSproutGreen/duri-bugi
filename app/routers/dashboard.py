from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, JournalEntry, JournalLine, RawMessage
from app.schemas import DashboardOut, AccountBalance, MonthlyRow
from app.services.ledger import get_account_balance

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db)):
    accounts = db.query(Account).filter(Account.is_active == 1).order_by(Account.code).all()

    totals = {"asset": 0, "liability": 0, "income": 0, "expense": 0}
    account_balances = []

    for acct in accounts:
        balance = get_account_balance(db, acct.id)
        account_balances.append(AccountBalance(
            id=acct.id, code=acct.code, name=acct.name,
            type=acct.type, balance=balance,
        ))
        if acct.type in totals:
            totals[acct.type] += balance

    pending_count = db.query(func.count(JournalEntry.id)).filter(
        JournalEntry.is_confirmed == 0
    ).scalar() or 0

    return DashboardOut(
        total_asset=totals["asset"],
        total_liability=totals["liability"],
        total_income=totals["income"],
        total_expense=totals["expense"],
        net_worth=totals["asset"] - totals["liability"],
        accounts=account_balances,
        pending_count=pending_count,
    )


@router.get("/dashboard/monthly", response_model=list[MonthlyRow])
def get_monthly(
    months: int = Query(6, le=24),
    db: Session = Depends(get_db),
):
    """Get monthly income and expense totals."""
    # Income: credit side of income accounts on confirmed entries
    rows = db.query(
        func.substr(JournalEntry.entry_date, 1, 7).label("month"),
        Account.type,
        func.sum(JournalLine.debit).label("total_debit"),
        func.sum(JournalLine.credit).label("total_credit"),
    ).join(JournalLine, JournalLine.entry_id == JournalEntry.id
    ).join(Account, Account.id == JournalLine.account_id
    ).filter(
        JournalEntry.is_confirmed == 1,
        Account.type.in_(["income", "expense"]),
    ).group_by("month", Account.type
    ).order_by(func.substr(JournalEntry.entry_date, 1, 7).desc()
    ).limit(months * 2).all()

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
    return result[:months]

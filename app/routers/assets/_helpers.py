"""Shared helpers for asset routers."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Account, JournalEntry, JournalLine, StockAccount, StockHolding, StockPerson
from app.services.ledger import get_account_balance


def _holding_to_out(h: StockHolding) -> dict:
    mv = h.quantity * h.current_price
    cost = h.quantity * h.avg_price
    gl = mv - cost
    gl_pct = (gl / cost * 100) if cost else 0.0
    return {
        "id": h.id, "account_id": h.account_id,
        "ticker": h.ticker, "name": h.name, "exchange": h.exchange,
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

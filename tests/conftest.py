import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
# Import all models so Base.metadata knows all tables
from app.models import Account, JournalEntry, JournalLine, RawMessage, AuditLog, CategoryRule  # noqa: F401


@pytest.fixture
def db():
    """Fresh in-memory SQLite DB per test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_pragma(conn, _):
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db, monkeypatch):
    """TestClient with test DB override and PIN auth disabled."""
    from app.config import settings
    monkeypatch.setattr(settings, "app_pins", "")
    monkeypatch.setattr(settings, "app_pin", "")

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Seed helpers ──

def seed_account(db, code, name, acct_type, is_group=0, parent_id=None, is_deleted=0):
    """Create and return an account."""
    acct = Account(
        code=code, name=name, type=acct_type,
        is_group=is_group, parent_id=parent_id, is_deleted=is_deleted,
    )
    db.add(acct)
    db.flush()
    return acct


def seed_accounts(db):
    """Seed a minimal set of accounts. Returns dict of {name: Account}."""
    accts = {}
    accts["bank"] = seed_account(db, "1001", "신한은행", "asset")
    accts["card"] = seed_account(db, "2001", "KB국민카드", "liability")
    accts["equity"] = seed_account(db, "3001", "기초자본", "equity")
    accts["salary"] = seed_account(db, "4001", "급여", "income")
    accts["food"] = seed_account(db, "5001", "식비", "expense")
    accts["misc_expense"] = seed_account(db, "5006", "기타비용", "expense")
    accts["expense_group"] = seed_account(db, "5000", "비용그룹", "expense", is_group=1)
    db.commit()
    return accts


def seed_entry(db, debit_account_id, credit_account_id, amount, confirmed=1, description="test", entry_date="2026-03-16"):
    """Create a balanced journal entry with two lines."""
    entry = JournalEntry(
        entry_date=entry_date,
        description=description,
        is_confirmed=confirmed,
        source="web",
    )
    db.add(entry)
    db.flush()
    db.add(JournalLine(entry_id=entry.id, account_id=debit_account_id, debit=amount, credit=0))
    db.add(JournalLine(entry_id=entry.id, account_id=credit_account_id, debit=0, credit=amount))
    db.commit()
    return entry


def seed_raw_message(db, content="테스트 메시지", source_name="테스트", device_name=""):
    """Create a raw message."""
    msg = RawMessage(
        source_type="NOTIFICATION",
        source="com.test",
        source_name=source_name,
        device_name=device_name,
        title="",
        content=content,
        timestamp=1710568800000,
        status="pending",
    )
    db.add(msg)
    db.commit()
    return msg

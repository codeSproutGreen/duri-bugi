import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import engine, SessionLocal, Base
from app.models import Account
from app.routers import webhook, messages, transactions, accounts, dashboard, rules, auth
from app.routers.auth import verify_token, _pin_enabled

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


SEED_ACCOUNTS = [
    # 자산
    ("1001", "신한은행", "asset"),
    ("1002", "카카오뱅크", "asset"),
    ("1003", "토스", "asset"),
    ("1004", "현금", "asset"),
    # 부채
    ("2001", "KB국민카드", "liability"),
    ("2002", "하나카드", "liability"),
    ("2003", "신한카드", "liability"),
    # 자본
    ("3001", "기초자본", "equity"),
    # 수입
    ("4001", "급여", "income"),
    ("4002", "이자수입", "income"),
    ("4003", "기타수입", "income"),
    # 비용
    ("5001", "식비", "expense"),
    ("5002", "교통비", "expense"),
    ("5003", "통신비", "expense"),
    ("5004", "쇼핑", "expense"),
    ("5005", "의료비", "expense"),
    ("5006", "기타비용", "expense"),
]


def seed_accounts():
    db = SessionLocal()
    try:
        if db.query(Account).count() == 0:
            for code, name, acct_type in SEED_ACCOUNTS:
                db.add(Account(code=code, name=name, type=acct_type))
            db.commit()
            logging.info("Seeded %d default accounts", len(SEED_ACCOUNTS))
    finally:
        db.close()


OLD_TO_NEW_CODES = {
    "1010": "1001", "1020": "1002", "1030": "1003", "1040": "1004",
    "2010": "2001", "2020": "2002", "2030": "2003",
    "3010": "3001",
    "4010": "4001", "4020": "4002", "4030": "4003",
    "5010": "5001", "5020": "5002", "5030": "5003",
    "5040": "5004", "5050": "5005", "5060": "5006",
}


def migrate_db():
    """Add new columns to existing tables if missing."""
    from sqlalchemy import text, inspect
    with engine.connect() as conn:
        columns = [c["name"] for c in inspect(engine).get_columns("journal_entries")]
        if "source" not in columns:
            conn.execute(text("ALTER TABLE journal_entries ADD COLUMN source TEXT NOT NULL DEFAULT 'web'"))
            conn.commit()
        if "created_by" not in columns:
            conn.execute(text("ALTER TABLE journal_entries ADD COLUMN created_by TEXT NOT NULL DEFAULT ''"))
            conn.commit()

        # Add is_group column
        acct_columns = [c["name"] for c in inspect(engine).get_columns("accounts")]
        if "is_group" not in acct_columns:
            conn.execute(text("ALTER TABLE accounts ADD COLUMN is_group INTEGER NOT NULL DEFAULT 0"))
            # Auto-detect: accounts that have children become groups
            conn.execute(text(
                "UPDATE accounts SET is_group = 1 "
                "WHERE id IN (SELECT DISTINCT parent_id FROM accounts WHERE parent_id IS NOT NULL) "
                "AND id NOT IN (SELECT DISTINCT account_id FROM journal_lines)"
            ))
            conn.commit()
            logging.info("Added is_group column and auto-detected group accounts")

        # Add is_deleted column to accounts
        if "is_deleted" not in acct_columns:
            conn.execute(text("ALTER TABLE accounts ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0"))
            conn.commit()
            logging.info("Added is_deleted column to accounts")

        # Add sort_order column to accounts
        acct_columns = [c["name"] for c in inspect(engine).get_columns("accounts")]
        if "sort_order" not in acct_columns:
            conn.execute(text("ALTER TABLE accounts ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"))
            # Initialize sort_order from code order
            conn.execute(text(
                "UPDATE accounts SET sort_order = ("
                "  SELECT COUNT(*) FROM accounts a2 "
                "  WHERE a2.type = accounts.type AND a2.code < accounts.code"
                ")"
            ))
            conn.commit()
            logging.info("Added sort_order column to accounts")

        # Migrate old account codes to new format
        row = conn.execute(text("SELECT code FROM accounts WHERE code = '1010' LIMIT 1")).fetchone()
        if row:
            for old, new in OLD_TO_NEW_CODES.items():
                conn.execute(text("UPDATE accounts SET code = :new WHERE code = :old"), {"old": old, "new": new})
            # Clear all journal entries/lines (user confirmed no important data)
            conn.execute(text("DELETE FROM journal_lines"))
            conn.execute(text("DELETE FROM journal_entries"))
            conn.commit()
            logging.info("Migrated account codes to new format")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_db()
    seed_accounts()
    yield


app = FastAPI(title="NotiLedger", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# PIN auth middleware
class PinAuthMiddleware(BaseHTTPMiddleware):
    OPEN_PATHS = {"/api/auth/check", "/api/auth/login", "/api/auth/logout"}

    async def dispatch(self, request: Request, call_next):
        # Skip if PIN not configured
        if not _pin_enabled():
            return await call_next(request)
        # Allow auth endpoints, static files, and webhook (from Android app)
        path = request.url.path
        if (
            path in self.OPEN_PATHS
            or not path.startswith("/api")
            or path == "/api/webhook"
        ):
            return await call_next(request)
        # Check session cookie
        token = request.cookies.get("noti_session")
        valid, _ = verify_token(token)
        if not valid:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)


app.add_middleware(PinAuthMiddleware)

app.include_router(auth.router)
app.include_router(webhook.router)
app.include_router(messages.router)
app.include_router(transactions.router)
app.include_router(accounts.router)
app.include_router(dashboard.router)
app.include_router(rules.router)

# Serve frontend
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

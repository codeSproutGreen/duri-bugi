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
    ("1010", "신한은행", "asset"),
    ("1020", "카카오뱅크", "asset"),
    ("1030", "토스", "asset"),
    ("1040", "현금", "asset"),
    # 부채
    ("2010", "KB국민카드", "liability"),
    ("2020", "하나카드", "liability"),
    ("2030", "신한카드", "liability"),
    # 자본
    ("3010", "기초자본", "equity"),
    # 수입
    ("4010", "급여", "income"),
    ("4020", "이자수입", "income"),
    ("4030", "기타수입", "income"),
    # 비용
    ("5010", "식비", "expense"),
    ("5020", "교통비", "expense"),
    ("5030", "통신비", "expense"),
    ("5040", "쇼핑", "expense"),
    ("5050", "의료비", "expense"),
    ("5060", "기타비용", "expense"),
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

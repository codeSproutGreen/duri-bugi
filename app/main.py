import logging
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
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


def run_migrations():
    """Run Alembic migrations programmatically."""
    from sqlalchemy import inspect as sa_inspect, text
    alembic_ini = Path(__file__).parent.parent / "alembic.ini"
    if alembic_ini.exists():
        alembic_cfg = Config(str(alembic_ini))
        inspector = sa_inspect(engine)
        has_tables = inspector.has_table("accounts")
        has_alembic = inspector.has_table("alembic_version")
        # Check if alembic_version exists but is empty (from previous failed runs)
        alembic_stamped = False
        if has_alembic:
            with engine.connect() as conn:
                row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
                alembic_stamped = row is not None
        if has_tables and not alembic_stamped:
            # Existing DB without valid alembic stamp → stamp to head
            command.stamp(alembic_cfg, "head")
            logging.info("Stamped existing DB to current alembic revision")
        else:
            command.upgrade(alembic_cfg, "head")
            logging.info("Alembic migrations applied")
    else:
        # Fallback: create tables directly (e.g. Docker without alembic.ini)
        Base.metadata.create_all(bind=engine)
        logging.info("Tables created directly (no alembic.ini found)")


def _setup_logging():
    """Ensure app loggers output to stdout for docker logs."""
    import sys
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    # Always add a direct StreamHandler to stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
    app_logger.addHandler(handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    run_migrations()
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

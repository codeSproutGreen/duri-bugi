import hashlib
import hmac
import time
import logging
from collections import defaultdict

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger(__name__)

# Rate limiting: track failed attempts per IP
_fail_attempts: dict[str, list[float]] = defaultdict(list)
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60  # 15 minutes


class PinRequest(BaseModel):
    pin: str


def _make_token(timestamp: int) -> str:
    """Create HMAC-signed session token."""
    msg = f"noti-session:{timestamp}"
    sig = hmac.new(
        settings.session_secret.encode(), msg.encode(), hashlib.sha256
    ).hexdigest()
    return f"{timestamp}:{sig}"


def verify_token(token: str) -> bool:
    """Verify a session token is valid and not expired (7 days)."""
    if not token:
        return False
    try:
        ts_str, sig = token.split(":", 1)
        ts = int(ts_str)
    except (ValueError, AttributeError):
        return False
    # Check expiry (7 days)
    if time.time() - ts > 7 * 24 * 3600:
        return False
    expected = _make_token(ts)
    return hmac.compare_digest(token, expected)


def _check_rate_limit(ip: str) -> bool:
    """Return True if IP is rate-limited."""
    now = time.time()
    # Clean old entries
    _fail_attempts[ip] = [t for t in _fail_attempts[ip] if now - t < LOCKOUT_SECONDS]
    return len(_fail_attempts[ip]) >= MAX_ATTEMPTS


def _record_failure(ip: str):
    _fail_attempts[ip].append(time.time())


@router.get("/check")
async def check_auth(request: Request):
    """Check if current session is authenticated."""
    if not settings.app_pin:
        return {"authenticated": True, "pin_required": False}
    token = request.cookies.get("noti_session")
    return {
        "authenticated": verify_token(token),
        "pin_required": True,
    }


@router.post("/login")
async def login(body: PinRequest, request: Request, response: Response):
    """Verify PIN and set session cookie."""
    ip = request.client.host if request.client else "unknown"

    if _check_rate_limit(ip):
        remaining = LOCKOUT_SECONDS
        attempts = _fail_attempts.get(ip, [])
        if attempts:
            remaining = int(LOCKOUT_SECONDS - (time.time() - attempts[0]))
        log.warning("Rate limited IP: %s", ip)
        return {
            "success": False,
            "error": f"Too many attempts. Try again in {remaining // 60} minutes.",
            "locked": True,
        }

    if not settings.app_pin:
        return {"success": True}

    # Compare PIN (constant-time)
    if not hmac.compare_digest(body.pin, settings.app_pin):
        _record_failure(ip)
        remaining = MAX_ATTEMPTS - len(_fail_attempts[ip])
        log.warning("Failed PIN attempt from %s (%d remaining)", ip, remaining)
        return {
            "success": False,
            "error": f"Wrong PIN. {remaining} attempts remaining.",
            "locked": False,
        }

    # Success - clear failures and set cookie
    _fail_attempts.pop(ip, None)
    token = _make_token(int(time.time()))
    response.set_cookie(
        key="noti_session",
        value=token,
        max_age=7 * 24 * 3600,  # 7 days
        httponly=True,
        samesite="lax",
    )
    return {"success": True}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("noti_session")
    return {"success": True}

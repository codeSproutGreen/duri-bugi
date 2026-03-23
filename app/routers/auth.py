import base64
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


def _get_pin_map() -> dict[str, str]:
    """Parse PIN→username mapping from settings.
    APP_PINS format: '1234:아내,5678:남편'
    Falls back to APP_PIN (single user, no name).
    """
    pin_map = {}
    if settings.app_pins:
        for pair in settings.app_pins.split(","):
            pair = pair.strip()
            if ":" in pair:
                pin, name = pair.split(":", 1)
                pin_map[pin.strip()] = name.strip()
    elif settings.app_pin:
        pin_map[settings.app_pin] = ""
    return pin_map


def _encode_username(username: str) -> str:
    """Base64url-encode username for cookie safety."""
    return base64.urlsafe_b64encode(username.encode()).decode()


def _decode_username(encoded: str) -> str:
    """Decode base64url-encoded username."""
    try:
        return base64.urlsafe_b64decode(encoded.encode()).decode()
    except Exception:
        return ""


def _make_token(timestamp: int, username: str = "") -> str:
    """Create HMAC-signed session token with embedded username."""
    encoded_name = _encode_username(username)
    msg = f"noti-session:{timestamp}:{encoded_name}"
    sig = hmac.new(
        settings.session_secret.encode(), msg.encode(), hashlib.sha256
    ).hexdigest()
    return f"{timestamp}:{encoded_name}:{sig}"


def verify_token(token: str) -> tuple[bool, str]:
    """Verify a session token. Returns (valid, username)."""
    if not token:
        return False, ""
    try:
        parts = token.split(":", 2)
        if len(parts) == 3:
            ts_str, encoded_name, sig = parts
        else:
            # Legacy 2-part token
            ts_str, sig = parts[0], parts[1]
            encoded_name = ""
        ts = int(ts_str)
    except (ValueError, AttributeError):
        return False, ""
    # Check expiry
    if time.time() - ts > settings.session_days * 24 * 3600:
        return False, ""
    username = _decode_username(encoded_name)
    expected = _make_token(ts, username)
    if hmac.compare_digest(token, expected):
        return True, username
    return False, ""


def get_current_user(request: Request) -> str:
    """Extract username from session cookie."""
    token = request.cookies.get("noti_session")
    valid, username = verify_token(token)
    return username if valid else ""


def _check_rate_limit(ip: str) -> bool:
    """Return True if IP is rate-limited."""
    now = time.time()
    _fail_attempts[ip] = [t for t in _fail_attempts[ip] if now - t < LOCKOUT_SECONDS]
    return len(_fail_attempts[ip]) >= MAX_ATTEMPTS


def _record_failure(ip: str):
    _fail_attempts[ip].append(time.time())


def _pin_enabled() -> bool:
    return bool(settings.app_pins or settings.app_pin)


@router.get("/check")
async def check_auth(request: Request):
    """Check if current session is authenticated."""
    if not _pin_enabled():
        return {"authenticated": True, "pin_required": False, "user": ""}
    token = request.cookies.get("noti_session")
    valid, username = verify_token(token)
    return {
        "authenticated": valid,
        "pin_required": True,
        "user": username if valid else "",
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

    pin_map = _get_pin_map()
    if not pin_map:
        return {"success": True, "user": ""}

    # Check against all registered PINs (constant-time per check, use bytes for unicode safety)
    matched_user = None
    for registered_pin, username in pin_map.items():
        if hmac.compare_digest(body.pin.encode(), registered_pin.encode()):
            matched_user = username
            break

    if matched_user is None:
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
    token = _make_token(int(time.time()), matched_user)
    response.set_cookie(
        key="noti_session",
        value=token,
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        samesite="lax",
    )
    return {"success": True, "user": matched_user}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("noti_session")
    return {"success": True}

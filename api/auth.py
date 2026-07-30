"""احراز هویت امن Telegram Mini App با HMAC-SHA256."""
import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException

from database import db


BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
except (TypeError, ValueError):
    ADMIN_ID = 0

INIT_DATA_MAX_AGE = 3600


def _auth_error(detail: str = "invalid_init_data") -> HTTPException:
    return HTTPException(status_code=401, detail=detail)


def verify_telegram_init_data(init_data: str) -> dict:
    """Validate Telegram WebApp initData and return its user object.

    Telegram signs the decoded query-string values.  ``parse_qsl`` is used
    instead of manually splitting the string so encoded characters and plus
    signs are handled correctly.  No user-provided id is trusted before the
    signature has been verified.
    """
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not set")
    if not isinstance(init_data, str) or not init_data.strip():
        raise _auth_error("missing_init_data")

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        parsed = dict(pairs)
    except (TypeError, ValueError):
        raise _auth_error()

    received_hash = parsed.pop("hash", "")
    if not received_hash or len(received_hash) != 64:
        raise _auth_error()

    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except (TypeError, ValueError):
        raise _auth_error()

    now = int(time.time())
    if auth_date <= 0 or auth_date > now + 60 or now - auth_date > INIT_DATA_MAX_AGE:
        raise _auth_error("init_data_expired")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(parsed.items())
    )
    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256
    ).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise _auth_error()

    try:
        user = json.loads(parsed.get("user", "{}"))
    except (TypeError, json.JSONDecodeError):
        raise _auth_error("invalid_user_data")
    if not isinstance(user, dict) or not user.get("id"):
        raise _auth_error("invalid_user_data")
    return user


async def get_current_user(
    x_init_data: str = Header(default="", alias="X-Init-Data"),
) -> dict:
    tg_user = verify_telegram_init_data(x_init_data)
    try:
        uid = int(tg_user["id"])
    except (KeyError, TypeError, ValueError):
        raise _auth_error("invalid_user_data")

    db_user = await db.get_user(uid)
    if not db_user:
        raise HTTPException(status_code=403, detail="not_registered")
    if not db_user.get("approved"):
        raise HTTPException(status_code=403, detail="pending_approval")
    if db_user.get("suspended"):
        raise HTTPException(status_code=403, detail="suspended")
    return {**tg_user, "id": uid, "_db": db_user}


async def get_admin_user(user=Depends(get_current_user)) -> dict:
    if user["id"] != ADMIN_ID:
        raise HTTPException(status_code=403, detail="admin_only")
    return user


async def get_content_admin_user(user=Depends(get_current_user)) -> dict:
    role = user["_db"].get("role", "student")
    if user["id"] != ADMIN_ID and role not in ("admin", "content_admin"):
        raise HTTPException(status_code=403, detail="content_admin_only")
    return user


async def get_resource_access_user(user=Depends(get_current_user)) -> dict:
    """گیت اشتراک برای «منابع علوم پایه» و «رفرنس‌ها».

    دقیقاً همان قانونِ واحد ربات (subscription.has_access) اجرا می‌شود:
    کلید سراسری subscription_enforced → بای‌پس مدیر اصلی → db.sub_is_active.
    بدون این گیت، مینی‌اپ محتوای قفلِ ربات را آزاد سرو می‌کرد؛ بک‌اند
    مرجع نهایی است و فرانت فقط UI قفل را نشان می‌دهد.
    """
    # import تنبل — گرفتن has_access از ماژول ربات بدون کشیدن وابستگی‌های
    # تلگرام به گرافِ بوت FastAPI و بدون دوباره‌نویسی منطق
    from subscription import has_access

    if not await has_access(user["id"]):
        raise HTTPException(status_code=403, detail="subscription_required")
    return user


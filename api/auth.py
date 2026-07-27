"""🔐 احراز هویت HMAC تلگرام"""
import os, hmac, hashlib, json, time
from urllib.parse import unquote
from fastapi import Header, HTTPException, Depends
from database import db

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))

def verify_telegram_init_data(init_data: str) -> dict:
    if not BOT_TOKEN: raise HTTPException(500, "BOT_TOKEN not set")
    if not init_data: raise HTTPException(401, "Missing init data")
    parsed = {}
    for part in init_data.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            parsed[k] = unquote(v)
    received_hash = parsed.pop("hash", "")
    if not received_hash: raise HTTPException(401, "Missing hash")
    if time.time() - int(parsed.get("auth_date", 0)) > 3600:
        raise HTTPException(401, "initData expired")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed   = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        raise HTTPException(401, "Invalid signature")
    try:
        return json.loads(parsed.get("user", "{}"))
    except Exception:
        raise HTTPException(401, "Invalid user data")

async def get_current_user(x_init_data: str = Header(..., alias="X-Init-Data")) -> dict:
    tg_user = verify_telegram_init_data(x_init_data)
    uid = tg_user.get("id")
    if not uid: raise HTTPException(401, "User ID missing")
    db_user = await db.get_user(uid)
    if not db_user: raise HTTPException(403, detail="not_registered")
    if not db_user.get("approved"): raise HTTPException(403, detail="pending_approval")
    if db_user.get("suspended"): raise HTTPException(403, detail="suspended")
    return {**tg_user, "_db": db_user}

async def get_admin_user(user=Depends(get_current_user)) -> dict:
    if user["id"] != ADMIN_ID: raise HTTPException(403, "Admin only")
    return user

async def get_content_admin_user(user=Depends(get_current_user)) -> dict:
    role = user["_db"].get("role", "student")
    if user["id"] != ADMIN_ID and role not in ("admin", "content_admin"):
        raise HTTPException(403, "Content admin only")
    return user

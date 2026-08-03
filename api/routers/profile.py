"""User profile endpoints for the Telegram Mini App."""
import asyncio
from typing import Any, List, Mapping

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import ADMIN_ID, get_current_user
from api.user_metrics import non_negative_int, normalize_stats, normalize_weekly
from database import db

router = APIRouter()
_VALID_ROLES = {"student", "content_admin", "support", "admin"}


def _text(value: Any, default: str = "") -> str:
    return str(value).strip() if value is not None else default


def _role_for(uid: int, db_user: Mapping[str, Any]) -> str:
    if uid == ADMIN_ID:
        return "admin"
    role = _text(db_user.get("role"), "student")
    return role if role in _VALID_ROLES else "student"


@router.get("")
async def get_profile(user=Depends(get_current_user)):
    uid = user["id"]
    db_user = user["_db"] if isinstance(user.get("_db"), Mapping) else {}
    raw_stats, weekly, raw_tickets = await asyncio.gather(
        db.user_stats(uid),
        db.weekly_activity(uid),
        db.ticket_get_user(uid),
    )

    stats = normalize_stats(raw_stats)
    stats["weekly_chart"] = normalize_weekly(weekly)
    tickets = raw_tickets if isinstance(raw_tickets, list) else []

    return {
        "user": {
            "name": _text(db_user.get("name")),
            "intake": _text(db_user.get("intake")),
            "group": _text(db_user.get("group")),
            "student_id": _text(db_user.get("student_id")),
            "role": _role_for(uid, db_user),
            "telegram_id": uid,
        },
        "stats": stats,
        "tickets": {
            "open": sum(
                1
                for ticket in tickets
                if isinstance(ticket, Mapping) and ticket.get("status") == "open"
            ),
            "closed": sum(
                1
                for ticket in tickets
                if isinstance(ticket, Mapping) and ticket.get("status") == "closed"
            ),
        },
    }


class NameUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.patch("/name")
async def update_name(body: NameUpdate, user=Depends(get_current_user)):
    name = " ".join(body.name.split())
    if len(name) < 3 or len(name) > 50 or "<" in name or ">" in name:
        raise HTTPException(status_code=422, detail="نام نامعتبر")
    await db.update_user(user["id"], {"name": name})
    return {"ok": True, "name": name}


class GroupUpdate(BaseModel):
    group: str = Field(pattern=r"^[12]$")


@router.patch("/group")
async def update_group(body: GroupUpdate, user=Depends(get_current_user)):
    await db.update_user(user["id"], {"group": body.group})
    return {"ok": True, "group": body.group}


class IntakeUpdate(BaseModel):
    intake: str = Field(min_length=1, max_length=50)


@router.patch("/intake")
async def update_intake(body: IntakeUpdate, user=Depends(get_current_user)):
    intake = body.intake.strip()
    active = await db.get_active_intakes()
    active_codes = {
        _text(item.get("code"))
        for item in (active if isinstance(active, list) else [])
        if isinstance(item, Mapping) and _text(item.get("code"))
    }
    if not intake or intake not in active_codes:
        raise HTTPException(status_code=422, detail="ورودی نامعتبر")
    await db.update_user(user["id"], {"intake": intake})
    return {"ok": True, "intake": intake}


class StudentIdUpdate(BaseModel):
    student_id: str = Field(min_length=3, max_length=20)


@router.patch("/student-id")
async def update_student_id(
    body: StudentIdUpdate, user=Depends(get_current_user)
):
    student_id = body.student_id.strip()
    if not student_id.isdigit():
        raise HTTPException(status_code=422, detail="شماره دانشجویی باید عدد باشد")
    await db.update_user(user["id"], {"student_id": student_id})
    return {"ok": True, "student_id": student_id}


@router.get("/rank")
async def get_rank(user=Depends(get_current_user)):
    uid = user["id"]
    db_user = user["_db"] if isinstance(user.get("_db"), Mapping) else {}
    if non_negative_int(db_user.get("total_answers")) == 0:
        return {"rank": None, "total_users": 0, "percentile": 0}

    my_correct = non_negative_int(db_user.get("correct_answers"))
    query = {"approved": True, "total_answers": {"$gt": 0}}
    better, total = await asyncio.gather(
        db.users.count_documents({**query, "correct_answers": {"$gt": my_correct}}),
        db.users.count_documents(query),
    )
    total = non_negative_int(total)
    better = min(non_negative_int(better), total)
    return {
        "rank": better + 1 if total else None,
        "total_users": total,
        "percentile": round((1 - better / total) * 100) if total else 0,
    }


@router.get("/prestige")
async def get_prestige(user=Depends(get_current_user)):
    """👑 وضعیت کامل Prestige (موج P0) — افزایشی؛ منبع یکتا db.prestige_state."""
    state = await db.prestige_state(user["id"])
    return {"prestige": state}


@router.get("/prestige/badges")
async def get_prestige_badges(user=Depends(get_current_user)):
    """👑 P1 — کلکسیون کامل نشان‌ها (۵ تکاملی + تکی‌ها + جهانی‌ها)"""
    data = await db.prestige_badges(user["id"])
    if data is None:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
    return {"badges": data}


@router.get("/prestige/history")
async def get_prestige_history(
    limit: int = 30,
    user=Depends(get_current_user),
):
    """👑 P1 — «سفر من»: تایم‌لاین رویدادهای پرستیژ با تاریخ جلالی"""
    limit = max(1, min(int(limit), 100))
    items = await db.prestige_history_list(user["id"], limit)
    return {"items": items}


class ShowcaseInput(BaseModel):
    keys: List[str] = []


@router.put("/prestige/showcase")
async def put_prestige_showcase(
    body: ShowcaseInput,
    user=Depends(get_current_user),
):
    """👑 P1 — پین حداکثر ۳ نشان بازشده (اعتبارسنجی سروری)"""
    keys = [str(k)[:60] for k in (body.keys or [])][:10]
    return await db.prestige_showcase_set(user["id"], keys)


class PrivacyInput(BaseModel):
    public: bool


@router.patch("/prestige/privacy")
async def patch_prestige_privacy(
    body: PrivacyInput,
    user=Depends(get_current_user),
):
    """👑 P2 — کلید پوشش عمومی (پیش‌فرض روشن؛ نام در لیدربرد/فید ماسک می‌شود)"""
    await db.users.update_one(
        {"user_id": user["id"]},
        {"$set": {"privacy_public": bool(body.public)}},
    )
    return {"ok": True, "privacy_public": bool(body.public)}


@router.get("/prestige/public/{target_uid}")
async def get_prestige_public(
    target_uid: int,
    user=Depends(get_current_user),
):
    """👑 P2 — Hero Card عمومی: رنک/Top٪/شوکیس/رکوردها — بدون آمار حساس"""
    try:
        tid = int(target_uid)
    except Exception:
        raise HTTPException(status_code=422, detail="شناسه‌ی نامعتبر")
    data = await db.prestige_public(tid)
    if not data.get("ok"):
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
    return data


@router.get("/intakes")
async def get_intakes(user=Depends(get_current_user)):
    items = await db.get_active_intakes()
    result = []
    seen = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, Mapping):
            continue
        code = _text(item.get("code"))
        if not code or code in seen:
            continue
        seen.add(code)
        result.append(
            {"code": code, "label": _text(item.get("label"), code) or code}
        )
    return {"intakes": result}


@router.get("/badges")
async def get_badges(user=Depends(get_current_user)):
    stats = normalize_stats(await db.user_stats(user["id"]))
    total = stats["total_answers"]
    percentage = stats["percentage"]
    downloads = stats["downloads"]

    earned = set()
    if total >= 1:
        earned.add("first")
    if total >= 50:
        earned.add("fifty")
    if total >= 200:
        earned.add("two_hundred")
    if percentage >= 70:
        earned.add("seventy")
    if percentage >= 90:
        earned.add("ninety")
    if downloads >= 10:
        earned.add("downloader")

    return {
        "badges": [
            {"id": "first", "title": "اولین قدم", "icon": "🌱", "earned": "first" in earned},
            {"id": "fifty", "title": "۵۰ سوال", "icon": "🧪", "earned": "fifty" in earned},
            {"id": "two_hundred", "title": "۲۰۰ سوال", "icon": "🏆", "earned": "two_hundred" in earned},
            {"id": "seventy", "title": "۷۰٪ موفق", "icon": "⭐", "earned": "seventy" in earned},
            {"id": "ninety", "title": "۹۰٪ موفق", "icon": "🥇", "earned": "ninety" in earned},
            {"id": "downloader", "title": "خواننده", "icon": "📚", "earned": "downloader" in earned},
        ]
    }

# ══════════════════════════════════════════════
# 💙 حمایت مالی — خواندن زنده همان تنظیماتی که
# ربات برای دکمه «💙 حمایت مالی» استفاده می‌کند
# ══════════════════════════════════════════════

@router.get("/donation")
async def donation_config(user=Depends(get_current_user)):
    """تنظیمات حمایت مالی برای مینی‌اپ.

    دقیقاً همان کلیدهایی که message_router.py ربات مصرف می‌کند
    (donation_enabled + donation_link) — پس فعال‌سازی/تغییر لینک
    از سمت بات بلافاصله در مینی‌اپ هم اعمال می‌شود (سینک کامل).
    """
    enabled = bool(await db.get_setting("donation_enabled", False))
    link = (await db.get_setting("donation_link", None)) or ""
    return {"enabled": enabled and bool(link), "link": link}

"""Dashboard endpoints for the Telegram Mini App."""
import asyncio
from datetime import date
from typing import Any, Mapping

from fastapi import APIRouter, Depends

from api.auth import ADMIN_ID, get_current_user
from api.user_metrics import (
    non_negative_int,
    normalize_stats,
    normalize_weekly,
    same_user_id,
)
from database import db
from utils import now_tehran

router = APIRouter()


def _text(value: Any, default: str = "") -> str:
    return str(value).strip() if value is not None else default


def _exam_item(exam: Mapping[str, Any], today: date) -> dict:
    raw_date = _text(exam.get("date"))
    try:
        days_left = max(0, (date.fromisoformat(raw_date) - today).days)
    except (TypeError, ValueError):
        days_left = None

    return {
        "id": _text(exam.get("_id")),
        "lesson": _text(exam.get("lesson")),
        "date": raw_date,
        "time": _text(exam.get("time")),
        "days_left": days_left,
    }


@router.get("")
async def get_dashboard(user=Depends(get_current_user)):
    uid = user["id"]
    db_user = user["_db"] if isinstance(user.get("_db"), Mapping) else {}
    group = _text(db_user.get("group"))

    raw_stats, raw_exams, raw_tickets = await asyncio.gather(
        db.user_stats(uid),
        db.upcoming_exams(7, group=group),
        db.ticket_get_user(uid),
    )

    stats = normalize_stats(raw_stats)
    stats["weak_topics"] = stats["weak_topics"][:3]
    exams = raw_exams if isinstance(raw_exams, list) else []
    tickets = raw_tickets if isinstance(raw_tickets, list) else []
    role = "admin" if uid == ADMIN_ID else _text(db_user.get("role"), "student")

    return {
        "user": {
            "name": _text(db_user.get("name")),
            "intake": _text(db_user.get("intake")),
            "group": group,
            "role": role or "student",
        },
        "stats": stats,
        "upcoming_exams": [
            _exam_item(exam, now_tehran().date())
            for exam in exams[:3]
            if isinstance(exam, Mapping)
        ],
        "open_tickets": sum(
            1
            for ticket in tickets
            if isinstance(ticket, Mapping) and ticket.get("status") == "open"
        ),
    }


@router.get("/weekly")
async def weekly(user=Depends(get_current_user)):
    data = await db.weekly_activity(user["id"])
    return {"weekly": normalize_weekly(data)}


@router.get("/leaderboard")
async def leaderboard(user=Depends(get_current_user)):
    leaders = await db.get_leaderboard(10)
    uid = user["id"]
    result = []

    for item in leaders if isinstance(leaders, list) else []:
        if not isinstance(item, Mapping):
            continue
        total = non_negative_int(item.get("total_answers"))
        correct = non_negative_int(item.get("correct_answers"))
        percent = round(correct / total * 100) if total else 0
        result.append(
            {
                "rank": len(result) + 1,
                "name": _text(item.get("name"), "کاربر") or "کاربر",
                "correct": correct,
                "total": total,
                "percent": min(100, percent),
                "is_me": same_user_id(item.get("user_id"), uid),
            }
        )

    return {"leaderboard": result}

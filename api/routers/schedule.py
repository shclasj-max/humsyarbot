"""Class and exam schedule endpoints."""
from datetime import date
from typing import Any, Mapping

from fastapi import APIRouter, Depends, Query

from api.auth import get_current_user
from database import db
from utils import now_tehran

router = APIRouter()


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _format_schedule(item: Mapping[str, Any] | None) -> dict | None:
    if not isinstance(item, Mapping):
        return None

    document = {
        "id": _text(item.get("_id")),
        "type": _text(item.get("type")),
        "lesson": _text(item.get("lesson")),
        "teacher": _text(item.get("teacher")),
        "date": _text(item.get("date")),
        "time": _text(item.get("time")),
        "note": _text(item.get("note")),
        "group": _text(item.get("group")),
    }
    if document["type"] == "exam" and document["date"]:
        try:
            exam_date = date.fromisoformat(document["date"])
            document["days_left"] = max(
                0, (exam_date - now_tehran().date()).days
            )
        except (TypeError, ValueError):
            document["days_left"] = None
    return document


@router.get("")
async def get_schedule(
    user=Depends(get_current_user), stype: str | None = Query(default=None)
):
    group = _text(user["_db"].get("group"))
    items = await db.get_schedules(stype=stype, upcoming=True, group=group)
    return {
        "schedule": [
            formatted
            for item in (items if isinstance(items, list) else [])
            if (formatted := _format_schedule(item)) is not None
        ],
        "group": group,
    }


@router.get("/exams")
async def get_exams(
    user=Depends(get_current_user),
    days: int = Query(default=30, ge=1, le=365),
):
    group = _text(user["_db"].get("group"))
    exams = await db.upcoming_exams(days, group=group)
    return {
        "exams": [
            formatted
            for exam in (exams if isinstance(exams, list) else [])
            if (formatted := _format_schedule(exam)) is not None
        ]
    }

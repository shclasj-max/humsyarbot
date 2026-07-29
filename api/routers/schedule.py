"""Class and exam schedule endpoints."""

from datetime import date
from typing import Any, Literal, Mapping

from fastapi import APIRouter, Depends, Query

from api.auth import get_current_user
from database import db
from utils import now_tehran


router = APIRouter()

ScheduleType = Literal[
    "class",
    "exam",
    "makeup",
]


def _text(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _format_schedule(
    item: Mapping[str, Any] | None,
) -> dict | None:
    if not isinstance(item, Mapping):
        return None

    schedule_type = _text(
        item.get("type")
    )

    raw_date = _text(
        item.get("date")
    )

    document = {
        "id": _text(
            item.get("_id")
        ),

        "type": schedule_type,

        "lesson": _text(
            item.get("lesson")
        ),

        "teacher": _text(
            item.get("teacher")
        ),

        "date": raw_date,

        "time": _text(
            item.get("time")
        ),

        "location": _text(
            item.get("location")
        ),

        # رکوردهای جدید از notes و بعضی
        # رکوردهای قدیمی از note استفاده می‌کنند.
        "note": _text(
            item.get("notes")
            or item.get("note")
        ),

        "group": _text(
            item.get("group")
        ),

        "flex_type": (
            _text(
                item.get("flex_type")
            )
            or "fixed"
        ),

        "flex_note": _text(
            item.get("flex_note")
        ),

        "days_left": None,
    }

    if (
        schedule_type == "exam"
        and raw_date
    ):
        try:
            exam_date = date.fromisoformat(
                raw_date
            )

            document["days_left"] = max(
                0,
                (
                    exam_date
                    - now_tehran().date()
                ).days,
            )

        except (
            TypeError,
            ValueError,
        ):
            document["days_left"] = None

    return document


def _serialize(
    items: Any,
) -> list[dict]:
    result = []

    if not isinstance(items, list):
        return result

    for item in items:
        formatted = _format_schedule(
            item
        )

        if formatted is not None:
            result.append(formatted)

    return result


@router.get("")
async def get_schedule(
    user=Depends(get_current_user),

    stype: ScheduleType | None = Query(
        default=None
    ),
):
    group = _text(
        user["_db"].get("group")
    )

    items = await db.get_schedules(
        stype=stype,
        upcoming=True,
        group=group,
    )

    return {
        "schedule": _serialize(items),
        "group": group,
    }


@router.get("/exams")
async def get_exams(
    user=Depends(get_current_user),

    days: int = Query(
        default=30,
        ge=1,
        le=365,
    ),
):
    group = _text(
        user["_db"].get("group")
    )

    exams = await db.upcoming_exams(
        days,
        group=group,
    )

    return {
        "exams": _serialize(exams),
    }

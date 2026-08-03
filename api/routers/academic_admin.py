"""Secure schedule and grade management endpoints."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Literal

from bson import ObjectId
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from pydantic import BaseModel, Field

from api.auth import get_content_admin_user
from database import db
from grade_utils import normalize_grade


router = APIRouter()

ScheduleType = Literal[
    "class",
    "exam",
    "makeup",
]

ScheduleGroup = Literal[
    "1",
    "2",
    "هر دو",
]

FlexType = Literal[
    "fixed",
    "flexible",
]


def _clean(
    value,
    max_length: int = 200,
) -> str:
    text = " ".join(
        str(value or "").split()
    )

    return text[:max_length]


def _valid_date(
    value: str,
) -> str:
    try:
        datetime.strptime(
            value,
            "%Y-%m-%d",
        )

    except (
        TypeError,
        ValueError,
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "تاریخ باید با فرمت "
                "YYYY-MM-DD باشد"
            ),
        )

    return value


def _valid_time(
    value: str,
) -> str:
    value = (
        value or ""
    ).strip()

    if not value:
        return ""

    try:
        datetime.strptime(
            value,
            "%H:%M",
        )

    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=(
                "ساعت باید با فرمت "
                "HH:MM باشد"
            ),
        )

    return value


def _schedule_document(
    item: dict,
) -> dict:
    return {
        "id": str(
            item.get("_id", "")
        ),

        "type": item.get(
            "type",
            "",
        ),

        "lesson": item.get(
            "lesson",
            "",
        ),

        "teacher": item.get(
            "teacher",
            "",
        ),

        "date": item.get(
            "date",
            "",
        ),

        "time": item.get(
            "time",
            "",
        ),

        "location": item.get(
            "location",
            "",
        ),

        "group": (
            item.get("group")
            or "هر دو"
        ),

        "note": (
            item.get("notes")
            or item.get("note", "")
        ),

        "flex_type": (
            item.get("flex_type")
            or "fixed"
        ),

        "flex_note": item.get(
            "flex_note",
            "",
        ),
    }


class ScheduleCreate(BaseModel):
    type: ScheduleType

    lesson: str = Field(
        min_length=2,
        max_length=100,
    )

    teacher: str = Field(
        default="",
        max_length=100,
    )

    date: str = Field(
        min_length=10,
        max_length=10,
    )

    time: str = Field(
        default="",
        max_length=5,
    )

    group: ScheduleGroup = "هر دو"

    location: str = Field(
        default="",
        max_length=100,
    )

    note: str = Field(
        default="",
        max_length=500,
    )

    flex_type: FlexType = "fixed"


class ScheduleUpdate(BaseModel):
    lesson: str = Field(
        min_length=2,
        max_length=100,
    )

    teacher: str = Field(
        default="",
        max_length=100,
    )

    date: str = Field(
        min_length=10,
        max_length=10,
    )

    time: str = Field(
        default="",
        max_length=5,
    )

    group: ScheduleGroup = "هر دو"

    location: str = Field(
        default="",
        max_length=100,
    )

    note: str = Field(
        default="",
        max_length=500,
    )

    flex_type: FlexType = "fixed"


class FlexChange(BaseModel):
    date: str = Field(
        min_length=10,
        max_length=10,
    )

    time: str = Field(
        min_length=5,
        max_length=5,
    )

    note: str = Field(
        default="",
        max_length=500,
    )


@router.get("/schedule")
async def schedule_list(
    stype: ScheduleType | None = Query(
        default=None
    ),

    admin=Depends(
        get_content_admin_user
    ),
):
    items = await db.get_schedules(
        stype=stype,
        upcoming=False,
    )

    if not isinstance(items, list):
        items = []

    return {
        "schedule": [
            _schedule_document(item)
            for item in items
            if isinstance(item, dict)
        ],
    }


@router.post("/schedule")
async def schedule_create(
    body: ScheduleCreate,

    admin=Depends(
        get_content_admin_user
    ),
):
    date = _valid_date(
        body.date
    )

    time = _valid_time(
        body.time
    )

    lesson = _clean(
        body.lesson,
        100,
    )

    teacher = _clean(
        body.teacher,
        100,
    )

    location = _clean(
        body.location,
        100,
    )

    note = str(
        body.note or ""
    ).strip()[:500]

    schedule_id = await db.add_schedule(
        stype=body.type,
        lesson=lesson,
        teacher=teacher,
        date=date,
        time=time,
        location=location,
        notes=note,
        group=body.group,
        flex_type=body.flex_type,
    )

    notified = 0

    try:
        users = await db.notif_users(
            "schedule",
            group=body.group,
        )

        collection = (
            db.client["medicalbot"]
            ["bot_notifications"]
        )

        icon = {
            "class": "🏫",
            "exam": "📝",
            "makeup": "🔄",
        }[body.type]

        type_label = {
            "class": "کلاس",
            "exam": "امتحان",
            "makeup": "جبرانی",
        }[body.type]

        text = (
            f"{icon} "
            f"<b>{type_label} جدید</b>"
            f"\n📚 {escape(lesson)}"
            f"\n📅 {date}"
        )

        if time:
            text += f"  ⏰ {time}"

        if teacher:
            text += (
                f"\n👨‍🏫 "
                f"{escape(teacher)}"
            )

        if location:
            text += (
                f"\n📍 "
                f"{escape(location)}"
            )

        documents = [
            {
                "type":
                    "schedule_notif",

                "chat_id":
                    user["user_id"],

                "text":
                    text,

                "sent":
                    False,

                "created_at":
                    datetime.now()
                    .isoformat(),
            }
            for user in users
            if user.get("user_id")
        ]

        if documents:
            await collection.insert_many(
                documents
            )

        notified = len(documents)

        # 🔔 موج ۴.۹۰ — اینباکس مینی‌اپ (Deep Link به تب «برنامه»)
        _inbox_body = f"📚 {lesson}\n📅 {date}"
        if time: _inbox_body += f"  ⏰ {time}"
        if teacher: _inbox_body += f"\n👨‍🏫 {teacher}"
        from urllib.parse import quote as _qq
        await db.inbox_add_many([
            {'user_id': user['user_id'], 'type': body.type,
             'title': f"{icon} {type_label} جدید",
             'body': _inbox_body,
             'link': '/schedule?hl=' + _qq(str(lesson or ''))}
            for user in users if user.get('user_id')
        ])

    except Exception:
        notified = 0

    return {
        "ok": True,
        "id": str(schedule_id),
        "notified": notified,
    }


@router.patch(
    "/schedule/{schedule_id}"
)
async def schedule_update(
    schedule_id: str,
    body: ScheduleUpdate,

    admin=Depends(
        get_content_admin_user
    ),
):
    date = _valid_date(
        body.date
    )

    time = _valid_time(
        body.time
    )

    ok = await db.update_schedule_full(
        schedule_id,

        _clean(
            body.lesson,
            100,
        ),

        _clean(
            body.teacher,
            100,
        ),

        date,
        time,

        _clean(
            body.location,
            100,
        ),

        str(
            body.note or ""
        ).strip()[:500],

        body.group,
        body.flex_type,
    )

    if not ok:
        raise HTTPException(
            status_code=404,
            detail="برنامه پیدا نشد",
        )

    return {
        "ok": True,
    }


@router.delete(
    "/schedule/{schedule_id}"
)
async def schedule_delete(
    schedule_id: str,

    admin=Depends(
        get_content_admin_user
    ),
):
    try:
        object_id = ObjectId(
            schedule_id
        )

    except Exception:
        raise HTTPException(
            status_code=422,
            detail=(
                "شناسه برنامه "
                "نامعتبر است"
            ),
        )

    result = await (
        db.schedules.delete_one(
            {
                "_id": object_id,
            }
        )
    )

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="برنامه پیدا نشد",
        )

    return {
        "ok": True,
    }


@router.get(
    "/schedule/flexible"
)
async def flexible_schedule_list(
    admin=Depends(
        get_content_admin_user
    ),
):
    items = await db.get_schedules(
        upcoming=True
    )

    if not isinstance(items, list):
        items = []

    return {
        "items": [
            _schedule_document(item)
            for item in items
            if (
                isinstance(item, dict)
                and item.get(
                    "flex_type"
                ) == "flexible"
            )
        ],
    }


@router.post(
    "/schedule/{schedule_id}"
    "/flex-change"
)
async def flexible_schedule_change(
    schedule_id: str,
    body: FlexChange,

    admin=Depends(
        get_content_admin_user
    ),
):
    date = _valid_date(
        body.date
    )

    time = _valid_time(
        body.time
    )

    schedule = (
        await db.get_schedule_by_id(
            schedule_id
        )
    )

    if not schedule:
        raise HTTPException(
            status_code=404,
            detail="برنامه پیدا نشد",
        )

    if (
        schedule.get("flex_type")
        != "flexible"
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "این کلاس منعطف نیست"
            ),
        )

    note = str(
        body.note or ""
    ).strip()[:500]

    ok = await db.update_schedule_time(
        schedule_id,
        date,
        time,
        note,
    )

    if not ok:
        raise HTTPException(
            status_code=500,
            detail=(
                "زمان کلاس "
                "به‌روزرسانی نشد"
            ),
        )

    notified = 0

    try:
        users = await db.notif_users(
            "schedule",

            group=schedule.get(
                "group",
                "هر دو",
            ),
        )

        collection = (
            db.client["medicalbot"]
            ["bot_notifications"]
        )

        text = (
            "🔄 <b>تغییر زمان کلاس</b>"
            f"\n📚 "
            f"{escape(str(schedule.get('lesson', '')))}"
            f"\n📅 {date}  ⏰ {time}"
        )

        if schedule.get("location"):
            text += (
                f"\n📍 "
                f"{escape(str(schedule['location']))}"
            )

        if note:
            text += (
                f"\n📝 {escape(note)}"
            )

        documents = [
            {
                "type":
                    "schedule_flex_change",

                "chat_id":
                    user["user_id"],

                "text":
                    text,

                "sent":
                    False,

                "created_at":
                    datetime.now()
                    .isoformat(),
            }
            for user in users
            if user.get("user_id")
        ]

        if documents:
            await collection.insert_many(
                documents
            )

        notified = len(documents)

        # 🔔 موج ۴.۹۰ — اینباکس مینی‌اپ (تغییر زمان کلاس)
        from urllib.parse import quote as _qq2
        await db.inbox_add_many([
            {'user_id': user['user_id'], 'type': 'schedule_change',
             'title': "🔄 تغییر زمان کلاس",
             'body': (f"📚 {schedule.get('lesson', '')}\n"
                      f"📅 {date}  ⏰ {time}"),
             'link': '/schedule?hl=' + _qq2(str(schedule.get('lesson', '') or ''))}
            for user in users if user.get('user_id')
        ])

    except Exception:
        notified = 0

    return {
        "ok": True,
        "notified": notified,
    }


class GradeEntry(BaseModel):
    user_id: int = Field(
        gt=0
    )

    score: float = Field(
        ge=0,
        le=20,
    )


class GradeBulkCreate(BaseModel):
    entries: list[GradeEntry] = Field(
        min_length=1,
        max_length=500,
    )

    lesson: str = Field(
        min_length=2,
        max_length=100,
    )

    exam_title: str = Field(
        min_length=2,
        max_length=100,
    )

    exam_date: str = Field(
        min_length=10,
        max_length=10,
    )


class GradeUpdate(BaseModel):
    score: float = Field(
        ge=0,
        le=20,
    )


@router.post("/grades/bulk")
async def grades_bulk_create(
    body: GradeBulkCreate,

    admin=Depends(
        get_content_admin_user
    ),
):
    exam_date = _valid_date(
        body.exam_date
    )

    lesson = _clean(
        body.lesson,
        100,
    )

    exam_title = _clean(
        body.exam_title,
        100,
    )

    user_ids = [
        entry.user_id
        for entry in body.entries
    ]

    if (
        len(user_ids)
        != len(set(user_ids))
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "هر دانشجو فقط یک بار "
                "باید در لیست باشد"
            ),
        )

    users = await db.users.find(
        {
            "user_id": {
                "$in": user_ids,
            },

            "approved": True,
        },
        {
            "user_id": 1,
        },
    ).to_list(
        len(user_ids)
    )

    valid_ids = {
        int(user["user_id"])
        for user in users
        if user.get("user_id")
    }

    if any(
        user_id not in valid_ids
        for user_id in user_ids
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "یک یا چند دانشجو "
                "معتبر یا تأییدشده نیستند"
            ),
        )

    saved = await db.grade_bulk_upsert(
        entries=[
            entry.model_dump()
            for entry in body.entries
        ],

        lesson=lesson,

        exam_title=exam_title,

        exam_date=exam_date,

        entered_by=admin["id"],
    )

    notified = 0

    try:
        collection = (
            db.client["medicalbot"]
            ["bot_notifications"]
        )

        safe_lesson = escape(
            lesson
        )

        safe_title = escape(
            exam_title
        )

        documents = [
            {
                "type":
                    "grade_notif",

                "chat_id":
                    item["student_id"],

                "text": (
                    "📊 <b>نمره‌ی جدید "
                    "ثبت شد</b>"

                    f"\n📚 "
                    f"{safe_lesson} — "
                    f"{safe_title}"

                    f"\n🎯 نمره: "
                    f"{item['score']}/20"
                ),

                "sent":
                    False,

                "created_at":
                    datetime.now()
                    .isoformat(),
            }

            for item in saved
        ]

        if documents:
            await collection.insert_many(
                documents
            )

        notified = len(documents)

        # 🔔 موج ۴.۹۰ — اینباکس مینی‌اپ (نمره → تب کارنامه)
        from urllib.parse import quote as _qq3
        await db.inbox_add_many([
            {'user_id': item['student_id'], 'type': 'grade',
             'title': "📊 نمره‌ی جدید ثبت شد",
             'body': (f"📚 {lesson} — {exam_title}\n"
                      f"🎯 نمره: {item['score']}/20"),
             'link': '/grades?hl=' + _qq3(str(lesson or ''))}
            for item in saved if item.get('student_id')
        ])

    except Exception:
        notified = 0

    return {
        "ok": True,
        "updated": len(saved),
        "notified": notified,
    }


@router.get("/grades/recent")
async def grades_recent(
    skip: int = Query(
        default=0,
        ge=0,
    ),

    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),

    intake: str | None = Query(
        default=None,
        max_length=50,
    ),

    admin=Depends(
        get_content_admin_user
    ),
):
    records = (
        await db.grade_list_recent(
            skip=skip,
            limit=limit,
            intake=intake,
        )
    )

    if not isinstance(records, list):
        records = []

    total = (
        await db.grade_count_recent(
            intake=intake
        )
    )

    user_ids = list({
        item.get("student_id")
        for item in records
        if item.get("student_id")
    })

    if user_ids:
        users = await db.users.find(
            {
                "user_id": {
                    "$in": user_ids,
                }
            },
            {
                "user_id": 1,
                "name": 1,
                "student_id": 1,
            },
        ).to_list(
            len(user_ids)
        )

    else:
        users = []

    users_by_id = {
        item.get("user_id"): item
        for item in users
    }

    result = []

    for record in records:
        grade = normalize_grade(
            record
        )

        if grade is None:
            continue

        user_id = record.get(
            "student_id"
        )

        student = users_by_id.get(
            user_id,
            {},
        )

        result.append({
            **grade,

            "student_id":
                user_id,

            "student_name": (
                student.get("name")
                or f"#{user_id}"
            ),

            "student_number":
                student.get(
                    "student_id",
                    "",
                ),
        })

    return {
        "total": max(
            0,
            int(total or 0),
        ),

        "grades": result,
    }


@router.get(
    "/grades/find-student"
)
async def grades_find_student(
    query: str = Query(
        min_length=2,
        max_length=100,
    ),

    admin=Depends(
        get_content_admin_user
    ),
):
    users = await db.search_users(
        query.strip()
    )

    return {
        "students": [
            {
                "id":
                    user.get("user_id"),

                "name":
                    user.get("name", ""),

                "student_id":
                    user.get(
                        "student_id",
                        "",
                    ),

                "group":
                    user.get(
                        "group",
                        "",
                    ),

                "intake":
                    user.get(
                        "intake",
                        "",
                    ),
            }

            for user in users

            if (
                user.get("approved")
                and user.get("user_id")
            )
        ],
    }


@router.patch(
    "/grades/{grade_id}"
)
async def grade_update(
    grade_id: str,
    body: GradeUpdate,

    admin=Depends(
        get_content_admin_user
    ),
):
    try:
        object_id = ObjectId(
            grade_id
        )

    except Exception:
        raise HTTPException(
            status_code=422,
            detail=(
                "شناسه نمره "
                "نامعتبر است"
            ),
        )

    result = await db.grades.update_one(
        {
            "_id": object_id,
        },

        {
            "$set": {
                "score":
                    body.score,

                "max_score":
                    20,

                "entered_by":
                    admin["id"],

                "updated_at":
                    datetime.now()
                    .isoformat(),
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="نمره پیدا نشد",
        )

    return {
        "ok": True,
        "score": body.score,
    }


@router.delete(
    "/grades/{grade_id}"
)
async def grade_delete(
    grade_id: str,

    admin=Depends(
        get_content_admin_user
    ),
):
    try:
        object_id = ObjectId(
            grade_id
        )

    except Exception:
        raise HTTPException(
            status_code=422,
            detail=(
                "شناسه نمره "
                "نامعتبر است"
            ),
        )

    result = (
        await db.grades.delete_one(
            {
                "_id": object_id,
            }
        )
    )

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="نمره پیدا نشد",
        )

    return {
        "ok": True,
    }

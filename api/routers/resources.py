"""Basic-science resource endpoints for the Telegram Mini App."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import get_resource_access_user
from api.telegram_send import send_bs_content
from database import db

logger = logging.getLogger(__name__)
router = APIRouter()

# تا زمانی که ارسال قبلی یک کاربر تمام نشده،
# درخواست ارسال جدید برای همان کاربر قبول نمی‌شود.
# این Guard از چند بار لمس سریع دکمه و ارسال تکراری جلوگیری می‌کند.
_sending_users: set[int] = set()


def _text(
    value,
    default: str = "",
) -> str:
    return str(
        value
        if value is not None
        else default
    ).strip()


def _safe_int(
    value,
    default: int = 0,
) -> int:
    try:
        return int(value or 0)
    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        return default


def _public_file(
    item: dict,
) -> dict:
    file_type = _text(
        item.get("type"),
        "file",
    )

    description = _text(
        item.get("description")
    )

    return {
        "id": str(
            item.get("_id") or ""
        ),
        "type": file_type,
        "name": (
            _text(item.get("name"))
            or description
            or "فایل آموزشی"
        ),
        "description": description,
        "downloads": max(
            0,
            _safe_int(
                item.get("downloads")
            ),
        ),
    }


@router.get("/terms")
async def terms(
    user=Depends(get_resource_access_user),
):
    raw_terms = await db.bs_lessons.distinct(
        "term"
    )

    term_names = sorted(
        {
            _text(value)
            for value in raw_terms
            if _text(value)
        }
    )

    result = []

    for term in term_names:
        count = await db.bs_lessons.count_documents(
            {
                "term": term,
            }
        )

        result.append(
            {
                "name": term,
                "lesson_count": max(
                    0,
                    _safe_int(count),
                ),
            }
        )

    return {
        "terms": result,
    }


@router.get("/lessons/{term}")
async def lessons(
    term: str,
    user=Depends(get_resource_access_user),
):
    items = await db.bs_get_lessons(
        term
    )

    result = []

    for item in (
        items
        if isinstance(items, list)
        else []
    ):
        lesson_id = str(
            item.get("_id") or ""
        )

        if not lesson_id:
            continue

        session_count = (
            await db.bs_sessions.count_documents(
                {
                    "lesson_id": lesson_id,
                }
            )
        )

        result.append(
            {
                "_id": lesson_id,
                "name": _text(
                    item.get("name"),
                    "درس بدون نام",
                ),
                "teacher": _text(
                    item.get("teacher")
                ),
                "term": _text(
                    item.get("term"),
                    term,
                ),
                "session_count": max(
                    0,
                    _safe_int(
                        session_count
                    ),
                ),
            }
        )

    return {
        "lessons": result,
    }


@router.get("/sessions/{lesson_id}")
async def sessions(
    lesson_id: str,
    user=Depends(get_resource_access_user),
):
    items = await db.bs_get_sessions(
        lesson_id
    )

    result = []

    for item in (
        items
        if isinstance(items, list)
        else []
    ):
        session_id = str(
            item.get("_id") or ""
        )

        if not session_id:
            continue

        file_count = (
            await db.bs_content.count_documents(
                {
                    "session_id": session_id,
                }
            )
        )

        result.append(
            {
                "_id": session_id,
                "number": max(
                    0,
                    _safe_int(
                        item.get("number")
                    ),
                ),
                "topic": _text(
                    item.get("topic"),
                    "جلسه بدون عنوان",
                ),
                "teacher": _text(
                    item.get("teacher")
                ),
                "file_count": max(
                    0,
                    _safe_int(
                        file_count
                    ),
                ),
            }
        )

    return {
        "sessions": result,
    }


@router.get("/files/{session_id}")
async def files(
    session_id: str,
    user=Depends(get_resource_access_user),
):
    items = await db.bs_get_content(
        session_id
    )

    return {
        "files": [
            _public_file(item)
            for item in (
                items
                if isinstance(
                    items,
                    list,
                )
                else []
            )
            if (
                isinstance(item, dict)
                and item.get("_id")
            )
        ]
    }


@router.post("/download/{content_id}")
async def download(
    content_id: str,
    user=Depends(get_resource_access_user),
):
    """فقط همان فایل انتخاب‌شده را در تلگرام ارسال می‌کند."""

    user_id = int(
        user["id"]
    )

    # فقط یک رکورد با شناسه‌ای که کاربر روی آن کلیک کرده
    # از دیتابیس خوانده می‌شود.
    item = await db.bs_get_content_item(
        content_id
    )

    if not item:
        raise HTTPException(
            status_code=404,
            detail="فایل پیدا نشد",
        )

    if not _text(
        item.get("file_id")
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "شناسه تلگرام این فایل "
                "ثبت نشده است"
            ),
        )

    # اگر ارسال دیگری برای همین کاربر در حال انجام است،
    # اجازه شروع درخواست دوم داده نمی‌شود.
    if user_id in _sending_users:
        raise HTTPException(
            status_code=409,
            detail=(
                "ارسال فایل قبلی هنوز تمام نشده است؛ "
                "چند لحظه صبر کنید"
            ),
        )

    _sending_users.add(
        user_id
    )

    try:
        next_downloads = (
            max(
                0,
                _safe_int(
                    item.get("downloads")
                ),
            )
            + 1
        )

        # فقط همین یک سند به تابع ارسال تلگرام داده می‌شود.
        # هیچ لیست جلسه یا فایل کناری وارد تابع ارسال نمی‌شود.
        send_item = {
            **item,
            "downloads": next_downloads,
        }

        sent = await send_bs_content(
            user_id,
            content_id,
            send_item,
        )

        if not sent:
            raise HTTPException(
                status_code=502,
                detail=(
                    "ارسال فایل از طریق ربات ناموفق بود. "
                    "لطفاً ابتدا یک پیام به ربات بفرستید "
                    "یا دوباره تلاش کنید."
                ),
            )

        # شمارنده فقط بعد از ارسال موفق فایل افزایش پیدا می‌کند.
        try:
            await db.bs_inc_download(
                content_id,
                user_id,
            )
        except Exception:
            # فایل قبلاً به کاربر رسیده است.
            # خطای شمارنده نباید باعث شود کاربر دوباره فایل را
            # ارسال کند و دو نسخه دریافت کند.
            logger.exception(
                "Updating basic-science "
                "download count failed"
            )

        public = _public_file(
            send_item
        )

        return {
            "sent": True,
            "file_id": public["id"],
            "type": public["type"],
            "name": public["name"],
            "downloads": next_downloads,
        }

    finally:
        # حتی در صورت خطا، قفل کاربر حتماً آزاد می‌شود.
        _sending_users.discard(
            user_id
        )


@router.get("/search")
async def search(
    q: str = Query(
        ...,
        min_length=2,
        max_length=100,
    ),
    user=Depends(get_resource_access_user),
):
    results = await db.search_resources(
        q.strip()
    )

    public_results = []

    for item in (
        results
        if isinstance(results, list)
        else []
    ):
        if (
            not isinstance(item, dict)
            or not item.get("_id")
        ):
            continue

        session = (
            item.get("_session")
            if isinstance(
                item.get("_session"),
                dict,
            )
            else {}
        )

        lesson = (
            item.get("_lesson")
            if isinstance(
                item.get("_lesson"),
                dict,
            )
            else {}
        )

        public = _public_file(
            item
        )

        public.update(
            {
                "lesson": _text(
                    lesson.get("name")
                    or item.get(
                        "lesson_name"
                    )
                ),
                "session": _text(
                    session.get("topic")
                    or item.get(
                        "session_topic"
                    )
                ),
            }
        )

        public_results.append(
            public
        )

    return {
        "results": public_results,
    }

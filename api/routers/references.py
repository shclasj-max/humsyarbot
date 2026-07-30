"""Educational-reference endpoints for the Telegram Mini App."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_resource_access_user
from api.telegram_send import send_ref_file
from database import db

logger = logging.getLogger(__name__)
router = APIRouter()

# جلوگیری از ارسال‌های تکراری ناشی از لمس سریع یا درخواست هم‌زمان.
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


def _public_reference_file(
    item: dict,
) -> dict:
    return {
        "id": str(
            item.get("_id") or ""
        ),
        "lang": (
            "en"
            if _text(
                item.get("lang")
            ).lower() == "en"
            else "fa"
        ),
        "volume": max(
            1,
            _safe_int(
                item.get("volume"),
                1,
            ),
        ),
        "description": _text(
            item.get("description")
        ),
        "downloads": max(
            0,
            _safe_int(
                item.get("downloads")
            ),
        ),
    }


@router.get("/subjects")
async def subjects(
    user=Depends(get_resource_access_user),
):
    items = await db.ref_get_subjects()

    result = []

    for item in (
        items
        if isinstance(items, list)
        else []
    ):
        subject_id = str(
            item.get("_id") or ""
        )

        if not subject_id:
            continue

        books = await db.ref_get_books(
            subject_id
        )

        result.append(
            {
                "id": subject_id,
                "name": _text(
                    item.get("name"),
                    "موضوع بدون نام",
                ),
                "book_count": (
                    len(books)
                    if isinstance(
                        books,
                        list,
                    )
                    else 0
                ),
            }
        )

    return {
        "subjects": result,
    }


@router.get("/books/{subject_id}")
async def books(
    subject_id: str,
    user=Depends(get_resource_access_user),
):
    subject = await db.ref_get_subject(
        subject_id
    )

    if not subject:
        raise HTTPException(
            status_code=404,
            detail="موضوع پیدا نشد",
        )

    book_items = await db.ref_get_books(
        subject_id
    )

    result = []

    for item in (
        book_items
        if isinstance(
            book_items,
            list,
        )
        else []
    ):
        book_id = str(
            item.get("_id") or ""
        )

        if not book_id:
            continue

        file_items = await db.ref_get_files(
            book_id
        )

        safe_files = (
            file_items
            if isinstance(
                file_items,
                list,
            )
            else []
        )

        result.append(
            {
                "id": book_id,
                "name": _text(
                    item.get("name"),
                    "کتاب بدون نام",
                ),
                "fa_count": sum(
                    1
                    for file in safe_files
                    if file.get("lang") == "fa"
                ),
                "en_count": sum(
                    1
                    for file in safe_files
                    if file.get("lang") == "en"
                ),
            }
        )

    return {
        "subject": {
            "id": subject_id,
            "name": _text(
                subject.get("name"),
                "موضوع بدون نام",
            ),
        },
        "books": result,
    }


@router.get("/files/{book_id}")
async def files(
    book_id: str,
    user=Depends(get_resource_access_user),
):
    book = await db.ref_get_book(
        book_id
    )

    if not book:
        raise HTTPException(
            status_code=404,
            detail="کتاب پیدا نشد",
        )

    file_items = await db.ref_get_files(
        book_id
    )

    safe_files = (
        file_items
        if isinstance(
            file_items,
            list,
        )
        else []
    )

    fa_files = sorted(
        [
            item
            for item in safe_files
            if item.get("lang") == "fa"
        ],
        key=lambda item: max(
            1,
            _safe_int(
                item.get("volume"),
                1,
            ),
        ),
    )

    en_files = sorted(
        [
            item
            for item in safe_files
            if item.get("lang") == "en"
        ],
        key=lambda item: max(
            1,
            _safe_int(
                item.get("volume"),
                1,
            ),
        ),
    )

    return {
        "book": {
            "id": book_id,
            "name": _text(
                book.get("name"),
                "کتاب بدون نام",
            ),
        },
        "fa_files": [
            _public_reference_file(
                item
            )
            for item in fa_files
        ],
        "en_files": [
            _public_reference_file(
                item
            )
            for item in en_files
        ],
    }


@router.post("/download/{file_id}")
async def download(
    file_id: str,
    user=Depends(get_resource_access_user),
):
    """فقط همان جلد انتخاب‌شده را ارسال می‌کند."""

    user_id = int(
        user["id"]
    )

    # فقط رکورد همان جلدی که کاربر روی آن کلیک کرده
    # از دیتابیس گرفته می‌شود.
    item = await db.ref_get_file(
        file_id
    )

    if not item:
        raise HTTPException(
            status_code=404,
            detail=(
                "فایل رفرنس پیدا نشد"
            ),
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

    # تا پایان ارسال قبلی، درخواست ارسال جدید
    # برای همین کاربر قبول نمی‌شود.
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

        # فقط همین یک رکورد برای تابع ارسال تلگرام فرستاده می‌شود.
        # فایل‌های زبان دیگر یا جلدهای دیگر وارد این تابع نمی‌شوند.
        send_item = {
            **item,
            "downloads": next_downloads,
        }

        sent = await send_ref_file(
            user_id,
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

        # شمارنده فقط پس از ارسال موفق افزایش پیدا می‌کند.
        try:
            await db.ref_inc_download(
                file_id,
                user_id,
            )

        except Exception:
            # فایل قبلاً برای کاربر ارسال شده است؛
            # خطای ثبت آمار نباید باعث ارسال مجدد شود.
            logger.exception(
                "Updating reference "
                "download count failed"
            )

        public = _public_reference_file(
            send_item
        )

        return {
            "sent": True,
            "file_id": public["id"],
            "lang": public["lang"],
            "volume": public["volume"],
            "downloads": next_downloads,
        }

    finally:
        # قفل در موفقیت و خطا حتماً آزاد می‌شود.
        _sending_users.discard(
            user_id
        )

"""Hoshyar AI endpoints for the Telegram Mini App.

The router deliberately keeps provider credentials and remote file URIs on the
backend. The Mini App only receives safe metadata for an active reference
file. Media is read with a hard byte limit and validated from its signature,
not merely from the client supplied Content-Type header.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from pathlib import PurePath

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ai_solver import (
    MAX_INPUT_CHARS,
    MAX_MEDIA_BYTES,
    AIError,
    _busy_users,
    _clear_memory,
    _gemini_upload_file,
    _get_history,
    _remember,
    _transcode_ogg_opus_to_wav,
    ask_ai,
    check_and_consume_quota,
    get_ai_config,
    record_token_usage,
)
from api.auth import get_current_user
from database import db

logger = logging.getLogger(__name__)
router = APIRouter()

REFERENCE_TTL_HOURS = 48
_READ_CHUNK_BYTES = 1024 * 1024

_SUPPORTED_AUDIO_MIMES = {
    "audio/aac",
    "audio/flac",
    "audio/m4a",
    "audio/mp3",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "audio/x-aac",
    "audio/x-m4a",
    "audio/x-wav",
}


class AskRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=MAX_INPUT_CHARS,
    )


class ReportRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=MAX_INPUT_CHARS,
    )
    answer: str = Field(
        min_length=1,
        max_length=12000,
    )


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return default


def _public_history(items: list) -> list[dict]:
    result = []

    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        if role not in ("user", "assistant", "model"):
            continue

        result.append(
            {
                "role": "assistant" if role == "model" else role,
                "text": str(item.get("text") or "")[:12000],
            }
        )

    return result


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value

    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None


def _now_for(value: datetime) -> datetime:
    if value.tzinfo:
        return datetime.now(tz=value.tzinfo)

    return datetime.now()


def _public_reference(document: dict | None) -> dict | None:
    """Return metadata without exposing Gemini private file URI."""

    if not isinstance(document, dict):
        return None

    if not document.get("uri"):
        return None

    uploaded_at = _parse_datetime(document.get("at"))

    expires_at = (
        uploaded_at + timedelta(hours=REFERENCE_TTL_HOURS)
        if uploaded_at
        else None
    )

    expired = bool(
        expires_at
        and _now_for(expires_at) >= expires_at
    )

    return {
        "name": str(
            document.get("name") or "سند مرجع"
        )[:100],
        "mime": str(
            document.get("mime") or "application/pdf"
        )[:100],
        "uploaded_at": (
            uploaded_at.isoformat()
            if uploaded_at
            else None
        ),
        "expires_at": (
            expires_at.isoformat()
            if expires_at
            else None
        ),
        "expired": expired,
    }


async def _active_reference(
    user_id: int,
) -> dict | None:
    document = await db.ai_get_doc(user_id)
    public = _public_reference(document)

    if public and public["expired"]:
        await db.ai_clear_doc(user_id)
        return None

    return public


def _clean_filename(
    filename: str | None,
    fallback: str,
) -> str:
    raw = PurePath(
        str(filename or fallback).replace("\\", "/")
    ).name

    cleaned = re.sub(
        r"[\x00-\x1f\x7f]",
        "",
        raw,
    ).strip(" .")

    return (cleaned or fallback)[:100]


def _normalise_content_type(
    value: str | None,
) -> str:
    return (
        str(value or "")
        .split(";", 1)[0]
        .strip()
        .lower()
    )


def _detect_media(
    data: bytes,
    declared_type: str | None,
    filename: str | None,
) -> tuple[str, str]:
    """Detect supported media using magic bytes."""

    head = data[:64]
    declared = _normalise_content_type(
        declared_type
    )
    suffix = PurePath(
        filename or ""
    ).suffix.lower()

    if head.startswith(b"%PDF-"):
        return "pdf", "application/pdf"

    if head.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg"

    if head.startswith(
        b"\x89PNG\r\n\x1a\n"
    ):
        return "image", "image/png"

    if (
        len(head) >= 12
        and head[:4] == b"RIFF"
        and head[8:12] == b"WEBP"
    ):
        return "image", "image/webp"

    if (
        len(head) >= 12
        and head[:4] == b"RIFF"
        and head[8:12] == b"WAVE"
    ):
        return "audio", "audio/wav"

    if head.startswith(b"OggS"):
        return "audio", "audio/ogg"

    if head.startswith(b"fLaC"):
        return "audio", "audio/flac"

    if head.startswith(
        b"\x1aE\xdf\xa3"
    ):
        return "audio", "audio/webm"

    if (
        head.startswith(b"ID3")
        or (
            len(head) >= 2
            and head[0] == 0xFF
            and (head[1] & 0xE0) == 0xE0
        )
    ):
        if (
            declared
            in {
                "audio/aac",
                "audio/x-aac",
            }
            or suffix == ".aac"
        ):
            return "audio", "audio/aac"

        return "audio", "audio/mpeg"

    if (
        len(head) >= 12
        and head[4:8] == b"ftyp"
    ):
        if declared.startswith("video/"):
            raise HTTPException(
                status_code=415,
                detail=(
                    "فایل ویدیویی پشتیبانی نمی‌شود؛ "
                    "فقط فایل صوتی بفرستید"
                ),
            )

        return "audio", "audio/mp4"

    if head.startswith(b"ADIF"):
        return "audio", "audio/aac"

    audio_extensions = {
        ".aac",
        ".flac",
        ".m4a",
        ".mp3",
        ".mp4",
        ".oga",
        ".ogg",
        ".wav",
        ".webm",
    }

    if (
        declared in _SUPPORTED_AUDIO_MIMES
        and suffix in audio_extensions
    ):
        canonical = {
            "audio/mp3": "audio/mpeg",
            "audio/m4a": "audio/mp4",
            "audio/x-m4a": "audio/mp4",
            "audio/x-wav": "audio/wav",
            "audio/x-aac": "audio/aac",
        }.get(
            declared,
            declared,
        )

        return "audio", canonical

    raise HTTPException(
        status_code=415,
        detail=(
            "فرمت فایل پشتیبانی نمی‌شود؛ "
            "عکس JPG/PNG/WEBP، فایل PDF "
            "یا فایل صوتی بفرستید"
        ),
    )


async def _read_upload_limited(
    upload: UploadFile,
) -> bytes:
    declared_size = getattr(
        upload,
        "size",
        None,
    )

    if (
        declared_size
        and declared_size > MAX_MEDIA_BYTES
    ):
        raise HTTPException(
            status_code=413,
            detail=(
                "حجم فایل نباید بیشتر از "
                f"{MAX_MEDIA_BYTES // (1024 * 1024)} "
                "مگابایت باشد"
            ),
        )

    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = await upload.read(
            _READ_CHUNK_BYTES
        )

        if not chunk:
            break

        total += len(chunk)

        if total > MAX_MEDIA_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    "حجم فایل نباید بیشتر از "
                    f"{MAX_MEDIA_BYTES // (1024 * 1024)} "
                    "مگابایت باشد"
                ),
            )

        chunks.append(chunk)

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="فایل خالی است",
        )

    return b"".join(chunks)


def _validate_message(
    message: str | None,
    *,
    required: bool,
) -> str:
    text = str(
        message or ""
    ).strip()

    if required and not text:
        raise HTTPException(
            status_code=422,
            detail="متن سؤال را وارد کنید",
        )

    if len(text) > MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=422,
            detail=(
                "متن سؤال نباید بیشتر از "
                f"{MAX_INPUT_CHARS} کاراکتر باشد"
            ),
        )

    return text


def _acquire_user(
    user_id: int,
) -> None:
    if user_id in _busy_users:
        raise HTTPException(
            status_code=409,
            detail=(
                "پاسخ قبلی هنوز "
                "در حال آماده‌شدن است"
            ),
        )

    _busy_users.add(user_id)


async def _ensure_available(
    user_id: int,
) -> dict:
    if await db.ai_is_banned(user_id):
        raise HTTPException(
            status_code=403,
            detail=(
                "دسترسی شما به هوشیار "
                "مسدود شده است"
            ),
        )

    config = await get_ai_config()

    if not config.get("enabled"):
        raise HTTPException(
            status_code=503,
            detail=(
                config.get(
                    "disabled_message"
                )
                or (
                    "هوشیار فعلاً توسط "
                    "مدیریت غیرفعال است"
                )
            ),
        )

    if not config.get("api_key"):
        raise HTTPException(
            status_code=503,
            detail=(
                "هوشیار هنوز توسط "
                "مدیریت آماده نشده است"
            ),
        )

    return config


async def _consume_quota(
    user_id: int,
) -> tuple[int, int]:
    allowed, used, limit = (
        await check_and_consume_quota(
            user_id
        )
    )

    used = max(
        0,
        _safe_int(used),
    )
    limit = max(
        0,
        _safe_int(limit),
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                "سهمیه روزانه هوشیار "
                f"تمام شده است ({used}/{limit})"
            ),
        )

    return used, limit


def _usage_payload(
    used: int,
    limit: int,
) -> dict:
    return {
        "used_today": used,
        "daily_limit": limit,
        "remaining": (
            max(0, limit - used)
            if limit
            else None
        ),
        "unlimited": limit == 0,
    }


async def _ask_provider(
    *,
    user_id: int,
    prompt: str,
    history_items: list,
    memory_label: str,
    used: int,
    limit: int,
    media_bytes: bytes | None = None,
    media_mime: str = "image/jpeg",
) -> dict:
    answer, tokens = await ask_ai(
        text=prompt or None,
        image_bytes=media_bytes,
        image_mime=media_mime,
        history=history_items,
        uid=user_id,
    )

    answer = str(
        answer or ""
    ).strip()

    if not answer:
        raise HTTPException(
            status_code=502,
            detail=(
                "هوشیار پاسخی برنگرداند"
            ),
        )

    token_count = max(
        0,
        _safe_int(tokens),
    )

    await _remember(
        user_id,
        "user",
        memory_label,
    )

    await _remember(
        user_id,
        "assistant",
        answer,
    )

    await record_token_usage(
        user_id,
        token_count,
    )

    return {
        "answer": answer,
        "tokens": token_count,
        **_usage_payload(
            used,
            limit,
        ),
    }


def _gemini_file_name(
    file_info: dict | None,
) -> str | None:
    if (
        isinstance(file_info, dict)
        and file_info.get("name")
    ):
        name = str(
            file_info["name"]
        ).strip().lstrip("/")

        if name.startswith("files/"):
            return name

        return None

    uri = str(
        (file_info or {}).get("uri")
        or ""
    )

    match = re.search(
        r"/(files/[^/?#]+)",
        uri,
    )

    return (
        match.group(1)
        if match
        else None
    )


async def _wait_for_gemini_file(
    api_key: str,
    file_info: dict,
) -> dict:
    """Wait for Gemini PDF processing."""

    state = str(
        file_info.get("state") or ""
    ).upper()

    if state == "ACTIVE" or not state:
        return file_info

    if state == "FAILED":
        raise AIError(
            "پردازش PDF توسط سرویس "
            "هوش مصنوعی ناموفق بود"
        )

    remote_name = _gemini_file_name(
        file_info
    )

    if not remote_name:
        return file_info

    url = (
        "https://generativelanguage."
        "googleapis.com/v1beta/"
        f"{remote_name}"
    )

    headers = {
        "x-goog-api-key": api_key,
    }

    try:
        async with httpx.AsyncClient(
            timeout=20
        ) as client:
            for _ in range(15):
                await asyncio.sleep(1.5)

                response = await client.get(
                    url,
                    headers=headers,
                )

                if response.status_code != 200:
                    continue

                current = (
                    response.json()
                    or {}
                )

                current_state = str(
                    current.get("state")
                    or ""
                ).upper()

                if current_state == "ACTIVE":
                    return current

                if current_state == "FAILED":
                    raise AIError(
                        "پردازش PDF توسط سرویس "
                        "هوش مصنوعی ناموفق بود"
                    )

    except AIError:
        raise

    except (
        httpx.HTTPError,
        ValueError,
    ):
        logger.warning(
            "Checking Gemini reference "
            "state failed",
            exc_info=True,
        )

    raise AIError(
        "آماده‌سازی PDF بیش از حد "
        "طول کشید؛ کمی بعد دوباره "
        "امتحان کنید"
    )


async def _delete_remote_reference(
    config: dict,
    document: dict | None,
) -> None:
    """Best-effort privacy cleanup."""

    if (
        config.get("provider")
        != "gemini"
        or not config.get("api_key")
    ):
        return

    remote_name = _gemini_file_name(
        document
    )

    if not remote_name:
        return

    try:
        async with httpx.AsyncClient(
            timeout=15
        ) as client:
            await client.delete(
                (
                    "https://generativelanguage."
                    "googleapis.com/v1beta/"
                    f"{remote_name}"
                ),
                headers={
                    "x-goog-api-key": (
                        config["api_key"]
                    )
                },
            )

    except httpx.HTTPError:
        logger.info(
            "Remote Gemini reference "
            "cleanup failed",
            exc_info=True,
        )


async def _store_pdf_reference(
    *,
    user_id: int,
    config: dict,
    data: bytes,
    filename: str,
) -> dict:
    previous = await db.ai_get_doc(
        user_id
    )

    uploaded = await _gemini_upload_file(
        config["api_key"],
        data,
        "application/pdf",
        filename,
    )

    uploaded = (
        await _wait_for_gemini_file(
            config["api_key"],
            uploaded,
        )
    )

    uri = uploaded.get("uri")

    if not uri:
        raise AIError(
            "سرویس هوش مصنوعی "
            "شناسه فایل را برنگرداند"
        )

    mime = (
        uploaded.get("mimeType")
        or "application/pdf"
    )

    await db.ai_set_doc(
        user_id,
        uri,
        mime,
        filename,
    )

    if (
        previous
        and previous.get("uri") != uri
    ):
        await _delete_remote_reference(
            config,
            previous,
        )

    return await _active_reference(
        user_id
    )


@router.get("/status")
async def status(
    user=Depends(get_current_user),
):
    config = await get_ai_config()
    database_user = (
        user.get("_db") or {}
    )

    banned = await db.ai_is_banned(
        user["id"]
    )

    limit = max(
        0,
        _safe_int(
            config.get("daily_limit")
        ),
    )

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    used = (
        max(
            0,
            _safe_int(
                database_user.get(
                    "ai_usage_count"
                )
            ),
        )
        if database_user.get(
            "ai_usage_date"
        )
        == today
        else 0
    )

    provider = str(
        config.get("provider") or ""
    )

    return {
        "enabled": bool(
            config.get("enabled")
        ),
        "banned": bool(banned),
        "provider": provider,
        "model": str(
            config.get("model") or ""
        ),
        "daily_limit": limit,
        "used_today": used,
        "remaining": (
            max(0, limit - used)
            if limit
            else None
        ),
        "unlimited": limit == 0,
        "disabled_message": str(
            config.get(
                "disabled_message"
            )
            or ""
        ),
        "max_input_chars": (
            MAX_INPUT_CHARS
        ),
        "max_media_bytes": (
            MAX_MEDIA_BYTES
        ),
        "capabilities": {
            "text": True,
            "image": provider
            in {
                "gemini",
                "openrouter",
            },
            "pdf": provider == "gemini",
            "audio": provider == "gemini",
            "reference_document": (
                provider == "gemini"
            ),
        },
        "active_reference": (
            await _active_reference(
                user["id"]
            )
        ),
    }


@router.get("/history")
async def history(
    user=Depends(get_current_user),
):
    items = await _get_history(
        user["id"]
    )

    return {
        "messages": _public_history(
            items
        )
    }


@router.post("/ask")
async def ask(
    body: AskRequest,
    user=Depends(get_current_user),
):
    user_id = user["id"]

    message = _validate_message(
        body.message,
        required=True,
    )

    await _ensure_available(user_id)
    _acquire_user(user_id)

    try:
        used, limit = await _consume_quota(
            user_id
        )

        return await _ask_provider(
            user_id=user_id,
            prompt=message,
            history_items=(
                await _get_history(
                    user_id
                )
            ),
            memory_label=message,
            used=used,
            limit=limit,
        )

    except HTTPException:
        raise

    except AIError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    except Exception as error:
        logger.exception(
            "Hoshyar text request failed "
            "for user %s",
            user_id,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "ارتباط با سرویس "
                "هوش مصنوعی ناموفق بود"
            ),
        ) from error

    finally:
        _busy_users.discard(
            user_id
        )


@router.post("/ask-media")
async def ask_media(
    message: str = Form(default=""),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Ask with image, PDF or audio."""

    user_id = user["id"]

    prompt = _validate_message(
        message,
        required=False,
    )

    config = await _ensure_available(
        user_id
    )

    _acquire_user(user_id)

    try:
        try:
            data = await _read_upload_limited(
                file
            )
        finally:
            await file.close()

        kind, mime = _detect_media(
            data,
            file.content_type,
            file.filename,
        )

        fallback_names = {
            "image": "تصویر.jpg",
            "pdf": "سند.pdf",
            "audio": (
                "صدای ضبط‌شده.webm"
            ),
        }

        filename = _clean_filename(
            file.filename,
            fallback_names[kind],
        )

        if (
            kind in {"pdf", "audio"}
            and config.get("provider")
            != "gemini"
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "پردازش PDF و صدا فقط "
                    "وقتی ارائه‌دهنده هوشیار "
                    "Gemini باشد در دسترس است"
                ),
            )

        active_reference = (
            await _active_reference(
                user_id
            )
        )

        media_bytes: bytes | None = data

        if kind == "pdf":
            active_reference = (
                await _store_pdf_reference(
                    user_id=user_id,
                    config=config,
                    data=data,
                    filename=filename,
                )
            )

            media_bytes = None

        elif (
            kind == "audio"
            and mime == "audio/ogg"
        ):
            converted = (
                await _transcode_ogg_opus_to_wav(
                    data
                )
            )

            if not converted:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "این فرمت پیام صوتی "
                        "قابل پردازش نیست؛ "
                        "فایل MP3/WAV بفرستید "
                        "یا سؤال را تایپ کنید"
                    ),
                )

            media_bytes = converted
            mime = "audio/wav"

        default_prompts = {
            "image": (
                "این تصویر را دقیق بررسی کن؛ "
                "اگر سؤال درسی است آن را حل "
                "و پاسخ را توضیح بده."
            ),
            "pdf": (
                "این PDF را به‌عنوان سند "
                "مرجع فعال بررسی کن، موضوع "
                "و نکات اصلی آن را کوتاه "
                "معرفی کن."
            ),
            "audio": (
                "محتوای این فایل صوتی را "
                "درک کن و به سؤال یا درخواست "
                "مطرح‌شده در آن پاسخ بده."
            ),
        }

        provider_prompt = (
            prompt
            or default_prompts[kind]
        )

        labels = {
            "image": "تصویر",
            "pdf": "سند مرجع PDF",
            "audio": "فایل صوتی",
        }

        memory_label = (
            f"[{labels[kind]}: {filename}]"
        )

        if prompt:
            memory_label += (
                f"\n{prompt}"
            )

        used, limit = (
            await _consume_quota(
                user_id
            )
        )

        result = await _ask_provider(
            user_id=user_id,
            prompt=provider_prompt,
            history_items=(
                await _get_history(
                    user_id
                )
            ),
            memory_label=memory_label,
            used=used,
            limit=limit,
            media_bytes=media_bytes,
            media_mime=mime,
        )

        result["attachment"] = {
            "kind": kind,
            "name": filename,
            "mime": mime,
            "size_bytes": len(data),
            "reference_active": (
                kind == "pdf"
            ),
        }

        result["active_reference"] = (
            active_reference
        )

        return result

    except HTTPException:
        raise

    except AIError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    except Exception as error:
        logger.exception(
            "Hoshyar media request failed "
            "for user %s",
            user_id,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "پردازش فایل یا ارتباط "
                "با سرویس هوش مصنوعی "
                "ناموفق بود"
            ),
        ) from error

    finally:
        _busy_users.discard(
            user_id
        )


@router.post("/reference")
async def upload_reference(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Attach PDF without quota use."""

    user_id = user["id"]

    config = await _ensure_available(
        user_id
    )

    if (
        config.get("provider")
        != "gemini"
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "سند مرجع فقط وقتی "
                "ارائه‌دهنده هوشیار Gemini "
                "باشد در دسترس است"
            ),
        )

    _acquire_user(user_id)

    try:
        try:
            data = (
                await _read_upload_limited(
                    file
                )
            )
        finally:
            await file.close()

        kind, _ = _detect_media(
            data,
            file.content_type,
            file.filename,
        )

        if kind != "pdf":
            raise HTTPException(
                status_code=415,
                detail=(
                    "برای سند مرجع فقط "
                    "فایل PDF مجاز است"
                ),
            )

        filename = _clean_filename(
            file.filename,
            "سند.pdf",
        )

        reference = (
            await _store_pdf_reference(
                user_id=user_id,
                config=config,
                data=data,
                filename=filename,
            )
        )

        return {
            "ok": True,
            "active_reference": reference,
        }

    except HTTPException:
        raise

    except AIError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    except Exception as error:
        logger.exception(
            "Reference upload failed "
            "for user %s",
            user_id,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "آپلود سند مرجع ناموفق بود"
            ),
        ) from error

    finally:
        _busy_users.discard(
            user_id
        )


@router.delete("/reference")
async def clear_reference(
    user=Depends(get_current_user),
):
    user_id = user["id"]

    if user_id in _busy_users:
        raise HTTPException(
            status_code=409,
            detail=(
                "پاسخ قبلی هنوز "
                "در حال آماده‌شدن است"
            ),
        )

    document = await db.ai_get_doc(
        user_id
    )

    config = await get_ai_config()

    await db.ai_clear_doc(
        user_id
    )

    await _delete_remote_reference(
        config,
        document,
    )

    return {
        "ok": True,
    }


@router.delete("/history")
async def clear_history(
    clear_reference: bool = False,
    user=Depends(get_current_user),
):
    user_id = user["id"]

    if user_id in _busy_users:
        raise HTTPException(
            status_code=409,
            detail=(
                "پاسخ قبلی هنوز "
                "در حال آماده‌شدن است"
            ),
        )

    await _clear_memory(
        user_id
    )

    reference_cleared = False

    if clear_reference:
        document = await db.ai_get_doc(
            user_id
        )

        config = await get_ai_config()

        await db.ai_clear_doc(
            user_id
        )

        await _delete_remote_reference(
            config,
            document,
        )

        reference_cleared = True

    return {
        "ok": True,
        "reference_cleared": (
            reference_cleared
        ),
    }


@router.post("/report")
async def report(
    body: ReportRequest,
    user=Depends(get_current_user),
):
    database_user = (
        user.get("_db") or {}
    )

    await db.ai_log_report(
        user["id"],
        str(
            database_user.get("name")
            or ""
        ),
        body.question.strip(),
        body.answer.strip(),
    )

    return {
        "ok": True,
    }

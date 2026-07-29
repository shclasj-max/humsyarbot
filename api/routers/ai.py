"""Hoshyar AI endpoints for the Telegram Mini App."""

from __future__ import annotations

from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from pydantic import (
    BaseModel,
    Field,
)

from api.auth import (
    get_current_user,
)

from database import db

from ai_solver import (
    AIError,
    MAX_INPUT_CHARS,
    _busy_users,
    _clear_memory,
    _get_history,
    _remember,
    ask_ai,
    check_and_consume_quota,
    get_ai_config,
    record_token_usage,
)


router = APIRouter()


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


def public_history(
    items: list,
) -> list[dict]:
    result = []

    if not isinstance(
        items,
        list,
    ):
        return result

    for item in items:
        role = item.get("role")

        if role not in (
            "user",
            "assistant",
            "model",
        ):
            continue

        result.append({
            "role": (
                "assistant"
                if role == "model"
                else role
            ),

            "text": str(
                item.get(
                    "text",
                    "",
                )
            )[:12000],
        })

    return result


@router.get("/status")
async def status(
    user=Depends(
        get_current_user
    ),
):
    config = (
        await get_ai_config()
    )

    database_user = user["_db"]

    banned = (
        await db.ai_is_banned(
            user["id"]
        )
    )

    limit = max(
        0,
        int(
            config.get(
                "daily_limit",
                0,
            )
            or 0
        ),
    )

    today = (
        datetime.now()
        .strftime("%Y-%m-%d")
    )

    used = (
        max(
            0,
            int(
                database_user.get(
                    "ai_usage_count",
                    0,
                )
                or 0
            ),
        )

        if database_user.get(
            "ai_usage_date"
        ) == today

        else 0
    )

    return {
        "enabled": bool(
            config.get("enabled")
        ),

        "banned": bool(
            banned
        ),

        "provider": config.get(
            "provider",
            "",
        ),

        "model": config.get(
            "model",
            "",
        ),

        "daily_limit": limit,

        "used_today": used,

        "remaining": (
            max(
                0,
                limit - used,
            )
            if limit
            else None
        ),

        "unlimited":
            limit == 0,

        "disabled_message":
            config.get(
                "disabled_message",
                "",
            ),
    }


@router.get("/history")
async def history(
    user=Depends(
        get_current_user
    ),
):
    items = await _get_history(
        user["id"]
    )

    return {
        "messages":
            public_history(items),
    }


@router.post("/ask")
async def ask(
    body: AskRequest,

    user=Depends(
        get_current_user
    ),
):
    user_id = user["id"]

    message = (
        body.message.strip()
    )

    if await db.ai_is_banned(
        user_id
    ):
        raise HTTPException(
            status_code=403,

            detail=(
                "دسترسی شما به هوشیار "
                "مسدود شده است"
            ),
        )

    if user_id in _busy_users:
        raise HTTPException(
            status_code=409,

            detail=(
                "پاسخ قبلی هنوز در حال "
                "آماده‌شدن است"
            ),
        )

    allowed, used, limit = (
        await check_and_consume_quota(
            user_id
        )
    )

    if not allowed:
        raise HTTPException(
            status_code=429,

            detail=(
                "سهمیه روزانه هوشیار "
                f"تمام شده است "
                f"({used}/{limit})"
            ),
        )

    _busy_users.add(
        user_id
    )

    try:
        history_items = (
            await _get_history(
                user_id
            )
        )

        answer, tokens = (
            await ask_ai(
                text=message,
                history=history_items,
                uid=user_id,
            )
        )

        answer = str(
            answer or ""
        ).strip()

        if not answer:
            raise HTTPException(
                status_code=502,

                detail=(
                    "هوشیار پاسخی "
                    "برنگرداند"
                ),
            )

        await _remember(
            user_id,
            "user",
            message,
        )

        await _remember(
            user_id,
            "assistant",
            answer,
        )

        await record_token_usage(
            user_id,
            int(tokens or 0),
        )

        return {
            "answer":
                answer,

            "tokens":
                int(tokens or 0),

            "used_today":
                used,

            "daily_limit":
                limit,

            "remaining": (
                max(
                    0,
                    limit - used,
                )
                if limit
                else None
            ),
        }

    except HTTPException:
        raise

    except AIError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        )

    except Exception:
        raise HTTPException(
            status_code=502,

            detail=(
                "ارتباط با سرویس "
                "هوش مصنوعی ناموفق بود"
            ),
        )

    finally:
        _busy_users.discard(
            user_id
        )


@router.delete("/history")
async def clear_history(
    user=Depends(
        get_current_user
    ),
):
    await _clear_memory(
        user["id"]
    )

    return {
        "ok": True,
    }


@router.post("/report")
async def report(
    body: ReportRequest,

    user=Depends(
        get_current_user
    ),
):
    database_user = user["_db"]

    await db.ai_log_report(
        user["id"],

        database_user.get(
            "name",
            "",
        ),

        body.question.strip(),

        body.answer.strip(),
    )

    return {
        "ok": True,
    }

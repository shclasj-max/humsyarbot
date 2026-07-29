"""Administrative controls for Hoshyar AI."""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from pydantic import (
    BaseModel,
    Field,
)

from api.auth import (
    get_admin_user,
)

from ai_solver import (
    AIError,
    ask_ai,
    get_ai_config,
    set_ai_setting,
)

from database import db


router = APIRouter()


class ConfigUpdate(BaseModel):
    enabled: bool

    provider: str = Field(
        pattern=(
            "^(gemini|openrouter)$"
        )
    )

    model: str = Field(
        min_length=2,
        max_length=150,
    )

    daily_limit: int = Field(
        ge=0,
        le=1000,
    )

    thinking: str = Field(
        pattern="^(auto|high)$"
    )

    system_prompt: str = Field(
        min_length=20,
        max_length=20000,
    )

    disabled_message: str = Field(
        default="",
        max_length=1000,
    )

    api_key: str | None = Field(
        default=None,
        max_length=500,
    )


class UserAction(BaseModel):
    user_id: int = Field(
        gt=0
    )


@router.get("/config")
async def config(
    admin=Depends(
        get_admin_user
    ),
):
    value = (
        await get_ai_config()
    )

    return {
        "enabled":
            value["enabled"],

        "provider":
            value["provider"],

        "model":
            value["model"],

        "daily_limit":
            value["daily_limit"],

        "thinking":
            value["thinking"],

        "system_prompt":
            value[
                "system_prompt"
            ],

        "disabled_message":
            value[
                "disabled_message"
            ],

        # کلید API هیچ‌وقت
        # به مرورگر ارسال نمی‌شود.
        "has_api_key":
            bool(
                value["api_key"]
            ),
    }


@router.put("/config")
async def update_config(
    body: ConfigUpdate,

    admin=Depends(
        get_admin_user
    ),
):
    editable_fields = (
        "enabled",
        "provider",
        "model",
        "daily_limit",
        "thinking",
        "system_prompt",
        "disabled_message",
    )

    for key in editable_fields:
        await set_ai_setting(
            key,
            getattr(body, key),
        )

    # فقط اگر کلید جدیدی وارد شده
    # باشد کلید قبلی جایگزین می‌شود.
    if (
        body.api_key
        and body.api_key.strip()
    ):
        await set_ai_setting(
            "api_key",
            body.api_key.strip(),
        )

    return {
        "ok": True,
    }


@router.get("/stats")
async def stats(
    admin=Depends(
        get_admin_user
    ),
):
    return await db.ai_usage_stats(
        10
    )


@router.get("/reports")
async def reports(
    limit: int = Query(
        default=30,
        ge=1,
        le=100,
    ),

    admin=Depends(
        get_admin_user
    ),
):
    items = (
        await db.ai_recent_reports(
            limit
        )
    )

    return {
        "reports": [
            {
                "id":
                    str(item["_id"]),

                "user_id":
                    item.get(
                        "user_id"
                    ),

                "name":
                    item.get(
                        "name",
                        "",
                    ),

                "question":
                    item.get(
                        "question",
                        "",
                    ),

                "answer":
                    item.get(
                        "answer",
                        "",
                    ),

                "created_at":
                    str(
                        item.get(
                            "created_at",
                            "",
                        )
                    )[:19],
            }

            for item in items
        ],
    }


@router.get("/banned")
async def banned(
    admin=Depends(
        get_admin_user
    ),
):
    items = (
        await db.ai_list_banned(
            100
        )
    )

    return {
        "users": [
            {
                "id":
                    item.get(
                        "user_id"
                    ),

                "name":
                    item.get(
                        "name",
                        "",
                    ),
            }

            for item in items
        ],
    }


@router.get("/users")
async def users(
    q: str = Query(
        ...,
        min_length=2,
        max_length=100,
    ),

    admin=Depends(
        get_admin_user
    ),
):
    items = (
        await db.search_users(
            q.strip()
        )
    )

    return {
        "users": [
            {
                "id":
                    item.get(
                        "user_id"
                    ),

                "name":
                    item.get(
                        "name",
                        "",
                    ),

                "banned":
                    bool(
                        item.get(
                            "ai_banned"
                        )
                    ),

                "usage_today":
                    item.get(
                        "ai_usage_count",
                        0,
                    ),

                "usage_total":
                    item.get(
                        "ai_total_usage",
                        0,
                    ),
            }

            for item in items

            if item.get(
                "approved"
            )
        ],
    }


@router.post("/users/ban")
async def toggle_ban(
    body: UserAction,

    admin=Depends(
        get_admin_user
    ),
):
    user = (
        await db.get_user(
            body.user_id
        )
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="کاربر پیدا نشد",
        )

    new_state = not bool(
        user.get("ai_banned")
    )

    await db.ai_set_banned(
        body.user_id,
        new_state,
    )

    return {
        "ok":
            True,

        "banned":
            new_state,
    }


@router.post(
    "/users/reset-quota"
)
async def reset_quota(
    body: UserAction,

    admin=Depends(
        get_admin_user
    ),
):
    result = (
        await db.users.update_one(
            {
                "user_id":
                    body.user_id,
            },

            {
                "$set": {
                    "ai_usage_count":
                        0,

                    "ai_tokens_today":
                        0,
                }
            },
        )
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="کاربر پیدا نشد",
        )

    return {
        "ok": True,
    }


@router.delete(
    "/users/{user_id}/profile"
)
async def clear_profile(
    user_id: int,

    admin=Depends(
        get_admin_user
    ),
):
    user = (
        await db.get_user(
            user_id
        )
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="کاربر پیدا نشد",
        )

    await db.ai_forget_profile(
        user_id
    )

    await db.ai_clear_memory(
        user_id
    )

    return {
        "ok": True,
    }


@router.post("/test")
async def test_connection(
    admin=Depends(
        get_admin_user
    ),
):
    try:
        answer, tokens = (
            await ask_ai(
                text=(
                    "فقط بنویس: "
                    "اتصال موفق است."
                ),

                history=[],

                uid=
                    admin["id"],
            )
        )

    except AIError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        )

    except Exception:
        raise HTTPException(
            status_code=502,

            detail=(
                "آزمایش اتصال "
                "ناموفق بود"
            ),
        )

    return {
        "ok":
            True,

        "answer":
            answer,

        "tokens":
            int(tokens or 0),
    }

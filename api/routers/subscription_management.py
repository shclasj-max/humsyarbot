"""Subscription administration endpoints."""

import re

from datetime import datetime

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

from api.telegram_send import (
    _send,
)

from api.routers.admin_panel import (
    _audit,
)

from database import db


router = APIRouter()


class PlanBody(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=100,
    )

    days: int = Field(
        ge=1,
        le=3650,
    )

    price: int = Field(
        ge=0,
        le=2_000_000_000,
    )


class DecisionBody(BaseModel):
    approved: bool

    note: str = Field(
        default="",
        max_length=500,
    )


class GrantBody(BaseModel):
    user_id: int = Field(
        gt=0
    )

    days: int = Field(
        ge=1,
        le=3650,
    )

    plan_name: str = Field(
        default="اشتراک دستی",
        max_length=100,
    )

    extend: bool = True


class RevokeBody(BaseModel):
    reason: str = Field(
        min_length=2,
        max_length=500,
    )


# ══════════════════════════════════════════════
# 🔎 جست‌وجوی یکپارچه — همان قرارداد سراسری
# db.build_user_search_query (نام، @یوزرنیم،
# شماره دانشجویی، آیدی عددی) که ربات و پنل
# کاربران هم از آن استفاده می‌کنند.
# ══════════════════════════════════════════════

async def _matched_user_ids(
    raw: str,
) -> list:
    """آیدی عددی کاربرانِ منطبق با عبارت جست‌وجو."""

    user_query = (
        db.build_user_search_query(
            raw
        )
    )

    if not user_query:
        return []

    matched = (
        await db.users.find(
            user_query,
            {'user_id': 1},
        ).to_list(500)
    )

    return [
        user['user_id']

        for user in matched

        if user.get('user_id')
        is not None
    ]


def _numeric_id_or_none(
    raw: str,
):
    """عبارت کاملاً عددی → int در غیر این صورت
    None — برای تطبیق مستقیم روی خودِ کالکشن
    (رسید/اشتراکِ کاربرِ حذف‌شده هم باید با
    آیدی عددی پیدا شود)."""

    if raw.lstrip('+-').isdigit():
        try:
            return int(raw)

        except (
            ValueError,
            OverflowError,
        ):
            return None

    return None


async def _payment_search_filter(
    search,
):
    """فیلتر $or رسیدها: کاربران منطبق + نام
    پلن + کد تخفیف + آیدی عددی مستقیم."""

    raw = (search or '').strip()

    if not raw:
        return None

    pattern = {
        '$regex':
            re.escape(raw),
        '$options': 'i',
    }

    or_parts = [
        {'plan_name': pattern},
        {'discount_code': pattern},
    ]

    ids = await _matched_user_ids(raw)

    if ids:
        or_parts.append(
            {'user_id': {'$in': ids}}
        )

    numeric = _numeric_id_or_none(raw)

    if numeric is not None:
        or_parts.append(
            {'user_id': numeric}
        )

    return {'$or': or_parts}


async def _subscriber_search_filter(
    search,
):
    """فیلتر $or مشترکین: کاربران منطبق (کلید
    اشتراک = user_id در فیلد _id) + نام پلن +
    آیدی عددی مستقیم."""

    raw = (search or '').strip()

    if not raw:
        return None

    pattern = {
        '$regex':
            re.escape(raw),
        '$options': 'i',
    }

    or_parts = [
        {'plan_name': pattern},
    ]

    ids = await _matched_user_ids(raw)

    if ids:
        or_parts.append(
            {'_id': {'$in': ids}}
        )

    numeric = _numeric_id_or_none(raw)

    if numeric is not None:
        or_parts.append(
            {'_id': numeric}
        )

    return {'$or': or_parts}


class DiscountBody(BaseModel):
    code: str = Field(
        min_length=2,
        max_length=40,
    )

    percent: int = Field(
        ge=1,
        le=100,
    )

    max_uses: int = Field(
        default=0,
        ge=0,
    )

    expires_at: str | None = None

    # 🎟 موج D1 — plan-targeting + per-user limit
    target_plan_ids: list[str] | None = None
    per_user_limit: int = Field(
        default=0,
        ge=0,
    )


class DiscountBroadcastBody(BaseModel):
    """بدنه‌ی درخواست انتشار کمپین کد تخفیف."""
    target: str = Field(
        default='all',
        pattern='^(all|subscribers|no_sub)$',
    )

    title: str | None = None
    description: str | None = None


class CardBody(BaseModel):
    card_number: str = Field(
        min_length=4,
        max_length=40,
    )

    card_owner: str = Field(
        min_length=2,
        max_length=100,
    )


@router.get("/overview")
async def overview(
    admin=Depends(
        get_admin_user
    ),
):
    stats = (
        await db.sub_stats()
    )

    plans = (
        await db.sub_plan_list()
    )

    card_number = (
        await db.get_setting(
            "subscription_card_number",
            "—",
        )
    )

    card_owner = (
        await db.get_setting(
            "subscription_card_owner",
            "—",
        )
    )

    return {
        "stats":
            stats,

        "plans": [
            {
                "id":
                    str(
                        plan["_id"]
                    ),

                "name":
                    plan.get(
                        "name",
                        "",
                    ),

                "days":
                    plan.get(
                        "days",
                        0,
                    ),

                "price":
                    plan.get(
                        "price",
                        0,
                    ),

                "active":
                    plan.get(
                        "active",
                        True,
                    ),
            }

            for plan in plans
        ],

        "card": {
            "card_number":
                card_number,

            "card_owner":
                card_owner,
        },
    }


@router.post("/plans")
async def add_plan(
    body: PlanBody,

    admin=Depends(
        get_admin_user
    ),
):
    plan_id = (
        await db.sub_plan_add(
            body.name.strip(),
            body.days,
            body.price,
        )
    )

    return {
        "ok":
            True,

        "id":
            plan_id,
    }


@router.post(
    "/plans/{plan_id}/toggle"
)
async def toggle_plan(
    plan_id: str,

    admin=Depends(
        get_admin_user
    ),
):
    changed = (
        await db.sub_plan_toggle(
            plan_id
        )
    )

    if not changed:
        raise HTTPException(
            status_code=404,
            detail="پلن پیدا نشد",
        )

    return {
        "ok": True,
    }


@router.delete(
    "/plans/{plan_id}"
)
async def delete_plan(
    plan_id: str,

    admin=Depends(
        get_admin_user
    ),
):
    plan = (
        await db.sub_plan_get(
            plan_id
        )
    )

    if not plan:
        raise HTTPException(
            status_code=404,
            detail="پلن پیدا نشد",
        )

    await db.sub_plan_delete(
        plan_id
    )

    return {
        "ok": True,
    }


@router.get("/payments")
async def payments(
    status: str | None = Query(
        default=None
    ),

    skip: int = Query(
        default=0,
        ge=0,
    ),

    limit: int = Query(
        default=30,
        ge=1,
        le=100,
    ),

    search: str | None = Query(
        default=None
    ),

    admin=Depends(
        get_admin_user
    ),
):
    extra = (
        await _payment_search_filter(
            search
        )
    )

    items = (
        await db
        .sub_payment_list_all(
            status=status,
            skip=skip,
            limit=limit,
            extra=extra,
        )
    )

    total = (
        await db
        .sub_payment_count_all(
            status=status,
            extra=extra,
        )
    )

    user_ids = list({
        item.get("user_id")

        for item in items

        if item.get("user_id")
    })

    if user_ids:
        users = (
            await db.users.find(
                {
                    "user_id": {
                        "$in":
                            user_ids,
                    }
                },

                {
                    "user_id": 1,
                    "name": 1,
                    "student_id": 1,
                    "username": 1,
                },
            )
            .to_list(
                len(user_ids)
            )
        )

    else:
        users = []

    users_map = {
        user["user_id"]:
            user

        for user in users
    }

    result = []

    for item in items:
        user_id = item.get(
            "user_id"
        )

        database_user = (
            users_map.get(
                user_id,
                {},
            )
        )

        result.append({
            "id":
                str(
                    item["_id"]
                ),

            "user_id":
                user_id,

            "user_name": (
                database_user.get(
                    "name"
                )
                or f"#{user_id}"
            ),

            "student_id":
                database_user.get(
                    "student_id",
                    "",
                ),

            "username": (
                database_user.get(
                    "username"
                )
                or ""
            ),

            "plan_id":
                item.get(
                    "plan_id",
                    "",
                ),

            "plan_name":
                item.get(
                    "plan_name",
                    "",
                ),

            "price":
                item.get(
                    "price",
                    0,
                ),

            "final_price":
                item.get(
                    "final_price",
                    item.get(
                        "price",
                        0,
                    ),
                ),

            "discount_code":
                item.get(
                    "discount_code",
                    "",
                ),

            "status":
                item.get(
                    "status",
                    "pending",
                ),

            "submitted_at":
                str(
                    item.get(
                        "submitted_at",
                        "",
                    )
                )[:16],

            "review_note":
                item.get(
                    "review_note",
                    "",
                ),
        })

    return {
        "total":
            total,

        "payments":
            result,
    }


@router.post(
    "/payments/{payment_id}/decision"
)
async def decide_payment(
    payment_id: str,

    body: DecisionBody,

    admin=Depends(
        get_admin_user
    ),
):
    payment = (
        await db.sub_payment_get(
            payment_id
        )
    )

    if not payment:
        raise HTTPException(
            status_code=404,
            detail="رسید پیدا نشد",
        )

    if (
        payment.get("status")
        != "pending"
    ):
        raise HTTPException(
            status_code=409,

            detail=(
                "این رسید قبلاً "
                "بررسی شده"
            ),
        )


    if body.approved:
        plan = (
            await db.sub_plan_get(
                str(
                    payment.get(
                        "plan_id",
                        "",
                    )
                )
            )
        )

        days = int(
            plan.get(
                "days",
                0,
            )
            if plan
            else 0
        )

        if days <= 0:
            raise HTTPException(
                status_code=422,

                detail=(
                    "مدت پلن "
                    "نامعتبر است"
                ),
            )

        await db.sub_activate(
            payment["user_id"],

            days,

            payment.get(
                "plan_name",
                "اشتراک",
            ),

            source=
                "payment",

            granted_by=
                admin["id"],

            extend=
                True,
        )


    await db.sub_payment_decide(
        payment_id,

        approved=
            body.approved,

        admin_id=
            admin["id"],

        note=
            body.note.strip(),
    )


    if not body.approved and payment.get("discount_code"):
        # 🎟 موج D1 — کد در ثبت رسید مصرف شده؛ در رد، ظرفیت برمی‌گردد
        await db.discount_release(
            payment["discount_code"], user_id=payment["user_id"]
        )


    notification_collection = (
        db.client[
            "medicalbot"
        ][
            "bot_notifications"
        ]
    )


    if body.approved:
        notification_text = (
            "✅ رسید شما تأیید و "
            "اشتراک فعال شد."
        )

    else:
        notification_text = (
            "❌ رسید شما رد شد."
        )

        if body.note.strip():
            notification_text += (
                f"\n{body.note.strip()}"
            )


    await notification_collection.insert_one({
        "type":
            "payment_decision",

        "chat_id":
            payment["user_id"],

        "text":
            notification_text,

        "sent":
            False,

        "created_at":
            datetime.now()
            .isoformat(),
    })


    return {
        "ok": True,
    }


@router.post(
    "/payments/{payment_id}/send-receipt"
)
async def send_receipt(
    payment_id: str,

    admin=Depends(
        get_admin_user
    ),
):
    payment = (
        await db.sub_payment_get(
            payment_id
        )
    )

    if (
        not payment
        or not payment.get(
            "screenshot_file_id"
        )
    ):
        raise HTTPException(
            status_code=404,

            detail=(
                "تصویر رسید موجود نیست"
            ),
        )


    sent = await _send(
        "sendDocument",

        {
            "chat_id":
                admin["id"],

            "document":
                payment[
                    "screenshot_file_id"
                ],

            "caption":
                f"رسید #{payment_id}",
        },
    )


    if not sent:
        raise HTTPException(
            status_code=502,

            detail=(
                "ارسال رسید ناموفق بود"
            ),
        )


    return {
        "ok": True,
    }


@router.get("/subscribers")
async def subscribers(
    status: str = Query(
        default="active"
    ),

    skip: int = Query(
        default=0,
        ge=0,
    ),

    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),

    search: str | None = Query(
        default=None
    ),

    admin=Depends(
        get_admin_user
    ),
):
    extra = (
        await _subscriber_search_filter(
            search
        )
    )

    items = (
        await db.sub_list_by_status(
            status,
            skip,
            limit,
            extra=extra,
        )
    )

    total = (
        await db
        .sub_count_by_status(
            status,
            extra=extra,
        )
    )

    user_ids = [
        item.get("_id")
        for item in items
    ]

    if user_ids:
        users = (
            await db.users.find(
                {
                    "user_id": {
                        "$in":
                            user_ids,
                    }
                },

                {
                    "user_id": 1,
                    "name": 1,
                    "student_id": 1,
                    "username": 1,
                },
            )
            .to_list(
                len(user_ids)
            )
        )

    else:
        users = []

    users_map = {
        user["user_id"]:
            user

        for user in users
    }

    result = []

    for item in items:
        user_id = item.get(
            "_id"
        )

        database_user = (
            users_map.get(
                user_id,
                {},
            )
        )

        result.append({
            "user_id":
                user_id,

            "name": (
                database_user.get(
                    "name"
                )
                or f"#{user_id}"
            ),

            "student_id":
                database_user.get(
                    "student_id",
                    "",
                ),

            "username": (
                database_user.get(
                    "username"
                )
                or ""
            ),

            "plan_name":
                item.get(
                    "plan_name",
                    "",
                ),

            "status":
                item.get(
                    "status",
                    "",
                ),

            "end_date":
                str(
                    item.get(
                        "end_date",
                        "",
                    )
                )[:10],
        })

    return {
        "total":
            total,

        "subscribers":
            result,
    }


@router.get(
    "/users/search"
)
async def search_users_for_grant(
    q: str = Query(
        default="",
        max_length=80,
    ),

    admin=Depends(
        get_admin_user
    ),
):
    """🔎 جست‌وجوی فشرده‌ی دانشجو برای
    «اعطای دستی» — همان موتور مشترک
    db.search_users (آیدی عددی دقیق،
    @یوزرنیم با/بدون @، نام و شماره
    دانشجویی) با خروجی سبک برای
    دراپ‌داون انتخاب."""

    raw = (q or "").strip()

    if len(raw) < 2:
        return {"users": []}

    results = (
        await db.search_users(
            raw,
            limit=8,
        )
    )

    return {
        "users": [
            {
                "id":
                    user.get(
                        "user_id"
                    ),

                "name":
                    user.get(
                        "name",
                        "",
                    ),

                "student_id":
                    user.get(
                        "student_id",
                        "",
                    ),

                "username":
                    user.get(
                        "username"
                    )
                    or "",
            }

            for user in results

            if user.get("user_id")
            is not None
        ]
    }


@router.post(
    "/subscribers/grant"
)
async def grant_subscription(
    body: GrantBody,

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


    end_date = (
        await db.sub_activate(
            body.user_id,

            body.days,

            body.plan_name
            .strip(),

            source=
                "manual",

            granted_by=
                admin["id"],

            extend=
                body.extend,
        )
    )


    return {
        "ok":
            True,

        "end_date":
            str(end_date)[:10],
    }


@router.post(
    "/subscribers/{user_id}/revoke"
)
async def revoke_subscription(
    user_id: int,

    body: RevokeBody,

    admin=Depends(
        get_admin_user
    ),
):
    revoked = (
        await db.sub_revoke(
            user_id,

            body.reason
            .strip(),

            admin["id"],
        )
    )

    if not revoked:
        raise HTTPException(
            status_code=404,

            detail=(
                "اشتراک پیدا نشد"
            ),
        )

    return {
        "ok": True,
    }


@router.get("/discounts")
async def discounts(
    admin=Depends(
        get_admin_user
    ),
):
    items = (
        await db.discount_list()
    )

    return {
        "discounts": [
            {
                "code":
                    item.get(
                        "code",
                        "",
                    ),

                "percent":
                    item.get(
                        "percent",
                        0,
                    ),

                "max_uses":
                    item.get(
                        "max_uses",
                        0,
                    ),

                "used_count":
                    item.get(
                        "used_count",
                        0,
                    ),

                "expires_at":
                    str(
                        item.get(
                            "expires_at",
                            "",
                        )
                        or ""
                    )[:10],

                "active":
                    item.get(
                        "active",
                        True,
                    ),

                "target_plan_ids":
                    item.get(
                        "target_plan_ids",
                        [],
                    )
                    or [],

                "per_user_limit":
                    item.get(
                        "per_user_limit",
                        0,
                    )
                    or 0,
            }

            for item in items
        ],
    }


@router.post("/discounts")
async def add_discount(
    body: DiscountBody,

    admin=Depends(
        get_admin_user
    ),
):
    created = (
        await db.discount_add(
            body.code,

            body.percent,

            body.max_uses,

            body.expires_at,

            admin["id"],

            body.target_plan_ids,

            body.per_user_limit,
        )
    )

    if not created:
        raise HTTPException(
            status_code=409,
            detail="کد تکراری است",
        )

    return {
        "ok": True,
    }


@router.post(
    "/discounts/{code}/toggle"
)
async def toggle_discount(
    code: str,

    admin=Depends(
        get_admin_user
    ),
):
    changed = (
        await db.discount_toggle(
            code
        )
    )

    if not changed:
        raise HTTPException(
            status_code=404,

            detail=(
                "کد پیدا نشد"
            ),
        )

    return {
        "ok": True,
    }


@router.delete(
    "/discounts/{code}"
)
async def delete_discount(
    code: str,

    admin=Depends(
        get_admin_user
    ),
):
    deleted = (
        await db.discount_delete(
            code
        )
    )

    if not deleted:
        raise HTTPException(
            status_code=404,

            detail=(
                "کد پیدا نشد"
            ),
        )

    return {
        "ok": True,
    }



# ══════════════════════════════════════════════════
#  🎟 موج D1 — کمپین تخفیف: Preview / Broadcast / Status / Stats
#  Bot و Mini App هر دو از همین API استفاده می‌کنند — Source of Truth
#  موتور تولید پیام: discount_campaign.py (Dynamic، بدون Hardcode)
# ══════════════════════════════════════════════════

async def _campaign_msg(discount: dict, title=None, description=None):
    from discount_campaign import build_campaign_message
    overrides = {}
    if title:
        overrides['title'] = title
    if description:
        overrides['description'] = description
    _, text = await build_campaign_message(db, discount, overrides=overrides or None)
    return text


@router.post("/discounts/{code}/preview")
async def preview_discount_campaign(
    code: str,

    admin=Depends(get_admin_user),
):
    discount = await db.discount_get(code)
    if not discount:
        raise HTTPException(status_code=404, detail="کد پیدا نشد")
    text = await _campaign_msg(discount)
    from discount_campaign import resolve_target_plans, campaign_cta_link
    plans = await resolve_target_plans(db, discount)
    return {
        "ok": True,
        "text": text,
        "plans": [{"id": str(p["_id"]), "name": p.get("name",""),
                   "days": p.get("days", 0), "price": p.get("price", 0)} for p in plans],
        "cta_link": campaign_cta_link(discount),
    }


@router.post("/discounts/{code}/broadcast")
async def start_discount_broadcast(
    code: str,

    body: DiscountBroadcastBody,

    admin=Depends(get_admin_user),
):
    from api.telegram_send import _send as _tg_send
    import asyncio as _asyncio

    discount = await db.discount_get(code)
    if not discount:
        raise HTTPException(status_code=404, detail="کد پیدا نشد")
    if not discount.get("active"):
        raise HTTPException(status_code=422, detail="این کد غیرفعال است — اول فعالش کن.")

    # ضد دابل‌کلیک: اگر broadcast همین کد در حال ارسال است
    active_bc = await db.discount_bcast_active_for(code)
    if active_bc:
        raise HTTPException(status_code=409, detail="انتشار قبلی همین کد هنوز در حال اجراست.")

    text = await _campaign_msg(discount, body.title, body.description)
    users = await db.discount_segment_users(body.target)
    # 🎚 ادغام نوتیفیکیشن: کاربرانی که دسته‌ی «🎁 تخفیف‌ها» را خاموش
    # کرده‌اند از ارسال DM کنار گذاشته می‌شوند
    try:
        _defaults = await db.get_notif_defaults()
        users = [u for u in users if db.notif_pref_on(
            u.get("notification_settings", {}), "discounts", _defaults)]
    except Exception:
        pass
    if not users:
        raise HTTPException(status_code=422,
            detail="هیچ مخاطبی در این بخش نیست (پس از اعمال ترجیحات اعلان کاربران).")

    from discount_campaign import campaign_cta_link
    from utils import webapp_url
    cta_url = webapp_url(campaign_cta_link(discount))
    kb_rows = []
    if cta_url:
        kb_rows.append([{
            "text": "🎟 دریافت اشتراک با تخفیف",
            "web_app": {"url": cta_url},
        }])
    kb_rows.append([
        {"text": "💳 تهیه اشتراک با تخفیف (در بات)",
         "callback_data": f"sub:dcode:{code}"}
    ])

    bid = await db.discount_bcast_create(code, body.target, admin["id"], source='web')
    await db.discount_bcast_update(bid, {"total": len(users)})

    await _audit(
        admin, "broadcast_started", "Discounts", severity="INFO",
        target_id=bid, target_type="broadcast", target_label=code,
        after={"code": code, "target": body.target, "total": len(users)},
        tags=["broadcast", "discount"],
    )

    async def _run():
        import os
        BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
        import httpx
        sent = failed = blocked = 0
        cancelled = False
        msg_refs = []  # ⛔ موج D2 — مرجع پیام‌های موفق برای ادیت «اتمام موجودی»
        base = f"https://api.telegram.org/bot{BOT_TOKEN}"
        reply_markup = {"inline_keyboard": kb_rows} if kb_rows else None
        async with httpx.AsyncClient(timeout=30) as cli:
            for i, u in enumerate(users):
                # ⛔ توقف: هر ۲۰ نفر وضعیت را از دیتابیس می‌خوانیم
                if i > 0 and i % 20 == 0:
                    cur = await db.discount_bcast_get(bid)
                    if cur and cur.get("status") == "cancelled":
                        cancelled = True
                        break
                uid = u["user_id"]
                payload = {
                    "chat_id": uid, "text": text, "parse_mode": "HTML",
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                outcome = "fail"  # ok | fail | blocked — شمارش دقیق هر کاربر
                for _attempt in range(3):
                    try:
                        r = await cli.post(f"{base}/sendMessage", json=payload)
                        if r.status_code == 200 and r.json().get("ok"):
                            outcome = "ok"
                            _mid = r.json().get("result", {}).get("message_id")
                            if _mid:
                                msg_refs.append({"c": uid, "m": _mid})
                            break
                        if r.status_code == 429:
                            # RetryAfter — صبر دقیق به اندازه‌ی اعلام تلگرام
                            ra = r.json().get("parameters", {}).get("retry_after", 2)
                            await _asyncio.sleep(ra + 0.5)
                            continue
                        if r.status_code == 403:
                            outcome = "blocked"
                            await db.mark_user_blocked(uid)
                            break
                        await _asyncio.sleep(1.2)
                        continue
                    except Exception:
                        await _asyncio.sleep(1.2)
                        continue
                if outcome == "ok":
                    sent += 1
                elif outcome == "blocked":
                    blocked += 1
                else:
                    failed += 1
                # گام‌بندی نرخ — الگوی _do_broadcast_send
                await _asyncio.sleep(0.05)
                if (i + 1) % 25 == 0 or (i + 1) == len(users):
                    if msg_refs:
                        try:
                            await db.discount_bcast_add_msgs(bid, msg_refs)
                        except Exception:
                            pass
                        msg_refs = []
                    await db.discount_bcast_update(bid, {
                        "sent": sent, "failed": failed, "blocked": blocked})
        # خالی‌کردن مراجع باقی‌مانده (در صورت توقف زودهنگام)
        if msg_refs:
            try:
                await db.discount_bcast_add_msgs(bid, msg_refs)
            except Exception:
                pass
        await db.discount_bcast_update(bid, {
            "status": "cancelled" if cancelled else "completed",
            "sent": sent, "failed": failed,
            "blocked": blocked, "finished_at": datetime.now().isoformat(),
        })
        if not cancelled:
            await _audit(
                admin, "broadcast_completed", "Discounts", severity="INFO",
                target_id=bid, target_type="broadcast", target_label=code,
                after={"sent": sent, "failed": failed, "blocked": blocked},
                tags=["broadcast", "discount"],
            )

    _asyncio.create_task(_run())
    return {"ok": True, "broadcast_id": bid, "total": len(users)}


@router.get("/discounts/{code}/broadcast/{bid}")
async def discount_broadcast_status(
    code: str, bid: str,

    admin=Depends(get_admin_user),
):
    bc = await db.discount_bcast_get(bid)
    if not bc or bc.get("code") != code:
        raise HTTPException(status_code=404, detail="broadcast پیدا نشد")
    return {
        "ok": True,
        "broadcast_id": bid,
        "status": bc.get("status"),
        "total": bc.get("total", 0),
        "sent": bc.get("sent", 0),
        "failed": bc.get("failed", 0),
        "blocked": bc.get("blocked", 0),
        "created_at": bc.get("created_at"),
        "finished_at": bc.get("finished_at"),
    }


@router.post("/discounts/{code}/broadcast/{bid}/cancel")
async def cancel_discount_broadcast(
    code: str, bid: str,

    admin=Depends(get_admin_user),
):
    bc = await db.discount_bcast_get(bid)
    if not bc or bc.get("code") != code:
        raise HTTPException(status_code=404, detail="broadcast پیدا نشد")
    if bc.get("status") != "sending":
        raise HTTPException(status_code=422, detail="این انتشار دیگر فعال نیست.")
    await db.discount_bcast_update(bid, {"status": "cancelled"})
    await _audit(
        admin, "broadcast_cancelled", "Discounts", severity="INFO",
        target_id=bid, target_type="broadcast", target_label=code,
    )
    return {"ok": True}


@router.get("/discounts/{code}/broadcasts")
async def discount_broadcasts_list(
    code: str,

    admin=Depends(get_admin_user),
):
    items = await db.discount_bcast_list(code, 10)
    return {
        "broadcasts": [
            {
                "broadcast_id": b.get("broadcast_id"),
                "status": b.get("status"),
                "target": b.get("target"),
                "total": b.get("total", 0),
                "sent": b.get("sent", 0),
                "failed": b.get("failed", 0),
                "blocked": b.get("blocked", 0),
                "created_at": b.get("created_at"),
                "finished_at": b.get("finished_at"),
            } for b in items
        ]
    }


@router.get("/discounts/{code}/stats")
async def discount_stats(
    code: str,

    admin=Depends(get_admin_user),
):
    discount = await db.discount_get(code)
    if not discount:
        raise HTTPException(status_code=404, detail="کد پیدا نشد")
    pay = await db.discount_payment_stats(code)
    mu = discount.get("max_uses", 0)
    used = discount.get("used_count", 0)
    remaining = max(0, mu - used) if mu > 0 else None
    targets = discount.get("target_plan_ids") or []
    plans_names = []
    if targets:
        plans = await db.sub_plan_list(only_active=False)
        plans_names = [p["name"] for p in plans if str(p["_id"]) in [str(t) for t in targets]]
    return {
        "ok": True,
        "code": code,
        "percent": discount.get("percent", 0),
        "used_count": used,
        "max_uses": mu,
        "remaining_uses": remaining,
        "target_plans": plans_names or None,
        "per_user_limit": discount.get("per_user_limit", 0),
        "expires_at": str(discount.get("expires_at", "") or "")[:10],
        "active": discount.get("active", True),
        "payments": pay,
    }


@router.put("/card")
async def update_card(
    body: CardBody,

    admin=Depends(
        get_admin_user
    ),
):
    await db.set_setting(
        "subscription_card_number",

        body.card_number
        .strip(),
    )

    await db.set_setting(
        "subscription_card_owner",

        body.card_owner
        .strip(),
    )

    return {
        "ok": True,
    }

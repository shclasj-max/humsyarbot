"""User subscription, discounts and payment receipt endpoints."""

import os

from datetime import datetime
from html import escape

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)

from pydantic import (
    BaseModel,
    Field,
)

from api.auth import (
    get_current_user,
)

from api.telegram_send import (
    upload_and_get_file_id,
)

from database import db


router = APIRouter()

MAX_RECEIPT_SIZE = (
    10 * 1024 * 1024
)


def normalize_plan(
    item: dict,
) -> dict:
    return {
        "id": str(
            item.get("_id", "")
        ),

        "name": str(
            item.get("name", "")
        ),

        "days": max(
            0,
            int(
                item.get(
                    "days",
                    0,
                )
                or 0
            ),
        ),

        "price": max(
            0,
            int(
                item.get(
                    "price",
                    0,
                )
                or 0
            ),
        ),
    }


def normalize_payment(
    item: dict,
) -> dict:
    status = item.get(
        "status",
        "pending",
    )

    labels = {
        "pending":
            "در انتظار بررسی",

        "approved":
            "تأییدشده",

        "rejected":
            "ردشده",
    }

    price = max(
        0,
        int(
            item.get(
                "price",
                0,
            )
            or 0
        ),
    )

    final_price = max(
        0,
        int(
            item.get(
                "final_price",
                price,
            )
            or 0
        ),
    )

    return {
        "id": str(
            item.get("_id", "")
        ),

        "plan_name":
            item.get(
                "plan_name",
                "",
            ),

        "price":
            price,

        "final_price":
            final_price,

        "discount_code":
            item.get(
                "discount_code",
                "",
            ),

        "status":
            status,

        "status_label":
            labels.get(
                status,
                status,
            ),

        "submitted_at":
            str(
                item.get(
                    "submitted_at",
                    "",
                )
            )[:16],

        "reviewed_at":
            str(
                item.get(
                    "reviewed_at",
                    "",
                )
            )[:16],

        "review_note":
            item.get(
                "review_note",
                "",
            ),
    }


@router.get("/status")
async def get_status(
    user=Depends(
        get_current_user
    ),
):
    user_id = user["id"]

    subscription = (
        await db.sub_get(
            user_id
        )
    )

    active = (
        await db.sub_is_active(
            user_id
        )
    )

    days_left = (
        await db.sub_days_left(
            user_id
        )
        if active
        else 0
    )

    plans = (
        await db.sub_plan_list(
            only_active=True
        )
    )

    history = (
        await db.sub_payment_history(
            user_id
        )
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

    # گیت از ماژول ربات — تک‌منبعِ قانون؛ فرانت فقط می‌خواند
    from subscription import (
        has_access,
    )

    resource_access = (
        await has_access(user_id)
    )

    enforced = bool(
        await db.get_setting(
            "subscription_enforced",
            False,
        )
    )

    has_pending = any(
        item.get("status")
        == "pending"

        for item in history
    )

    return {
        "active":
            active,

        "days_left":
            days_left,

        "plan_name": (
            subscription.get(
                "plan_name",
                "",
            )
            if subscription
            else ""
        ),

        "expires": (
            str(
                subscription.get(
                    "end_date",
                    "",
                )
            )[:10]
            if subscription
            else ""
        ),

        "has_pending_payment":
            has_pending,

        "resource_access":
            resource_access,

        "enforced":
            enforced,

        "plans": [
            normalize_plan(item)
            for item in plans
        ],

        "payments": [
            normalize_payment(item)
            for item in history
        ],

        "payment": {
            "card_number":
                card_number,

            "card_owner":
                card_owner,
        },
    }


class DiscountRequest(
    BaseModel
):
    plan_id: str = Field(
        min_length=24,
        max_length=24,
    )

    code: str = Field(
        min_length=1,
        max_length=40,
    )


@router.post("/discount")
async def validate_discount(
    body: DiscountRequest,

    user=Depends(
        get_current_user
    ),
):
    plan = (
        await db.sub_plan_get(
            body.plan_id
        )
    )

    if (
        not plan
        or not plan.get("active")
    ):
        raise HTTPException(
            status_code=404,
            detail="پلن پیدا نشد",
        )

    code = (
        body.code
        .strip()
        .upper()
    )

    result = (
        await db.discount_validate(
            code
        )
    )

    if not result.get("ok"):
        raise HTTPException(
            status_code=422,

            detail=result.get(
                "reason",
                "کد تخفیف معتبر نیست",
            ),
        )

    price = max(
        0,
        int(
            plan.get(
                "price",
                0,
            )
            or 0
        ),
    )

    percent = max(
        0,
        min(
            100,
            int(
                result.get(
                    "percent",
                    0,
                )
                or 0
            ),
        ),
    )

    final_price = round(
        price
        * (
            100 - percent
        )
        / 100
    )

    return {
        "ok":
            True,

        "code":
            code,

        "percent":
            percent,

        "price":
            price,

        "final_price":
            final_price,
    }


@router.post("/buy")
async def buy(
    plan_id: str = Form(...),

    discount_code: str = Form(
        ""
    ),

    receipt: UploadFile | None = File(
        default=None
    ),

    user=Depends(
        get_current_user
    ),
):
    user_id = user["id"]

    database_user = user["_db"]

    plan = (
        await db.sub_plan_get(
            plan_id
        )
    )

    if (
        not plan
        or not plan.get("active")
    ):
        raise HTTPException(
            status_code=404,
            detail="پلن پیدا نشد",
        )

    has_pending = (
        await db
        .sub_payment_has_pending(
            user_id
        )
    )

    if has_pending:
        raise HTTPException(
            status_code=409,

            detail=(
                "یک رسید قبلی در "
                "انتظار بررسی دارید"
            ),
        )


    price = max(
        0,
        int(
            plan.get(
                "price",
                0,
            )
            or 0
        ),
    )

    final_price = price

    code = (
        discount_code
        .strip()
        .upper()
        or None
    )


    if code:
        validation = (
            await db
            .discount_validate(
                code
            )
        )

        if not validation.get(
            "ok"
        ):
            raise HTTPException(
                status_code=422,

                detail=validation.get(
                    "reason",
                    "کد تخفیف معتبر نیست",
                ),
            )

        percent = max(
            0,
            min(
                100,
                int(
                    validation.get(
                        "percent",
                        0,
                    )
                    or 0
                ),
            ),
        )

        final_price = round(
            price
            * (
                100 - percent
            )
            / 100
        )


    # تخفیف صددرصدی:
    # بدون رسید و تأیید ادمین
    if final_price <= 0:
        end_date = (
            await db.sub_activate(
                user_id,

                int(
                    plan.get(
                        "days",
                        0,
                    )
                    or 0
                ),

                plan.get(
                    "name",
                    "اشتراک",
                ),

                source=
                    "discount",

                granted_by=
                    0,

                extend=
                    True,
            )
        )

        payment_id = (
            await db
            .sub_payment_create(
                user_id=
                    user_id,

                plan_id=
                    plan_id,

                plan_name=
                    plan.get(
                        "name",
                        "",
                    ),

                price=
                    price,

                final_price=
                    0,

                screenshot_file_id=
                    "",

                discount_code=
                    code,
            )
        )

        await db.sub_payment_decide(
            payment_id,

            approved=True,

            admin_id=0,

            note=
                "تخفیف ۱۰۰٪",
        )

        if code:
            await db.discount_consume(
                code
            )

        return {
            "ok":
                True,

            "activated":
                True,

            "payment_id":
                payment_id,

            "expires":
                str(end_date)[:10],

            "message":
                "اشتراک رایگان فعال شد.",
        }


    # برای پرداخت معمولی
    # تصویر رسید الزامی است
    if receipt is None:
        raise HTTPException(
            status_code=422,

            detail=(
                "تصویر رسید پرداخت "
                "الزامی است"
            ),
        )


    content_type = (
        receipt.content_type
        or ""
    )

    if not content_type.startswith(
        "image/"
    ):
        raise HTTPException(
            status_code=422,

            detail=(
                "رسید باید فایل "
                "تصویری باشد"
            ),
        )


    raw = await receipt.read()

    if not raw:
        raise HTTPException(
            status_code=422,

            detail=(
                "فایل رسید خالی است"
            ),
        )


    if (
        len(raw)
        > MAX_RECEIPT_SIZE
    ):
        raise HTTPException(
            status_code=413,

            detail=(
                "حجم رسید بیشتر از "
                "۱۰ مگابایت است"
            ),
        )


    file_id = (
        await upload_and_get_file_id(
            user_id,

            receipt.filename
            or "receipt.jpg",

            raw,

            content_type
            or "image/jpeg",
        )
    )


    if not file_id:
        raise HTTPException(
            status_code=502,

            detail=(
                "آپلود رسید در "
                "تلگرام ناموفق بود"
            ),
        )


    payment_id = (
        await db.sub_payment_create(
            user_id=
                user_id,

            plan_id=
                plan_id,

            plan_name=
                plan.get(
                    "name",
                    "",
                ),

            price=
                price,

            final_price=
                final_price,

            screenshot_file_id=
                file_id,

            discount_code=
                code,
        )
    )


    if code:
        await db.discount_consume(
            code
        )


    try:
        notification_collection = (
            db.client[
                "medicalbot"
            ][
                "bot_notifications"
            ]
        )

        admin_id = int(
            os.getenv(
                "ADMIN_ID",
                "0",
            )
        )

        safe_payment_id = escape(
            payment_id
        )

        safe_name = escape(
            str(
                database_user.get(
                    "name",
                    "",
                )
            )
        )

        safe_plan = escape(
            str(
                plan.get(
                    "name",
                    "",
                )
            )
        )

        await (
            notification_collection
            .insert_one({
                "type":
                    "payment_request",

                "chat_id":
                    admin_id,

                "text": (
                    f"💳 <b>رسید جدید "
                    f"#{safe_payment_id}</b>"

                    f"\n👤 {safe_name}"

                    f"\n📦 {safe_plan}"

                    f"\n💰 "
                    f"{final_price:,} "
                    f"تومان"
                ),

                "sent":
                    False,

                "created_at":
                    datetime.now()
                    .isoformat(),
            })
        )

    except Exception:
        # ثبت رسید نباید به‌خاطر
        # خطای اعلان ادمین شکست بخورد
        pass


    return {
        "ok":
            True,

        "activated":
            False,

        "payment_id":
            payment_id,

        "price":
            price,

        "final_price":
            final_price,

        "plan_name":
            plan.get(
                "name",
                "",
            ),

        "message": (
            "رسید ثبت شد و در "
            "انتظار بررسی مدیریت است."
        ),
    }

"""Subscription administration endpoints."""

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

    admin=Depends(
        get_admin_user
    ),
):
    items = (
        await db
        .sub_payment_list_all(
            status=status,
            skip=skip,
            limit=limit,
        )
    )

    total = (
        await db
        .sub_payment_count_all(
            status=status
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

    admin=Depends(
        get_admin_user
    ),
):
    items = (
        await db.sub_list_by_status(
            status,
            skip,
            limit,
        )
    )

    total = (
        await db
        .sub_count_by_status(
            status
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

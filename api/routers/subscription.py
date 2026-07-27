"""💳 Subscription"""
import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from api.auth import get_current_user
from database import db

router = APIRouter()

@router.get("/status")
async def get_status(user=Depends(get_current_user)):
    uid    = user["id"]
    sub    = await db.sub_get(uid)
    active = await db.sub_is_active(uid)
    days   = await db.sub_days_left(uid) if active else 0
    plans  = await db.sub_plan_list(only_active=True)
    try: pending = await db.sub_payment_has_pending(uid)
    except Exception: pending = False
    return {
        "active": active, "days_left": days,
        "plan_name": sub.get("plan_name","") if sub else "",
        "expires": sub.get("expires_at","")[:10] if sub else "",
        "has_pending_payment": pending,
        "plans": [{"id":str(p["_id"]),"name":p.get("name",""),
            "days":p.get("days",0),"price":p.get("price",0)} for p in plans],
    }

class BuyRequest(BaseModel):
    plan_id: str
    discount_code: Optional[str] = None

@router.post("/buy")
async def buy(body: BuyRequest, user=Depends(get_current_user)):
    uid = user["id"]; db_user = user["_db"]
    plan = await db.sub_plan_get(body.plan_id)
    if not plan: raise HTTPException(404,"پلن پیدا نشد")
    try:
        pending = await db.sub_payment_has_pending(uid)
        if pending: raise HTTPException(400,"یک درخواست در انتظار دارید")
    except HTTPException: raise
    except Exception: pass
    price = plan.get("price",0)
    pid = await db.sub_payment_create(user_id=uid, plan_id=body.plan_id,
        plan_name=plan.get("name",""), price=price,
        name=db_user.get("name",""), student_id=db_user.get("student_id",""))
    try:
        notif = db.client["medicalbot"]["bot_notifications"]
        await notif.insert_one({"type":"payment_request","chat_id":int(os.getenv("ADMIN_ID","0")),
            "text":f"💳 <b>درخواست خرید ({db_user.get('name','')})</b>\n📦 {plan.get('name','')} — {price:,} تومان\n🆔 {pid}",
            "sent":False,"created_at":datetime.now().isoformat()})
    except Exception: pass
    return {"ok":True,"payment_id":pid,"price":price,"plan_name":plan.get("name",""),
        "message":"درخواست ثبت شد — رسید پرداخت را از ربات ارسال کنید."}

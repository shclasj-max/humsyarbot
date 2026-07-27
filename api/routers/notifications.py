"""🔔 Notifications"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Dict
from api.auth import get_current_user
from database import db

router = APIRouter()
NOTIF_ITEMS = [
    ("new_resources","📚 منابع جدید","وقتی محتوای جدید آپلود شود"),
    ("schedule","📅 برنامه","افزودن کلاس یا تغییر زمان"),
    ("exam","📝 یادآوری امتحان","۷، ۳ و ۱ روز قبل"),
    ("makeup","🔄 کلاس جبرانی","وقتی جبرانی ثبت شود"),
    ("daily_question","🧪 سوال روزانه","هر روز صبح"),
    ("edu_message","🎓 پیام آموزشی","نکات آموزشی"),
    ("general","📢 اطلاعیه","اخبار کلی"),
    ("grade_release","📊 اعلام نمرات","وقتی نمره ثبت شود"),
    ("sub_expiry","💳 انقضای اشتراک","۷ و ۳ روز قبل"),
]

@router.get("/settings")
async def get_settings(user=Depends(get_current_user)):
    s = user["_db"].get("notification_settings",{})
    return {"settings":[{"key":k,"label":l,"desc":d,"enabled":s.get(k,True)} for k,l,d in NOTIF_ITEMS]}

class Toggle(BaseModel):
    settings: Dict[str,bool]

@router.patch("/settings")
async def update(body: Toggle, user=Depends(get_current_user)):
    valid = {k for k,_,_ in NOTIF_ITEMS}
    updates = {f"notification_settings.{k}":v for k,v in body.settings.items() if k in valid}
    if updates: await db.update_user(user["id"], updates)
    return {"ok":True}

class ToggleAll(BaseModel):
    enabled: bool

@router.patch("/settings/all")
async def toggle_all(body: ToggleAll, user=Depends(get_current_user)):
    updates = {f"notification_settings.{k}":body.enabled for k,_,_ in NOTIF_ITEMS}
    await db.update_user(user["id"], updates)
    return {"ok":True,"enabled":body.enabled}

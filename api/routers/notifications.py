"""🔔 Notifications"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
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


# ══════════════════════════════════════════════════
#  🔔 مرکز اعلان (inbox) — موج ۴.۹۰
#  منبع داده: همان رویدادهایی که در ربات برای کاربر پیام می‌شوند
#  (jobs + پنل‌ها) و از طریق db.inbox_add* ثبت شده‌اند.
# ══════════════════════════════════════════════════

@router.get("/inbox")
async def get_inbox(user=Depends(get_current_user)):
    """فهرست اعلان‌ها + شمارش خوانده‌نشده (بج و صفحه یک پاسخ مشترک دارند)"""
    return await db.inbox_list(user["id"], limit=60)

class InboxRead(BaseModel):
    # None → خواندن همه («خواندن همه» از کلاینت ids=null می‌فرستد؛
    # در pydantic v2 باید صراحتاً Optional باشد وگرنه 422 می‌شد)
    ids: Optional[List[str]] = None

@router.post("/inbox/read")
async def mark_read(body: InboxRead, user=Depends(get_current_user)):
    unread = await db.inbox_mark_read(user["id"], body.ids)
    return {"ok": True, "unread": unread}

@router.delete("/inbox/{nid}")
async def delete_inbox(nid: str, user=Depends(get_current_user)):
    ok = await db.inbox_delete(user["id"], nid)
    if not ok: raise HTTPException(404, "اعلان پیدا نشد")
    return {"ok": True}

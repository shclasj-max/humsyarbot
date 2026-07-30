"""🎫 Tickets"""
import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from api.auth import get_current_user
from database import db

router = APIRouter()
SUBJECTS = ["🔬 مشکل در منابع","🧪 مشکل در بانک سوال","💳 مشکل اشتراک","📊 مشکل نمرات","👤 مشکل حساب","⚙️ مشکل فنی","💡 پیشنهاد","❓ سوال دیگر"]

def _fmt(t, detail=False):
    replies = t.get("replies",[])
    r = {"id":t.get("ticket_id"),"subject":t.get("subject",""),"status":t.get("status","open"),
        "created_at":t.get("created_at","")[:10],"reply_count":len(replies)}
    if detail:
        r["message"] = t.get("message","")
        r["replies"] = [{"text":rep.get("text","").removeprefix("[دانشجو]").strip(),
            "sender":"user" if rep.get("text","").startswith("[دانشجو]") else "support",
            "at":rep.get("at","")[:16]} for rep in replies]
    return r

@router.get("")
async def list_tickets(user=Depends(get_current_user)):
    tickets = await db.ticket_get_user(user["id"])
    return {"tickets":[_fmt(t) for t in tickets],"subjects":SUBJECTS}

@router.get("/unread-count")
async def unread_count(user=Depends(get_current_user)):
    """تعداد تیکت‌هایی که آخرین پاسخ‌دهنده‌شان «پشتیبانی» است و کاربر
    بعد از آن وارد گفت‌وگو نشده — برای Badge قرمز BottomNav.

    قرارداد: باز کردن صفحه گفت‌وگوی تیکت، user_seen_at را به‌روز می‌کند
    (در GET /{tid}). اگر خود کاربر آخرین پاسخ را داده باشد، چیزی برای
    خواندن نیست و تیکت، خوانده‌نشده محسوب نمی‌شود.
    """
    tickets = await db.tickets.find(
        {"user_id": user["id"]},
        {"replies": 1, "user_seen_at": 1, "ticket_id": 1},
    ).to_list(30)

    count = 0
    for t in tickets or []:
        replies = t.get("replies") or []
        if not replies:
            continue
        last = replies[-1]
        if last.get("text", "").startswith("[دانشجو]"):
            continue                    # آخرین پاسخ از خود کاربره
        if last.get("at", "") > (t.get("user_seen_at") or ""):
            count += 1

    return {"unread": count}

@router.get("/{tid}")
async def get_ticket(tid: int, user=Depends(get_current_user)):
    ticket = await db.ticket_get(tid)
    if not ticket: raise HTTPException(404,"پیدا نشد")
    if ticket["user_id"] != user["id"]: raise HTTPException(403)
    # باز شدن گفت‌وگو = خوانده شدن پاسخ‌های پشتیبانی
    await db.tickets.update_one(
        {"ticket_id": tid},
        {"$set": {"user_seen_at": datetime.now().isoformat()}},
    )
    return {"ticket":_fmt(ticket,detail=True)}

class NewTicket(BaseModel):
    subject: str; message: str

@router.post("")
async def create_ticket(body: NewTicket, user=Depends(get_current_user)):
    uid = user["id"]; db_user = user["_db"]
    if len(body.message.strip()) < 10: raise HTTPException(422,"متن کوتاه است")
    tid = await db.ticket_create(uid, db_user.get("name",""), body.subject, body.message.strip())
    try:
        notif = db.client["medicalbot"]["bot_notifications"]
        await notif.insert_one({"type":"new_ticket","chat_id":int(os.getenv("ADMIN_ID","0")),
            "text":f"🔔 <b>تیکت #{tid}</b>\n👤 {db_user.get('name','')}\n📋 {body.subject}\n\n{body.message.strip()[:200]}",
            "sent":False,"created_at":datetime.now().isoformat()})
    except Exception: pass
    return {"ok":True,"ticket_id":tid}

class ReplyBody(BaseModel):
    message: str

@router.post("/{tid}/reply")
async def reply(tid: int, body: ReplyBody, user=Depends(get_current_user)):
    ticket = await db.ticket_get(tid)
    if not ticket: raise HTTPException(404)
    if ticket["user_id"] != user["id"]: raise HTTPException(403)
    if ticket.get("status") == "closed": raise HTTPException(400,"تیکت بسته است")
    msg = body.message.strip()
    if not msg: raise HTTPException(422)
    await db.ticket_add_reply(tid, f"[دانشجو] {msg}")
    try:
        notif = db.client["medicalbot"]["bot_notifications"]
        await notif.insert_one({"type":"ticket_reply","chat_id":int(os.getenv("ADMIN_ID","0")),
            "text":f"💬 <b>پاسخ دانشجو #{tid}</b>\n{msg[:200]}",
            "sent":False,"created_at":datetime.now().isoformat()})
    except Exception: pass
    return {"ok":True}

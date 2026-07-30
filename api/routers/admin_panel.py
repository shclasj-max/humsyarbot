"""👑 Admin Panel"""
import asyncio
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from api.auth import get_admin_user
from database import db

router = APIRouter()
ADMIN_ID = int(os.getenv("ADMIN_ID","0"))


def _notify(chat_id: int, text: str, ntype: str = "admin_notice"):
    notif = db.client["medicalbot"]["bot_notifications"]
    return notif.insert_one({"type":ntype,"chat_id":chat_id,"text":text,
        "sent":False,"created_at":datetime.now().isoformat()})


async def _audit(admin, action: str, module: str, *, severity: str = "INFO",
                 target_id: str = "", target_type: str = "",
                 target_label: str = "", details: str = "",
                 before: dict = None, after: dict = None,
                 tags: list = None):
    """ثبت رویداد در audit_logs برای اقدامات انجام‌شده از پنل وب.

    مقادیر به‌صورت موضعی (positional) به db.log_action داده می‌شوند تا
    دقیقاً با امضای موجود در database.py سازگار بمانند. هر خطایی در لاگ
    نباید اقدام اصلی را شکست دهد، پس در try/except قرار گرفته است.
    """
    try:
        actor = admin.get("_db") or {}
        await db.log_action(
            actor.get("user_id", admin.get("id", 0)),
            actor.get("name", "مدیر ارشد"),
            actor.get("role", "admin"),
            action, module, "admin", severity,
            str(target_id), target_type, target_label,
            before, after, details, tags,
        )
    except Exception:
        pass


@router.get("/stats")
async def stats(admin=Depends(get_admin_user)):
    return {
        "users":{"total":await db.users.count_documents({"approved":True}),"pending":await db.users.count_documents({"approved":False})},
        "questions":{"approved":await db.questions.count_documents({"approved":True}),"pending":await db.questions.count_documents({"approved":False})},
        "tickets":{"open":await db.tickets.count_documents({"status":"open"})},
        "reports":{"open":await db.content_reports.count_documents({"status":"new"})},
        "subscriptions":{"active":0},
    }

@router.get("/bot-status")
async def bot_status(admin=Depends(get_admin_user)):
    import time
    db_ping="—"; db_status="❌"
    try:
        t0=time.monotonic(); await db.client.admin.command("ping")
        db_ping=f"{int((time.monotonic()-t0)*1000)} ms"; db_status="✅ متصل"
    except Exception as e: db_status=f"❌ {str(e)[:40]}"
    sys_info={}
    try:
        import psutil, os as _os
        proc=psutil.Process(_os.getpid()); mem=proc.memory_info().rss/1024/1024
        vm=psutil.virtual_memory(); cpu=psutil.cpu_percent(interval=0.2)
        up=time.time()-proc.create_time(); h,r=divmod(int(up),3600); m,s=divmod(r,60)
        sys_info={"bot_ram_mb":round(mem,1),"total_ram_mb":round(vm.total/1024/1024),
            "used_ram_pct":vm.percent,"cpu_pct":cpu,"uptime":f"{h}h {m}m" if h else f"{m}m {s}s"}
    except Exception: pass
    return {"db_status":db_status,"db_ping":db_ping,"sys":sys_info}

# ══════════════════════════════════════════════
# 👥 کاربران
# ══════════════════════════════════════════════

@router.get("/users")
async def list_users(admin=Depends(get_admin_user), search: Optional[str]=Query(None),
                      group: Optional[str]=Query(None), intake: Optional[str]=Query(None)):
    q={}
    if search:
        import re; pat=re.compile(re.escape(search),re.IGNORECASE)
        q["$or"]=[{"name":pat},{"student_id":pat},{"username":pat}]
    if group: q["group"]=group
    if intake: q["intake"]=intake
    users = await db.users.find(q).sort("registered_at",-1).to_list(500)
    return {"users":[{"id":u.get("user_id"),"name":u.get("name",""),"student_id":u.get("student_id",""),
        "group":u.get("group",""),"intake":u.get("intake",""),"role":u.get("role","student"),
        "approved":u.get("approved",False),"suspended":u.get("suspended",False),
        "registered_at":u.get("registered_at","")[:10],"total_answers":u.get("total_answers",0)} for u in users]}

@router.get("/users/pending")
async def pending_users(admin=Depends(get_admin_user)):
    users = await db.pending_users()
    return {"users":[{"id":u.get("user_id"),"name":u.get("name",""),"student_id":u.get("student_id",""),
        "group":u.get("group",""),"intake":u.get("intake",""),"registered_at":u.get("registered_at","")[:10]} for u in users]}

@router.get("/users/{uid}")
async def user_detail(uid: int, admin=Depends(get_admin_user)):
    u = await db.get_user(uid)
    if not u: raise HTTPException(404, "کاربر پیدا نشد")
    return {"user":{"id":u.get("user_id"),"name":u.get("name",""),"student_id":u.get("student_id",""),
        "group":u.get("group",""),"intake":u.get("intake",""),"role":u.get("role","student"),
        "approved":u.get("approved",False),"suspended":u.get("suspended",False),
        "registered_at":u.get("registered_at","")[:10],"total_answers":u.get("total_answers",0),
        "correct_answers":u.get("correct_answers",0),"downloads":u.get("downloads",0)}}

@router.post("/users/{uid}/approve")
async def approve(uid: int, admin=Depends(get_admin_user)):
    user = await db.get_user(uid)
    if not user: raise HTTPException(404)
    await db.update_user(uid,{"approved":True})
    _notify(uid, "✅ <b>حساب شما تأیید شد!</b>\n\nاکنون می‌توانید از هامزیار استفاده کنید.\n/start بزنید.", "user_approved")
    await _audit(admin, "تأیید حساب کاربر", "Users", severity="INFO",
        target_id=uid, target_type="user", target_label=user.get("name",""),
        tags=["تأیید_کاربر","پنل_وب"])
    return {"ok":True}

@router.post("/users/{uid}/reject")
async def reject(uid: int, admin=Depends(get_admin_user)):
    user = await db.get_user(uid)
    await db.users.delete_one({"user_id":uid})
    await _audit(admin, "رد درخواست عضویت", "Users", severity="WARNING",
        target_id=uid, target_type="user",
        target_label=(user or {}).get("name",""),
        tags=["رد_کاربر","پنل_وب"])
    return {"ok":True}

@router.post("/users/{uid}/suspend")
async def suspend(uid: int, admin=Depends(get_admin_user)):
    if uid == ADMIN_ID: raise HTTPException(403,"نمی‌توانید ادمین را تعلیق کنید")
    user = await db.get_user(uid)
    if not user: raise HTTPException(404)
    suspended = not user.get("suspended",False)
    await db.update_user(uid,{"suspended":suspended, "approved": not suspended})
    if suspended:
        _notify(uid, "⚠️ دسترسی شما موقتاً تعلیق شد.", "user_suspended")
    await _audit(admin,
        "تعلیق حساب کاربر" if suspended else "رفع تعلیق حساب کاربر",
        "Users", severity="HIGH" if suspended else "INFO",
        target_id=uid, target_type="user", target_label=user.get("name",""),
        before={"suspended":not suspended}, after={"suspended":suspended},
        tags=["تعلیق_کاربر","پنل_وب"])
    return {"ok":True,"suspended":suspended}

@router.post("/users/{uid}/delete")
async def delete_user_ep(uid: int, admin=Depends(get_admin_user)):
    if uid == ADMIN_ID: raise HTTPException(403,"نمی‌توانید ادمین ارشد را حذف کنید")
    user = await db.get_user(uid)
    if not user: raise HTTPException(404)
    _notify(uid, "❌ حساب شما حذف شد.", "user_deleted")
    await db.delete_user(uid)
    await _audit(admin, "حذف حساب کاربر", "Users", severity="CRITICAL",
        target_id=uid, target_type="user", target_label=user.get("name",""),
        tags=["حذف_کاربر","پنل_وب"])
    return {"ok":True}

@router.post("/users/{uid}/block")
async def block_user_ep(uid: int, admin=Depends(get_admin_user)):
    if uid == ADMIN_ID: raise HTTPException(403,"نمی‌توانید ادمین ارشد را بلاک کنید")
    user = await db.get_user(uid)
    if not user: raise HTTPException(404)
    actor_name = admin["_db"].get("name","مدیر ارشد")
    await db.block_user(uid, blocked_by=admin["id"], blocked_by_name=actor_name)
    await db.blacklist.update_one({"_id":uid},{"$set":{"name":user.get("name","")}})
    _notify(uid, "🚫 حساب شما مسدود شد و امکان ثبت‌نام مجدد ندارید.", "user_blocked")
    await _audit(admin, "مسدودسازی کاربر (بلک‌لیست)", "Users", severity="CRITICAL",
        target_id=uid, target_type="user", target_label=user.get("name",""),
        tags=["بلاک_کاربر","پنل_وب"])
    return {"ok":True}

@router.post("/users/{uid}/unblock")
async def unblock_user_ep(uid: int, admin=Depends(get_admin_user)):
    ok = await db.unblock_user(uid)
    if not ok: raise HTTPException(404,"این آیدی در بلک‌لیست نبود")
    await _audit(admin, "رفع مسدودیت کاربر", "Users", severity="HIGH",
        target_id=uid, target_type="user", tags=["آنبلاک_کاربر","پنل_وب"])
    return {"ok":True}

@router.get("/blacklist")
async def blacklist(admin=Depends(get_admin_user)):
    items = await db.get_blacklist()
    return {"blacklist":[{"id":b.get("_id"),"name":b.get("name",""),
        "blocked_by_name":b.get("blocked_by_name",""),"blocked_at":str(b.get("blocked_at",""))[:10]} for b in items]}

# ══════════════════════════════════════════════
# 🎓 ادمین‌های محتوا
# ══════════════════════════════════════════════

@router.get("/content-admins")
async def content_admins_list(admin=Depends(get_admin_user)):
    admins = await db.get_content_admins()
    return {"admins":[{"id":a.get("user_id"),"name":a.get("name","")} for a in admins]}

@router.post("/content-admins/{uid}")
async def grant_content_admin(uid: int, admin=Depends(get_admin_user)):
    user = await db.get_user(uid)
    if not user: raise HTTPException(404)
    await db.update_user(uid,{"role":"content_admin"})
    _notify(uid, "🎓 <b>دسترسی ادمین محتوا به شما داده شد!</b>", "content_admin_granted")
    await _audit(admin, "اعطای دسترسی مدیر محتوا", "Roles", severity="HIGH",
        target_id=uid, target_type="user", target_label=user.get("name",""),
        tags=["اعطای_نقش","پنل_وب"])
    return {"ok":True}

@router.delete("/content-admins/{uid}")
async def revoke_content_admin(uid: int, admin=Depends(get_admin_user)):
    await db.update_user(uid,{"role":"student"})
    _notify(uid, "⚠️ دسترسی ادمین محتوای شما لغو شد.", "content_admin_revoked")
    await _audit(admin, "لغو دسترسی مدیر محتوا", "Roles", severity="HIGH",
        target_id=uid, target_type="user",
        tags=["لغو_نقش","پنل_وب"])
    return {"ok":True}

@router.get("/students")
async def students_list(admin=Depends(get_admin_user), q: Optional[str]=Query(None)):
    users = await db.all_users(approved_only=True)
    students = [u for u in users if u.get("role","student")=="student"]
    if q:
        ql=q.lower()
        students=[u for u in students if ql in u.get("name","").lower() or ql in u.get("student_id","").lower()]
    return {"students":[{"id":u.get("user_id"),"name":u.get("name",""),"group":u.get("group","")} for u in students[:50]]}

# ══════════════════════════════════════════════
# ✏️ ویرایش کاربر
# ══════════════════════════════════════════════

class UserPatch(BaseModel):
    name: Optional[str]=None; group: Optional[str]=None
    intake: Optional[str]=None; student_id: Optional[str]=None
    role: Optional[str]=None

@router.patch("/users/{uid}")
async def edit_user(uid: int, body: UserPatch, admin=Depends(get_admin_user)):
    updates={}
    if body.name       is not None: updates["name"]=body.name.strip()
    if body.group      is not None: updates["group"]=body.group
    if body.intake     is not None: updates["intake"]=body.intake
    if body.student_id is not None: updates["student_id"]=body.student_id.strip()
    if body.role       is not None:
        if body.role not in ("student","content_admin","support"): raise HTTPException(422,"نقش نامعتبر")
        updates["role"]=body.role
    if updates:
        await db.update_user(uid,updates)
        await _audit(admin, "ویرایش اطلاعات کاربر", "Users", severity="WARNING",
            target_id=uid, target_type="user",
            details=" / ".join(f"{k}: {v}" for k, v in updates.items())[:400],
            tags=["ویرایش_کاربر","پنل_وب"])
    return {"ok":True}

# ══════════════════════════════════════════════
# 📅 ورودی‌ها (Intakes)
# ══════════════════════════════════════════════

@router.get("/intakes")
async def intakes_list(admin=Depends(get_admin_user)):
    items = await db.get_all_intakes()
    result=[]
    for i in items:
        st = await db.intake_stats(i.get("code",""))
        result.append({"code":i.get("code",""),"label":i.get("label",""),
            "active":i.get("active",True),"total":st.get("total",0),"groups":st.get("groups",{})})
    return {"intakes":result}

class IntakeCreate(BaseModel):
    code: str; label: str

@router.post("/intakes")
async def add_intake_ep(body: IntakeCreate, admin=Depends(get_admin_user)):
    code=body.code.strip(); label=body.label.strip()
    if not code or not label: raise HTTPException(422,"کد و برچسب الزامی است")
    await db.add_intake(code, label)
    await _audit(admin, "افزودن ورودی جدید", "Users", severity="INFO",
        target_id=code, target_type="intake", target_label=label,
        tags=["ورودی","پنل_وب"])
    return {"ok":True}

@router.post("/intakes/{code}/toggle")
async def toggle_intake_ep(code: str, admin=Depends(get_admin_user)):
    new_state = await db.toggle_intake(code)
    await _audit(admin,
        "فعال‌سازی پذیرش ورودی" if new_state else "توقف پذیرش ورودی",
        "Users", severity="WARNING",
        target_id=code, target_type="intake",
        tags=["ورودی","پنل_وب"])
    return {"ok":True,"active":new_state}

@router.delete("/intakes/{code}")
async def delete_intake_ep(code: str, admin=Depends(get_admin_user)):
    await db.delete_intake(code)
    await _audit(admin, "حذف ورودی", "Users", severity="HIGH",
        target_id=code, target_type="intake", tags=["ورودی","پنل_وب"])
    return {"ok":True}

# ══════════════════════════════════════════════
# 🎫 تیکت‌ها
# ══════════════════════════════════════════════

@router.get("/tickets")
async def all_tickets(admin=Depends(get_admin_user), status: Optional[str]=Query(None)):
    tickets = await db.ticket_get_all(status=status)
    return {"tickets":[{"id":t.get("ticket_id"),"user_name":t.get("user_name",""),"subject":t.get("subject",""),
        "status":t.get("status","open"),"reply_count":len(t.get("replies",[])),"created_at":t.get("created_at","")[:10]} for t in tickets]}

@router.get("/tickets/{tid}")
async def ticket_detail(tid: int, admin=Depends(get_admin_user)):
    t = await db.ticket_get(tid)
    if not t: raise HTTPException(404)
    uid=t.get("user_id"); u=await db.get_user(uid) if uid else None
    replies=[{"text":r.get("text","").removeprefix("[دانشجو]").strip(),
        "sender":"user" if r.get("text","").startswith("[دانشجو]") else "support","at":r.get("at","")[:16]} for r in t.get("replies",[])]
    return {"ticket":{"id":t.get("ticket_id"),"subject":t.get("subject",""),"message":t.get("message",""),
        "status":t.get("status","open"),"created_at":t.get("created_at","")[:10],"replies":replies,
        "user":{"id":uid,"name":t.get("user_name",""),"student_id":u.get("student_id","") if u else "","group":u.get("group","") if u else "","intake":u.get("intake","") if u else ""}}}

class AdminReply(BaseModel):
    message: str

@router.post("/tickets/{tid}/reply")
async def admin_reply(tid: int, body: AdminReply, admin=Depends(get_admin_user)):
    t=await db.ticket_get(tid)
    if not t: raise HTTPException(404)
    if t.get("status")=="closed": raise HTTPException(400)
    msg=body.message.strip()
    if not msg: raise HTTPException(422)
    await db.ticket_add_reply(tid, msg)
    _notify(t["user_id"], f"💬 <b>پاسخ پشتیبانی #{tid}</b>\n{msg}", "ticket_admin_reply")
    await _audit(admin, "پاسخ به تیکت پشتیبانی", "Tickets", severity="INFO",
        target_id=tid, target_type="ticket", target_label=t.get("subject",""),
        tags=["تیکت","پنل_وب"])
    return {"ok":True}

@router.post("/tickets/{tid}/close")
async def close_ticket(tid: int, admin=Depends(get_admin_user)):
    await db.ticket_close(tid)
    await _audit(admin, "بستن تیکت", "Tickets", severity="INFO",
        target_id=tid, target_type="ticket", tags=["تیکت","پنل_وب"])
    return {"ok":True}

@router.post("/tickets/{tid}/reopen")
async def reopen_ticket(tid: int, admin=Depends(get_admin_user)):
    await db.ticket_reopen(tid)
    await _audit(admin, "بازگشایی تیکت", "Tickets", severity="INFO",
        target_id=tid, target_type="ticket", tags=["تیکت","پنل_وب"])
    return {"ok":True}

# ══════════════════════════════════════════════
# 📢 Broadcast پیشرفته — preview / تأیید / زمان‌دار / هدفمند
# ══════════════════════════════════════════════

class BroadcastTarget(BaseModel):
    scope: str = "all"                    # all | intake | intake_group
    intake: Optional[str] = None
    group: Optional[str] = None           # "1" | "2"

async def _resolve_broadcast_users(target: BroadcastTarget):
    users = await db.all_users(approved_only=True)
    if target.scope == "intake" and target.intake:
        users = [u for u in users if u.get("intake") == target.intake]
    elif target.scope == "intake_group" and target.intake and target.group:
        users = [u for u in users if u.get("intake") == target.intake and u.get("group") == target.group]
    return [u for u in users if u.get("user_id") != ADMIN_ID]

class BroadcastPreview(BaseModel):
    target: BroadcastTarget

@router.post("/broadcast/preview")
async def broadcast_preview(body: BroadcastPreview, admin=Depends(get_admin_user)):
    users = await _resolve_broadcast_users(body.target)
    return {"recipient_count": len(users)}

class BroadcastSend(BaseModel):
    text: str
    target: BroadcastTarget
    send_at: Optional[str] = None   # ISO datetime — اگه خالی باشه فوری ارسال می‌شه

@router.post("/broadcast")
async def broadcast(body: BroadcastSend, admin=Depends(get_admin_user)):
    text = body.text.strip()
    if len(text) < 5: raise HTTPException(422, "متن پیام خیلی کوتاهه")
    if body.send_at:
        try: datetime.fromisoformat(body.send_at)
        except ValueError: raise HTTPException(422, "فرمت زمان نامعتبر است")
    users = await _resolve_broadcast_users(body.target)
    notif = db.client["medicalbot"]["bot_notifications"]
    doc_base = {"type":"broadcast","text":text,"sent":False,"created_at":datetime.now().isoformat()}
    if body.send_at: doc_base["send_at"] = body.send_at
    docs = [{**doc_base, "chat_id": u["user_id"]} for u in users]
    if docs: await notif.insert_many(docs)
    await _audit(admin, "ارسال همگانی" + (" (زمان‌دار)" if body.send_at else ""),
        "Notifications", severity="HIGH",
        target_type="broadcast", target_label=f"{len(docs)} گیرنده",
        details=text[:300],
        tags=["ارسال_همگانی","پنل_وب"])
    return {"ok":True, "queued": len(docs), "scheduled": bool(body.send_at)}

@router.get("/broadcast/history")
async def broadcast_history(admin=Depends(get_admin_user), limit: int=Query(20)):
    notif = db.client["medicalbot"]["bot_notifications"]
    pipeline = [
        {"$match": {"type": "broadcast"}},
        {"$group": {"_id": {"text":"$text","created_at":"$created_at"},
            "total": {"$sum": 1}, "sent": {"$sum": {"$cond": ["$sent", 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$failed", True]}, 1, 0]}}}},
        {"$sort": {"_id.created_at": -1}}, {"$limit": limit},
    ]
    rows = await notif.aggregate(pipeline).to_list(limit)
    return {"history":[{"text":r["_id"]["text"][:80],"created_at":r["_id"]["created_at"],
        "total":r["total"],"sent":r["sent"],"failed":r["failed"]} for r in rows]}

# ══════════════════════════════════════════════
# 📊 نظرسنجی کانال
# ══════════════════════════════════════════════

@router.get("/poll/status")
async def poll_status(admin=Depends(get_admin_user)):
    channel_id = await db.get_setting("poll_channel_id", None)
    return {"channel_id": channel_id, "configured": bool(channel_id)}

class PollChannelSet(BaseModel):
    channel_id: str

@router.post("/poll/channel")
async def poll_channel_set(body: PollChannelSet, admin=Depends(get_admin_user)):
    await db.set_setting("poll_channel_id", body.channel_id.strip())
    return {"ok":True}

class PollCreate(BaseModel):
    question: str; options: List[str]; anonymous: bool = False

@router.post("/poll")
async def poll_create(body: PollCreate, admin=Depends(get_admin_user)):
    if len(body.options) < 2: raise HTTPException(422, "حداقل ۲ گزینه لازم است")
    channel_id = await db.get_setting("poll_channel_id", None)
    if not channel_id: raise HTTPException(400, "کانال نظرسنجی تنظیم نشده — اول از بخش تنظیمات کانال رو وارد کن")
    from api.telegram_send import BOT_TOKEN, API_BASE
    import httpx
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(f"{API_BASE}/sendPoll", json={
            "chat_id": channel_id, "question": body.question, "options": body.options,
            "is_anonymous": body.anonymous, "allows_multiple_answers": False,
        })
    data = resp.json()
    if not data.get("ok"):
        raise HTTPException(502, f"ارسال ناموفق — مطمئن شو ربات ادمین کانال هست ({data.get('description','')})")
    await _audit(admin, "ایجاد نظرسنجی در کانال", "Notifications", severity="INFO",
        target_type="poll", target_label=body.question[:100],
        tags=["نظرسنجی","پنل_وب"])
    return {"ok":True}

# ══════════════════════════════════════════════
# 🔔 مدیریت اعلان‌ها — فاصله زمانی / تاریخچه / retry
# ══════════════════════════════════════════════

@router.get("/notifications/settings")
async def notif_settings(admin=Depends(get_admin_user)):
    interval = await db.get_setting("resource_notif_interval_hours", 24)
    last_sent = await db.get_setting("resource_notif_last_sent", None)
    last_error = await db.get_setting("resource_notif_last_error", None)
    return {"interval_hours": interval, "last_sent": last_sent, "last_error": last_error}

class NotifSettingsUpdate(BaseModel):
    interval_hours: int

@router.post("/notifications/settings")
async def notif_settings_update(body: NotifSettingsUpdate, admin=Depends(get_admin_user)):
    if body.interval_hours not in (24, 48, 72): raise HTTPException(422, "مقدار مجاز: ۲۴، ۴۸ یا ۷۲")
    old = await db.get_setting("resource_notif_interval_hours", 24)
    await db.set_setting("resource_notif_interval_hours", body.interval_hours)
    await _audit(admin, "تغییر فاصله اعلان منابع", "Settings", severity="WARNING",
        target_type="settings",
        before={"فاصله(ساعت)": old}, after={"فاصله(ساعت)": body.interval_hours},
        tags=["تنظیمات_اعلان","پنل_وب"])
    return {"ok":True}

@router.get("/notifications/history")
async def notif_history(admin=Depends(get_admin_user), job_name: Optional[str]=Query(None), limit: int=Query(15)):
    runs = await db.get_recent_notif_runs(job_name=job_name, limit=limit)
    return {"runs":[{"id":str(r["_id"]),"job_name":r.get("job_name",""),"status":r.get("status",""),
        "sent":r.get("sent",0),"failed":r.get("failed",0),"total":r.get("total",0),
        "started_at":r.get("started_at",""),"finished_at":r.get("finished_at")} for r in runs]}

@router.post("/notifications/history/{run_id}/retry")
async def notif_retry(run_id: str, admin=Depends(get_admin_user)):
    targets = await db.get_failed_notif_details(run_id)
    if not targets: raise HTTPException(404, "موردی برای تلاش مجدد پیدا نشد")
    notif = db.client["medicalbot"]["bot_notifications"]
    docs = [{"type":"notif_retry","chat_id":t["user_id"],"text":t["message"],"sent":False,
        "created_at":datetime.now().isoformat()} for t in targets if t.get("message")]
    if docs: await notif.insert_many(docs)
    return {"ok":True, "requeued": len(docs)}

@router.post("/export/excel")
async def export_excel(admin=Depends(get_admin_user)):
    _notify(ADMIN_ID, "__EXCEL_EXPORT__", "excel_export_request")
    return {"ok":True,"message":"📊 فایل اکسل از طریق ربات ارسال می‌شود."}

# ══════════════════════════════════════════════
# 🛡 لاگ فعالیت مدیران (نمایش در پنل وب)
# ══════════════════════════════════════════════

@router.get("/audit-logs")
async def audit_logs_admin(
    admin=Depends(get_admin_user),
    category: Optional[str] = Query(None),
    min_severity: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
):
    """فهرست لاگ فعالیت با فیلتر دسته/سطح/جست‌وجو + شمارنده سطوح.

    داده همان audit_logs مشترک با بات است؛ اکشن‌های ثبت‌شده از پنل وب
    (تگ «پنل_وب») و اکشن‌های بات هر دو اینجا دیده می‌شوند.
    """
    query = {}
    if category in ("admin", "content"):
        query["category"] = category
    if min_severity:
        order = ["INFO", "WARNING", "HIGH", "CRITICAL"]
        idx = order.index(min_severity) if min_severity in order else 0
        query["severity"] = {"$in": order[idx:]}
    if q:
        import re
        pat = re.compile(re.escape(q), re.IGNORECASE)
        query["$or"] = [
            {"action": pat},
            {"actor.name": pat},
            {"target.label": pat},
            {"details": pat},
            {"module": pat},
        ]

    total = await db.audit_logs.count_documents(query)

    # شمارنده سطوح (با همان فیلترهای دسته/جست‌وجو، بدون فیلتر سطح)
    counter_query = {k: v for k, v in query.items() if k != "severity"}
    sev_counts = await db.audit_logs.aggregate([
        {"$match": counter_query},
        {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
    ]).to_list(10)
    counters = {
        r["_id"]: r["count"] for r in sev_counts if r.get("_id")
    }

    rows = await db.audit_logs.find(query).sort(
        "timestamp", -1
    ).skip(skip).limit(limit).to_list(limit)

    logs = [{
        "id": str(r.get("_id")),
        "timestamp": r.get("timestamp", ""),
        "severity": r.get("severity", "INFO"),
        "category": r.get("category", "admin"),
        "module": r.get("module", ""),
        "action": r.get("action", ""),
        "actor": r.get("actor") or {},
        "target": r.get("target") or {},
        "details": r.get("details", ""),
        "changes": r.get("changes") or [],
        "tags": r.get("tags") or [],
    } for r in rows]

    return {"logs": logs, "total": total, "counters": counters}

# ══════════════════════════════════════════════
# 📊 آمار تحلیلی (نمودارهای پنل وب)
# ══════════════════════════════════════════════

@router.get("/analytics")
async def analytics_admin(
    admin=Depends(get_admin_user),
    days: int = Query(14, ge=7, le=90),
):
    """آمار روزانه بازه اخیر + کاربران فعال + توزیع عملیات و ساعات اوج.

    timestamp ها به‌صورت رشته ISO ذخیره می‌شوند، پس تاریخ روز با
    $substrBytes روی ۱۰ کاراکتر اول استخراج می‌شود (سازگار با الگوی
    موجود در database.py).
    """
    since = (datetime.now() - timedelta(days=days)).isoformat()

    async def _daily(col, ts_field):
        expr = {"$substrBytes": [f"${ts_field}", 0, 10]}
        rows = await col.aggregate([
            {"$match": {ts_field: {"$gte": since}}},
            {"$group": {"_id": expr, "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]).to_list(days + 2)
        return [{"date": r["_id"], "count": r["count"]}
                for r in rows if r.get("_id")]

    users_daily, activity_daily, tickets_daily = (
        await asyncio.gather(
            _daily(db.users, "registered_at"),
            _daily(db.stats_col, "timestamp"),
            _daily(db.tickets, "created_at"),
        )
    )

    # KPI ها
    active_uids = await db.stats_col.distinct(
        "user_id", {"timestamp": {"$gte": since}}
    )
    new_users = await db.users.count_documents(
        {"registered_at": {"$gte": since}}
    )
    total_actions = await db.stats_col.count_documents(
        {"timestamp": {"$gte": since}}
    )
    new_tickets = await db.tickets.count_documents(
        {"created_at": {"$gte": since}}
    )
    open_reports = await db.content_reports.count_documents(
        {"status": "new"}
    )

    # پرکاربردترین عملیات‌ها
    top_actions_rows = await db.stats_col.aggregate([
        {"$match": {"timestamp": {"$gte": since}}},
        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 8},
    ]).to_list(8)
    top_actions = [
        {"action": r["_id"] or "نامشخص", "count": r["count"]}
        for r in top_actions_rows
    ]

    # ساعت‌های اوج فعالیت (ساعت از کاراکترهای ۱۱ تا ۱۳ رشته ISO)
    hourly_rows = await db.stats_col.aggregate([
        {"$match": {"timestamp": {"$gte": since}}},
        {"$group": {
            "_id": {"$substrBytes": ["$timestamp", 11, 2]},
            "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 6},
    ]).to_list(6)
    hourly = sorted(
        [{"hour": int(r["_id"]), "count": r["count"]}
         for r in hourly_rows
         if r.get("_id") and str(r["_id"]).isdigit()],
        key=lambda x: x["hour"],
    )

    return {
        "days": days,
        "kpis": {
            "active_users": len(active_uids),
            "new_users": new_users,
            "total_actions": total_actions,
            "new_tickets": new_tickets,
            "open_reports": open_reports,
        },
        "daily": {
            "users": users_daily,
            "activity": activity_daily,
            "tickets": tickets_daily,
        },
        "top_actions": top_actions,
        "hourly": hourly,
    }

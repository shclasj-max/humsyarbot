"""👑 Admin Panel"""
import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from api.auth import get_admin_user
from database import db

router = APIRouter()
ADMIN_ID = int(os.getenv("ADMIN_ID","0"))

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

@router.get("/users")
async def list_users(admin=Depends(get_admin_user), search: Optional[str]=Query(None)):
    q={}
    if search:
        import re; pat=re.compile(re.escape(search),re.IGNORECASE)
        q["$or"]=[{"name":pat},{"student_id":pat}]
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

@router.post("/users/{uid}/approve")
async def approve(uid: int, admin=Depends(get_admin_user)):
    user = await db.get_user(uid)
    if not user: raise HTTPException(404)
    await db.update_user(uid,{"approved":True})
    try:
        notif = db.client["medicalbot"]["bot_notifications"]
        await notif.insert_one({"type":"user_approved","chat_id":uid,
            "text":"✅ <b>حساب شما تأیید شد!</b>\n\nاکنون می‌توانید از همیار استفاده کنید.\n/start بزنید.",
            "sent":False,"created_at":datetime.now().isoformat()})
    except Exception: pass
    return {"ok":True}

@router.post("/users/{uid}/reject")
async def reject(uid: int, admin=Depends(get_admin_user)):
    await db.users.delete_one({"user_id":uid}); return {"ok":True}

@router.post("/users/{uid}/suspend")
async def suspend(uid: int, admin=Depends(get_admin_user)):
    if uid == ADMIN_ID: raise HTTPException(403,"نمی‌توانید ادمین را تعلیق کنید")
    user = await db.get_user(uid)
    if not user: raise HTTPException(404)
    suspended = not user.get("suspended",False)
    await db.update_user(uid,{"suspended":suspended})
    return {"ok":True,"suspended":suspended}

class UserPatch(BaseModel):
    group: Optional[str]=None; intake: Optional[str]=None; role: Optional[str]=None

@router.patch("/users/{uid}")
async def edit_user(uid: int, body: UserPatch, admin=Depends(get_admin_user)):
    updates={}
    if body.group  is not None: updates["group"]=body.group
    if body.intake is not None: updates["intake"]=body.intake
    if body.role   is not None:
        if body.role not in ("student","content_admin","support"): raise HTTPException(422)
        updates["role"]=body.role
    if updates: await db.update_user(uid,updates)
    return {"ok":True}

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
    try:
        notif = db.client["medicalbot"]["bot_notifications"]
        await notif.insert_one({"type":"ticket_admin_reply","chat_id":t["user_id"],
            "text":f"💬 <b>پاسخ پشتیبانی #{tid}</b>\n{msg}",
            "sent":False,"created_at":datetime.now().isoformat()})
    except Exception: pass
    return {"ok":True}

@router.post("/tickets/{tid}/close")
async def close_ticket(tid: int, admin=Depends(get_admin_user)):
    await db.ticket_close(tid); return {"ok":True}

@router.post("/tickets/{tid}/reopen")
async def reopen_ticket(tid: int, admin=Depends(get_admin_user)):
    await db.ticket_reopen(tid); return {"ok":True}

class BroadcastBody(BaseModel):
    text: str; target: str="all"

@router.post("/broadcast")
async def broadcast(body: BroadcastBody, admin=Depends(get_admin_user)):
    text=body.text.strip()
    if len(text)<5: raise HTTPException(422)
    q={"approved":True}
    if body.target=="group_1": q["group"]="1"
    elif body.target=="group_2": q["group"]="2"
    users=await db.users.find(q).to_list(5000)
    notif=db.client["medicalbot"]["bot_notifications"]
    docs=[{"type":"broadcast","chat_id":u["user_id"],"text":text,"sent":False,
        "created_at":datetime.now().isoformat()} for u in users if u.get("user_id")!=ADMIN_ID]
    if docs: await notif.insert_many(docs)
    return {"ok":True,"queued":len(docs)}

@router.post("/export/excel")
async def export_excel(admin=Depends(get_admin_user)):
    notif=db.client["medicalbot"]["bot_notifications"]
    await notif.insert_one({"type":"excel_export_request","chat_id":ADMIN_ID,
        "text":"__EXCEL_EXPORT__","sent":False,"created_at":datetime.now().isoformat()})
    return {"ok":True,"message":"📊 فایل اکسل از طریق ربات ارسال می‌شود."}

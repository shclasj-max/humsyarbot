"""🎓 Content Admin"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from api.auth import get_content_admin_user
from database import db

router = APIRouter()

@router.get("/overview")
async def overview(admin=Depends(get_content_admin_user)):
    return {"pending_questions":await db.questions.count_documents({"approved":False}),
        "approved_questions":await db.questions.count_documents({"approved":True}),
        "total_resources":await db.bs_content.count_documents({}),
        "upcoming_exams":0,"total_faq":0}

@router.get("/questions/pending")
async def pending_questions(admin=Depends(get_content_admin_user)):
    docs=await db.questions.find({"approved":False}).sort("created_at",-1).to_list(100)
    return {"questions":[{"id":str(d["_id"]),"lesson":d.get("lesson",""),"topic":d.get("topic",""),
        "difficulty":d.get("difficulty",""),"question":d.get("question",""),"options":d.get("options",[]),
        "correct":d.get("correct_answer",0),"explanation":d.get("explanation",""),
        "creator_name":d.get("creator_name",""),"created_at":d.get("created_at","")[:10],
        "source":d.get("source","bot")} for d in docs]}

@router.post("/questions/{qid}/approve")
async def approve_question(qid: str, admin=Depends(get_content_admin_user)):
    q=await db.get_question_by_id(qid)
    if not q: raise HTTPException(404)
    await db.approve_question(qid)
    if q.get("source")=="webapp" and q.get("creator_id"):
        try:
            notif=db.client["medicalbot"]["bot_notifications"]
            await notif.insert_one({"type":"question_approved","chat_id":q["creator_id"],
                "text":f"✅ <b>سوال شما تأیید شد!</b>\n📚 {q.get('lesson','')} — {q.get('topic','')}",
                "sent":False,"created_at":datetime.now().isoformat()})
        except Exception: pass
    return {"ok":True}

@router.post("/questions/{qid}/reject")
async def reject_question(qid: str, admin=Depends(get_content_admin_user)):
    q=await db.get_question_by_id(qid)
    if not q: raise HTTPException(404)
    await db.delete_question(qid)
    if q.get("source")=="webapp" and q.get("creator_id"):
        try:
            notif=db.client["medicalbot"]["bot_notifications"]
            await notif.insert_one({"type":"question_rejected","chat_id":q["creator_id"],
                "text":f"❌ <b>سوال شما رد شد</b>\n📚 {q.get('lesson','')} — {q.get('topic','')}",
                "sent":False,"created_at":datetime.now().isoformat()})
        except Exception: pass
    return {"ok":True}

@router.get("/schedule")
async def schedule_list(admin=Depends(get_content_admin_user), stype: Optional[str]=Query(None)):
    items=await db.get_schedules(stype=stype, upcoming=False)
    return {"schedule":[{"id":str(s["_id"]),"type":s.get("type",""),"lesson":s.get("lesson",""),
        "teacher":s.get("teacher",""),"date":s.get("date",""),"time":s.get("time",""),
        "group":s.get("group",""),"note":s.get("note","")} for s in items]}

class ScheduleCreate(BaseModel):
    type: str; lesson: str; teacher: str=""; date: str; time: str=""; group: str="0"; note: str=""

@router.post("/schedule")
async def add_schedule(body: ScheduleCreate, admin=Depends(get_content_admin_user)):
    if body.type not in ("class","exam","makeup"): raise HTTPException(422)
    try: datetime.strptime(body.date,"%Y-%m-%d")
    except ValueError: raise HTTPException(422,"فرمت تاریخ YYYY-MM-DD")
    await db.add_schedule(stype=body.type,lesson=body.lesson,teacher=body.teacher,
        date=body.date,time=body.time,location="",notes=body.note)
    try:
        users=await db.notif_users("schedule")
        notif=db.client["medicalbot"]["bot_notifications"]
        icon={"class":"🏫","exam":"📝","makeup":"🔄"}.get(body.type,"📅")
        type_fa={"class":"کلاس","exam":"امتحان","makeup":"جبرانی"}.get(body.type,"")
        docs=[{"type":"schedule_notif","chat_id":u["user_id"],
            "text":f"{icon} <b>{type_fa} جدید</b>\n📚 {body.lesson}" + (f"\n👨‍🏫 {body.teacher}" if body.teacher else "") + f"\n📅 {body.date}",
            "sent":False,"created_at":datetime.now().isoformat()} for u in users]
        if docs: await notif.insert_many(docs)
    except Exception: pass
    return {"ok":True}

@router.delete("/schedule/{sid}")
async def del_schedule(sid: str, admin=Depends(get_content_admin_user)):
    try: await db.delete_schedule(sid)
    except Exception: raise HTTPException(404)
    return {"ok":True}

@router.get("/faq")
async def faq_list(admin=Depends(get_content_admin_user)):
    docs=await db.faq_get_all()
    return {"items":[{"id":str(d["_id"]),"category":d.get("category","عمومی"),
        "question":d.get("question",""),"answer":d.get("answer","")} for d in docs]}

class FaqCreate(BaseModel):
    category: str="عمومی"; question: str=Field(min_length=5); answer: str=Field(min_length=5)

@router.post("/faq")
async def add_faq(body: FaqCreate, admin=Depends(get_content_admin_user)):
    await db.faq_add(body.question, body.answer, body.category); return {"ok":True}

@router.delete("/faq/{fid}")
async def del_faq(fid: str, admin=Depends(get_content_admin_user)):
    try: await db.faq_delete(fid)
    except Exception: raise HTTPException(404)
    return {"ok":True}

class GradeBulk(BaseModel):
    entries: List[dict]; lesson: str; exam_title: str; exam_date: str; max_score: float=20.0

@router.post("/grades/bulk")
async def bulk_grades(body: GradeBulk, admin=Depends(get_content_admin_user)):
    count=await db.grade_bulk_upsert(entries=body.entries,lesson=body.lesson,
        exam_title=body.exam_title,exam_date=body.exam_date,max_score=body.max_score)
    return {"ok":True,"updated":count}

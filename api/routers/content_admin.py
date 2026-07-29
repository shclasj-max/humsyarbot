"""🎓 Content Admin"""
import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Optional, List
from api.auth import get_content_admin_user
from api.telegram_send import upload_and_get_file_id
from database import db

router = APIRouter()
TERMS = ['ترم ۱', 'ترم ۲', 'ترم ۳', 'ترم ۴', 'ترم ۵']
CONTENT_TYPES = ['video', 'ppt', 'pdf', 'note', 'test', 'voice']

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

# ══════════════════════════════════════════════
# 🧬 علوم پایه — ترم‌ها / درس‌ها / جلسات / محتوا
# ══════════════════════════════════════════════

@router.get("/basic-science/terms")
async def bs_terms(admin=Depends(get_content_admin_user)):
    return {"terms": TERMS}

@router.get("/basic-science/lessons")
async def bs_lessons(term: str = Query(...), admin=Depends(get_content_admin_user)):
    items = await db.bs_get_lessons(term)
    return {"lessons":[{"id":str(l["_id"]),"name":l.get("name",""),"teacher":l.get("teacher","")} for l in items]}

class BsLessonCreate(BaseModel):
    term: str; name: str = Field(min_length=1); teacher: str = ""

@router.post("/basic-science/lessons")
async def bs_add_lesson_ep(body: BsLessonCreate, admin=Depends(get_content_admin_user)):
    if body.term not in TERMS: raise HTTPException(422, "ترم نامعتبر")
    r = await db.bs_add_lesson(body.term, body.name.strip(), body.teacher.strip())
    if r is None: raise HTTPException(409, "این درس قبلاً در این ترم ثبت شده")
    return {"ok":True, "id":str(r)}

@router.delete("/basic-science/lessons/{lid}")
async def bs_del_lesson_ep(lid: str, admin=Depends(get_content_admin_user)):
    await db.bs_delete_lesson(lid); return {"ok":True}

@router.get("/basic-science/lessons/{lid}/sessions")
async def bs_sessions_ep(lid: str, admin=Depends(get_content_admin_user)):
    items = await db.bs_get_sessions(lid)
    return {"sessions":[{"id":str(s["_id"]),"number":s.get("number",0),"topic":s.get("topic",""),
        "teacher":s.get("teacher","")} for s in items]}

class BsSessionCreate(BaseModel):
    number: int; topic: str = Field(min_length=1); teacher: str = ""

@router.post("/basic-science/lessons/{lid}/sessions")
async def bs_add_session_ep(lid: str, body: BsSessionCreate, admin=Depends(get_content_admin_user)):
    sid = await db.bs_add_session(lid, body.number, body.topic.strip(), body.teacher.strip())
    return {"ok":True, "id":sid}

@router.delete("/basic-science/sessions/{sid}")
async def bs_del_session_ep(sid: str, admin=Depends(get_content_admin_user)):
    await db.bs_delete_session(sid); return {"ok":True}

@router.get("/basic-science/sessions/{sid}/content")
async def bs_content_ep(sid: str, admin=Depends(get_content_admin_user)):
    items = await db.bs_get_content(sid)
    return {"content":[{"id":str(c["_id"]),"type":c.get("type",""),"description":c.get("description",""),
        "extra_info":c.get("extra_info",""),"downloads":c.get("downloads",0)} for c in items]}

@router.post("/basic-science/sessions/{sid}/content")
async def bs_add_content_ep(sid: str, ctype: str = Form(...), description: str = Form(""),
                             extra_info: str = Form(""), file: UploadFile = File(...),
                             admin=Depends(get_content_admin_user)):
    if ctype not in CONTENT_TYPES: raise HTTPException(422, "نوع محتوا نامعتبر")
    raw = await file.read()
    if len(raw) > 45 * 1024 * 1024: raise HTTPException(413, "حجم فایل بیش از حد مجاز است (۴۵MB)")
    file_id = await upload_and_get_file_id(admin["id"], file.filename or "file", raw,
        file.content_type or "application/octet-stream")
    if not file_id: raise HTTPException(502, "آپلود فایل به تلگرام ناموفق بود")
    cid = await db.bs_add_content(sid, ctype, file_id, description.strip(), extra_info.strip())
    return {"ok":True, "id":str(cid)}

@router.delete("/basic-science/content/{cid}")
async def bs_del_content_ep(cid: str, admin=Depends(get_content_admin_user)):
    await db.bs_delete_content(cid); return {"ok":True}

# ══════════════════════════════════════════════
# 📖 رفرنس‌ها — موضوع‌ها / کتاب‌ها / فایل‌ها
# ══════════════════════════════════════════════

@router.get("/references/subjects")
async def ref_subjects_ep(admin=Depends(get_content_admin_user)):
    items = await db.ref_get_subjects()
    return {"subjects":[{"id":str(s["_id"]),"name":s.get("name","")} for s in items]}

class RefSubjectCreate(BaseModel):
    name: str = Field(min_length=1)

@router.post("/references/subjects")
async def ref_add_subject_ep(body: RefSubjectCreate, admin=Depends(get_content_admin_user)):
    r = await db.ref_add_subject(body.name.strip())
    if r is None: raise HTTPException(409, "این موضوع قبلاً ثبت شده")
    return {"ok":True, "id":str(r)}

@router.delete("/references/subjects/{sid}")
async def ref_del_subject_ep(sid: str, admin=Depends(get_content_admin_user)):
    await db.ref_delete_subject(sid); return {"ok":True}

@router.get("/references/subjects/{sid}/books")
async def ref_books_ep(sid: str, admin=Depends(get_content_admin_user)):
    items = await db.ref_get_books(sid)
    return {"books":[{"id":str(b["_id"]),"name":b.get("name","")} for b in items]}

class RefBookCreate(BaseModel):
    name: str = Field(min_length=1)

@router.post("/references/subjects/{sid}/books")
async def ref_add_book_ep(sid: str, body: RefBookCreate, admin=Depends(get_content_admin_user)):
    r = await db.ref_add_book(sid, body.name.strip())
    return {"ok":True, "id":str(r)}

@router.delete("/references/books/{bid}")
async def ref_del_book_ep(bid: str, admin=Depends(get_content_admin_user)):
    await db.ref_delete_book(bid); return {"ok":True}

@router.get("/references/books/{bid}/files")
async def ref_files_ep(bid: str, admin=Depends(get_content_admin_user)):
    items = await db.ref_get_files(bid)
    return {"files":[{"id":str(f["_id"]),"lang":f.get("lang","fa"),"volume":f.get("volume",1),
        "description":f.get("description",""),"downloads":f.get("downloads",0)} for f in items]}

@router.post("/references/books/{bid}/files")
async def ref_add_file_ep(bid: str, lang: str = Form("fa"), volume: int = Form(1),
                           description: str = Form(""), file: UploadFile = File(...),
                           admin=Depends(get_content_admin_user)):
    if lang not in ("fa","en"): raise HTTPException(422, "زبان نامعتبر")
    raw = await file.read()
    if len(raw) > 45 * 1024 * 1024: raise HTTPException(413, "حجم فایل بیش از حد مجاز است (۴۵MB)")
    file_id = await upload_and_get_file_id(admin["id"], file.filename or "file", raw,
        file.content_type or "application/octet-stream")
    if not file_id: raise HTTPException(502, "آپلود فایل به تلگرام ناموفق بود")
    fid = await db.ref_add_file(bid, lang, file_id, volume, description.strip())
    return {"ok":True, "id":fid}

@router.delete("/references/files/{fid}")
async def ref_del_file_ep(fid: str, admin=Depends(get_content_admin_user)):
    await db.ref_delete_file(fid); return {"ok":True}

# ══════════════════════════════════════════════
# 🧪 بانک سوال — آپلود و مدیریت فایل
# ══════════════════════════════════════════════

@router.get("/qbank/files")
async def qbank_files_ep(lesson: Optional[str]=Query(None), topic: Optional[str]=Query(None),
                          admin=Depends(get_content_admin_user)):
    items = await db.get_qbank_files(lesson, topic)
    return {"files":[{"id":str(f["_id"]),"lesson":f.get("lesson",""),"topic":f.get("topic",""),
        "description":f.get("description",""),"file_type":f.get("file_type","document"),
        "downloads":f.get("downloads",0),"upload_date":f.get("upload_date","")[:10]} for f in items]}

@router.post("/qbank/files")
async def qbank_add_file_ep(lesson: str = Form(...), topic: str = Form(...),
                             description: str = Form(""), file: UploadFile = File(...),
                             admin=Depends(get_content_admin_user)):
    raw = await file.read()
    if len(raw) > 45 * 1024 * 1024: raise HTTPException(413, "حجم فایل بیش از حد مجاز است (۴۵MB)")
    ctype = file.content_type or ""
    ftype = "video" if ctype.startswith("video") else "voice" if ctype.startswith("audio") else "document"
    file_id = await upload_and_get_file_id(admin["id"], file.filename or "file", raw,
        ctype or "application/octet-stream")
    if not file_id: raise HTTPException(502, "آپلود فایل به تلگرام ناموفق بود")
    fid = await db.add_qbank_file(lesson.strip(), topic.strip(), file_id, description.strip(), ftype)
    return {"ok":True, "id":str(fid)}

@router.delete("/qbank/files/{fid}")
async def qbank_del_file_ep(fid: str, admin=Depends(get_content_admin_user)):
    await db.delete_qbank_file(fid); return {"ok":True}

# ══════════════════════════════════════════════
# 🚩 گزارش‌های ایراد (سوال/جزوه)
# ══════════════════════════════════════════════

@router.get("/reports/stats")
async def reports_stats_ep(admin=Depends(get_content_admin_user)):
    return await db.content_reports_stats()

@router.get("/reports")
async def reports_list_ep(status: Optional[str]=Query(None), admin=Depends(get_content_admin_user)):
    items = await db.get_content_reports(status=status)
    REASON_FA = {'wrong_answer':'پاسخ اشتباه','unclear':'گنگ/نامفهوم','duplicate':'تکراری',
        'broken_file':'فایل خراب','outdated':'محتوای قدیمی','other':'سایر'}
    return {"reports":[{"id":r.get("report_id"),"target_type":r.get("target_type",""),
        "target_id":r.get("target_id",""),"reporter_name":r.get("reporter_name",""),
        "reason":REASON_FA.get(r.get("reason",""), r.get("reason","")),"note":r.get("note",""),
        "status":r.get("status","new"),"created_at":r.get("created_at","")[:10]} for r in items]}

class ReportStatusUpdate(BaseModel):
    status: str

@router.post("/reports/{rid}/status")
async def report_status_ep(rid: int, body: ReportStatusUpdate, admin=Depends(get_content_admin_user)):
    if body.status not in ("new","reviewing","resolved","rejected"): raise HTTPException(422,"وضعیت نامعتبر")
    r = await db.get_content_report(rid)
    if not r: raise HTTPException(404)
    await db.update_report_status(rid, body.status, resolved_by=admin["id"])
    return {"ok":True}

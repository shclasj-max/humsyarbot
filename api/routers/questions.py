"""🧪 Questions"""
import random, uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from api.auth import get_current_user
from database import db

router = APIRouter()
_SESSIONS: dict = {}

def _fmt(q):
    return {"id":str(q["_id"]),"lesson":q.get("lesson",""),"topic":q.get("topic",""),
        "difficulty":q.get("difficulty","متوسط"),"question":q.get("question",""),"options":q.get("options",[])}

@router.get("/lessons")
async def get_lessons(user=Depends(get_current_user)):
    lessons = await db.questions.distinct("lesson",{"approved":True})
    result = []
    for l in sorted(lessons):
        c = await db.questions.count_documents({"lesson":l,"approved":True})
        result.append({"name":l,"count":c})
    return {"lessons":result}

@router.get("/topics/{lesson}")
async def get_topics(lesson: str, user=Depends(get_current_user)):
    topics = await db.questions.distinct("topic",{"lesson":lesson,"approved":True})
    result = []
    for t in sorted(topics):
        c = await db.questions.count_documents({"lesson":lesson,"topic":t,"approved":True})
        result.append({"name":t,"count":c})
    return {"topics":result}

@router.get("/practice")
async def practice(user=Depends(get_current_user), lesson: str=Query(None), topic: str=Query(None), exclude: str=Query(None)):
    excl = [e.strip() for e in exclude.split(",")] if exclude else []
    qs = await db.get_questions(lesson=lesson, topic=topic, limit=10, exclude=excl)
    if not qs: return {"question":None}
    return {"question":_fmt(random.choice(qs))}

@router.get("/weak")
async def weak(user=Depends(get_current_user)):
    qs = await db.get_weak_questions(user["id"], limit=5)
    if not qs: return {"question":None,"message":"نقطه ضعفی ثبت نشده"}
    return {"question":_fmt(random.choice(qs))}

@router.get("/hard")
async def hard(user=Depends(get_current_user), exclude: str=Query(None)):
    excl = [e.strip() for e in exclude.split(",")] if exclude else []
    qs = await db.get_questions(difficulty="سخت 🔴", limit=10, exclude=excl)
    if not qs: return {"question":None}
    return {"question":_fmt(random.choice(qs))}

class AnswerIn(BaseModel):
    question_id: str; selected: int

@router.post("/answer")
async def answer(body: AnswerIn, user=Depends(get_current_user)):
    uid = user["id"]
    q = await db.get_question_by_id(body.question_id)
    if not q: raise HTTPException(404)
    ca = q.get("correct_answer",0); ok = body.selected == ca
    await db.save_answer(uid, body.question_id, body.selected, ok)
    if not ok and q.get("topic"):
        await db.users.update_one({"user_id":uid},{"$addToSet":{"weak_topics":q["topic"]}})
    return {"is_correct":ok,"correct_answer":ca,"explanation":q.get("explanation",""),
        "question":{**_fmt(q),"correct_answer":ca,"explanation":q.get("explanation","")}}

@router.get("/stats/by-lesson")
async def stats_by_lesson(user=Depends(get_current_user)):
    pipeline = [
        {"$match":{"user_id":user["id"]}},
        {"$addFields":{"qid_obj":{"$convert":{"input":"$question_id","to":"objectId","onError":None}}}},
        {"$lookup":{"from":"questions","localField":"qid_obj","foreignField":"_id","as":"q"}},
        {"$unwind":{"path":"$q","preserveNullAndEmptyArrays":False}},
        {"$group":{"_id":"$q.lesson","total":{"$sum":1},"correct":{"$sum":{"$cond":["$is_correct",1,0]}}}},
        {"$sort":{"total":-1}},
    ]
    try: rows = await db.answers.aggregate(pipeline).to_list(100)
    except Exception: rows = []
    return {"lessons":[{"lesson":r["_id"] or "نامشخص","total":r["total"],"correct":r["correct"],
        "percentage":round(r["correct"]/r["total"]*100) if r["total"] else 0} for r in rows]}

class ExamStart(BaseModel):
    lesson: str; topic: Optional[str]=None; count: int=Field(ge=5,le=40); minutes: int=Field(ge=0,le=90)

@router.post("/custom-exam/start")
async def start_exam(body: ExamStart, user=Depends(get_current_user)):
    topic = None if not body.topic or body.topic=="همه" else body.topic
    qs = await db.questions.find({"approved":True,"lesson":body.lesson,**({"topic":topic} if topic else {})}).to_list(200)
    if not qs: raise HTTPException(404,"سوالی پیدا نشد")
    random.shuffle(qs); selected = qs[:body.count]
    sid = uuid.uuid4().hex[:12]
    _SESSIONS[sid] = {"uid":user["id"],"question_ids":[str(q["_id"]) for q in selected],
        "index":0,"minutes":body.minutes,"correct":0,"answered":0}
    return {"session_id":sid,"total":len(selected),"minutes":body.minutes}

@router.get("/custom-exam/{sid}/next")
async def exam_next(sid: str, user=Depends(get_current_user)):
    s = _SESSIONS.get(sid)
    if not s or s["uid"]!=user["id"]: raise HTTPException(404)
    idx = s["index"]
    if idx >= len(s["question_ids"]):
        return {"finished":True,"correct":s["correct"],"answered":s["answered"],
            "total":len(s["question_ids"]),"percentage":round(s["correct"]/s["answered"]*100) if s["answered"] else 0}
    q = await db.get_question_by_id(s["question_ids"][idx])
    return {"finished":False,"question":_fmt(q),"progress":idx+1,"total":len(s["question_ids"])}

class ExamAnswer(BaseModel):
    selected: int

@router.post("/custom-exam/{sid}/answer")
async def exam_answer(sid: str, body: ExamAnswer, user=Depends(get_current_user)):
    s = _SESSIONS.get(sid)
    if not s or s["uid"]!=user["id"]: raise HTTPException(404)
    idx = s["index"]
    if idx >= len(s["question_ids"]): raise HTTPException(400,"آزمون تمام شده")
    q = await db.get_question_by_id(s["question_ids"][idx])
    ca = q.get("correct_answer",0); ok = body.selected==ca
    await db.save_answer(user["id"], s["question_ids"][idx], body.selected, ok)
    s["answered"]+=1
    if ok: s["correct"]+=1
    s["index"]+=1
    return {"is_correct":ok,"correct_answer":ca,"explanation":q.get("explanation",""),
        "progress":idx+1,"total":len(s["question_ids"])}

class QuestionDesign(BaseModel):
    lesson: str; topic: str; question: str=Field(min_length=10)
    options: List[str]=Field(min_length=4,max_length=4)
    correct: int=Field(ge=0,le=3); explanation: Optional[str]=""; difficulty: str="متوسط 🟡"

@router.post("/design")
async def design(body: QuestionDesign, user=Depends(get_current_user)):
    uid = user["id"]; db_user = user["_db"]
    is_priv = db_user.get("role","student") in ("admin","content_admin")
    r = await db.questions.insert_one({"lesson":body.lesson,"topic":body.topic,"difficulty":body.difficulty,
        "question":body.question,"options":body.options,"correct_answer":body.correct,
        "explanation":body.explanation or "","creator_id":uid,"creator_name":db_user.get("name",""),
        "approved":is_priv,"source":"webapp","created_at":datetime.now().isoformat(),"attempt_count":0,"correct_count":0})
    if not is_priv:
        try:
            import os
            notif = db.client["medicalbot"]["bot_notifications"]
            await notif.insert_one({"type":"new_question_design","chat_id":int(os.getenv("ADMIN_ID","0")),
                "text":f"🔔 <b>سوال جدید</b>\n✏️ {db_user.get('name','')}\n📚 {body.lesson} — {body.topic}",
                "sent":False,"created_at":datetime.now().isoformat()})
        except Exception: pass
    return {"ok":True,"question_id":str(r.inserted_id),"auto_approved":is_priv,
        "message":"✅ ثبت شد!" if is_priv else "✅ بعد از تأیید ادمین نمایش داده می‌شود."}

@router.get("/my-designs")
async def my_designs(user=Depends(get_current_user)):
    docs = await db.questions.find({"creator_id":user["id"]}).sort("created_at",-1).to_list(100)
    return {"questions":[{"id":str(d["_id"]),"lesson":d.get("lesson",""),"topic":d.get("topic",""),
        "question":d.get("question",""),"difficulty":d.get("difficulty",""),
        "approved":d.get("approved",False),"created_at":d.get("created_at","")[:10]} for d in docs]}

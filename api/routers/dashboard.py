"""🩺 Dashboard"""
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends
from api.auth import get_current_user
from api.level import get_level
from database import db

router = APIRouter()

@router.get("/")
async def get_dashboard(user=Depends(get_current_user)):
    uid = user["id"]; db_user = user["_db"]
    stats, exams, tickets = await asyncio.gather(
        db.user_stats(uid), db.upcoming_exams(7), db.ticket_get_user(uid))
    exam_list = []
    for e in exams[:3]:
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d")
            days = max(0, (d.date() - datetime.now().date()).days)
        except Exception: days = None
        exam_list.append({"id": str(e["_id"]), "lesson": e.get("lesson",""),
            "date": e.get("date",""), "time": e.get("time",""), "days_left": days})
    return {
        "user": {"name": db_user.get("name",""), "intake": db_user.get("intake",""),
            "group": db_user.get("group",""), "role": db_user.get("role","student")},
        "stats": {**stats, "level": get_level(stats["percentage"]), "weak_topics": stats["weak_topics"][:3]},
        "upcoming_exams": exam_list,
        "open_tickets": sum(1 for t in tickets if t.get("status")=="open"),
    }

@router.get("/weekly")
async def weekly(user=Depends(get_current_user)):
    data = await db.weekly_activity(user["id"])
    return {"weekly": [{"date": d, "count": c} for d, c in data]}

@router.get("/leaderboard")
async def leaderboard(user=Depends(get_current_user)):
    leaders = await db.get_leaderboard(10)
    uid = user["id"]
    result = []
    for i, u in enumerate(leaders):
        t = int(u.get("total_answers",0) or 0)
        c = int(u.get("correct_answers",0) or 0)
        result.append({"rank":i+1,"name":u.get("name",""),"correct":c,"total":t,
            "percent":round(c/t*100) if t else 0,"is_me":u.get("user_id")==uid})
    return {"leaderboard": result}

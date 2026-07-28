"""📅 Schedule"""
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from api.auth import get_current_user
from database import db

router = APIRouter()

def _fmt(s):
    if not s: return None
    doc = {"id":str(s["_id"]),"type":s.get("type",""),"lesson":s.get("lesson",""),
        "teacher":s.get("teacher",""),"date":s.get("date",""),"time":s.get("time",""),
        "note":s.get("note",""),"group":s.get("group","")}
    if s.get("type")=="exam" and s.get("date"):
        try:
            d = datetime.strptime(s["date"],"%Y-%m-%d")
            doc["days_left"] = max(0,(d.date()-datetime.now().date()).days)
        except Exception: doc["days_left"] = None
    return doc

@router.get("")
async def get_schedule(user=Depends(get_current_user), stype: str=Query(None)):
    group = str(user["_db"].get("group",""))
    items = await db.get_schedules(stype=stype, upcoming=True, group=group)
    return {"schedule": [_fmt(s) for s in items], "group": group}

@router.get("/exams")
async def get_exams(user=Depends(get_current_user), days: int=Query(30)):
    exams = await db.upcoming_exams(days)
    return {"exams": [_fmt(e) for e in exams]}

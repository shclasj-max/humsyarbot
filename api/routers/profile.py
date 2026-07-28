"""👤 Profile"""
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from api.auth import get_current_user
from api.level import get_level
from database import db

router = APIRouter()

@router.get("")
async def get_profile(user=Depends(get_current_user)):
    uid = user["id"]; db_user = user["_db"]
    stats, weekly, tickets = await __import__("asyncio").gather(
        db.user_stats(uid), db.weekly_activity(uid), db.ticket_get_user(uid))
    return {
        "user":{"name":db_user.get("name",""),"intake":db_user.get("intake",""),
            "group":db_user.get("group",""),"student_id":db_user.get("student_id",""),
            "role":db_user.get("role","student"),"telegram_id":uid},
        "stats":{**stats,"level":get_level(stats["percentage"]),
            "weekly_chart":[{"date":d,"count":c} for d,c in weekly]},
        "tickets":{"open":sum(1 for t in tickets if t.get("status")=="open"),
            "closed":sum(1 for t in tickets if t.get("status")=="closed")},
    }

class NameUpdate(BaseModel):
    name: str

@router.patch("/name")
async def update_name(body: NameUpdate, user=Depends(get_current_user)):
    n = body.name.strip()
    if not n or len(n)>50: raise HTTPException(422,"نام نامعتبر")
    await db.update_user(user["id"],{"name":n}); return {"ok":True}

class GroupUpdate(BaseModel):
    group: str = Field(pattern="^[12]$")

@router.patch("/group")
async def update_group(body: GroupUpdate, user=Depends(get_current_user)):
    await db.update_user(user["id"],{"group":body.group}); return {"ok":True,"group":body.group}

class IntakeUpdate(BaseModel):
    intake: str

@router.patch("/intake")
async def update_intake(body: IntakeUpdate, user=Depends(get_current_user)):
    active = await db.get_active_intakes()
    if body.intake not in {i.get("code") for i in active}: raise HTTPException(422,"ورودی نامعتبر")
    await db.update_user(user["id"],{"intake":body.intake}); return {"ok":True}

class SidUpdate(BaseModel):
    student_id: str = Field(min_length=3, max_length=20)

@router.patch("/student-id")
async def update_sid(body: SidUpdate, user=Depends(get_current_user)):
    sid = body.student_id.strip()
    if not sid.isdigit(): raise HTTPException(422,"باید عدد باشد")
    await db.update_user(user["id"],{"student_id":sid}); return {"ok":True}

@router.get("/rank")
async def get_rank(user=Depends(get_current_user)):
    uid = user["id"]; db_user = user["_db"]
    if not db_user.get("total_answers",0): return {"rank":None,"total_users":0}
    my_correct = db_user.get("correct_answers",0)
    better = await db.users.count_documents({"approved":True,"total_answers":{"$gt":0},"correct_answers":{"$gt":my_correct}})
    total  = await db.users.count_documents({"approved":True,"total_answers":{"$gt":0}})
    return {"rank":better+1,"total_users":total,"percentile":round((1-better/total)*100) if total else 0}

@router.get("/intakes")
async def get_intakes(user=Depends(get_current_user)):
    items = await db.get_active_intakes()
    return {"intakes":[{"code":i.get("code",""),"label":i.get("label","")} for i in items]}

@router.get("/badges")
async def get_badges(user=Depends(get_current_user)):
    db_user = user["_db"]
    total=db_user.get("total_answers",0); correct=db_user.get("correct_answers",0)
    pct=round(correct/total*100) if total else 0
    earned=set()
    if total>=1: earned.add("first")
    if total>=50: earned.add("fifty")
    if total>=200: earned.add("two_hundred")
    if pct>=70: earned.add("seventy")
    if pct>=90: earned.add("ninety")
    if db_user.get("downloads",0)>=10: earned.add("downloader")
    return {"badges":[
        {"id":"first","title":"اولین قدم","icon":"🌱","earned":"first" in earned},
        {"id":"fifty","title":"۵۰ سوال","icon":"🧪","earned":"fifty" in earned},
        {"id":"two_hundred","title":"۲۰۰ سوال","icon":"🏆","earned":"two_hundred" in earned},
        {"id":"seventy","title":"۷۰٪ موفق","icon":"⭐","earned":"seventy" in earned},
        {"id":"ninety","title":"۹۰٪ موفق","icon":"🥇","earned":"ninety" in earned},
        {"id":"downloader","title":"خواننده","icon":"📚","earned":"downloader" in earned},
    ]}

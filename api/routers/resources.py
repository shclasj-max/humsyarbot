"""📚 Resources"""
from fastapi import APIRouter, Depends, HTTPException, Query
from api.auth import get_current_user
from database import db

router = APIRouter()

@router.get("/terms")
async def terms(user=Depends(get_current_user)):
    ts = await db.bs_lessons.distinct("term")
    result = []
    for t in sorted(ts):
        c = await db.bs_lessons.count_documents({"term":t})
        result.append({"name":t,"lesson_count":c})
    return {"terms":result}

@router.get("/lessons/{term}")
async def lessons(term: str, user=Depends(get_current_user)):
    items = await db.bs_get_lessons(term)
    result = []
    for l in items:
        l2 = {**l,"_id":str(l["_id"])}
        l2["session_count"] = await db.bs_sessions.count_documents({"lesson_id":str(l["_id"])})
        result.append(l2)
    return {"lessons":result}

@router.get("/sessions/{lesson_id}")
async def sessions(lesson_id: str, user=Depends(get_current_user)):
    items = await db.bs_get_sessions(lesson_id)
    result = []
    for s in items:
        s2 = {**s,"_id":str(s["_id"])}
        s2["file_count"] = await db.bs_content.count_documents({"session_id":str(s["_id"])})
        result.append(s2)
    return {"sessions":result}

@router.get("/files/{session_id}")
async def files(session_id: str, user=Depends(get_current_user)):
    items = await db.bs_get_content(session_id)
    return {"files":[{"id":str(f["_id"]),"type":f.get("type",""),"name":f.get("name",""),
        "description":f.get("description",""),"downloads":f.get("downloads",0)} for f in items]}

@router.post("/download/{cid}")
async def download(cid: str, user=Depends(get_current_user)):
    item = await db.bs_get_content_item(cid)
    if not item: raise HTTPException(404,"فایل پیدا نشد")
    await db.bs_inc_download(cid, user["id"])
    return {"file_id":item.get("file_id",""),"type":item.get("type",""),"name":item.get("name","")}

@router.get("/search")
async def search(user=Depends(get_current_user), q: str=Query(..., min_length=2)):
    results = await db.search_resources(q)
    return {"results":[{"id":str(r["_id"]),"name":r.get("name",""),
        "type":r.get("type",""),"lesson":r.get("lesson_name",""),"session":r.get("session_topic","")} for r in results]}

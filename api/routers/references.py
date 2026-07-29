"""📖 References"""
from fastapi import APIRouter, Depends, HTTPException
from api.auth import get_current_user
from api.telegram_send import send_ref_file
from database import db

router = APIRouter()

@router.get("/subjects")
async def subjects(user=Depends(get_current_user)):
    items = await db.ref_get_subjects()
    result = []
    for s in items:
        sid = str(s["_id"])
        books = await db.ref_get_books(sid)
        result.append({"id":sid,"name":s.get("name",""),"book_count":len(books)})
    return {"subjects":result}

@router.get("/books/{sid}")
async def books(sid: str, user=Depends(get_current_user)):
    subject = await db.ref_get_subject(sid)
    if not subject: raise HTTPException(404,"پیدا نشد")
    bs = await db.ref_get_books(sid)
    result = []
    for b in bs:
        bid=str(b["_id"]); fs=await db.ref_get_files(bid)
        result.append({"id":bid,"name":b.get("name",""),
            "fa_count":sum(1 for f in fs if f.get("lang")=="fa"),
            "en_count":sum(1 for f in fs if f.get("lang")=="en")})
    return {"subject":{"id":sid,"name":subject.get("name","")},"books":result}

@router.get("/files/{bid}")
async def files(bid: str, user=Depends(get_current_user)):
    book = await db.ref_get_book(bid)
    if not book: raise HTTPException(404,"پیدا نشد")
    fs = await db.ref_get_files(bid)
    fa = sorted([f for f in fs if f.get("lang")=="fa"], key=lambda x:x.get("volume",1))
    en = sorted([f for f in fs if f.get("lang")=="en"], key=lambda x:x.get("volume",1))
    def fmt(f): return {"id":str(f["_id"]),"lang":f.get("lang","fa"),"volume":f.get("volume",1),
        "description":f.get("description",""),"downloads":f.get("downloads",0)}
    return {"book":{"id":bid,"name":book.get("name","")},"fa_files":[fmt(f) for f in fa],"en_files":[fmt(f) for f in en]}

@router.post("/download/{fid}")
async def download(fid: str, user=Depends(get_current_user)):
    item = await db.ref_get_file(fid)
    if not item: raise HTTPException(404,"پیدا نشد")
    await db.ref_inc_download(fid, user["id"])
    item = await db.ref_get_file(fid)  # برای گرفتن شمارنده‌ی به‌روز، مثل خود ربات
    sent = await send_ref_file(user["id"], item)
    if not sent:
        raise HTTPException(502, "ارسال فایل از طریق ربات ناموفق بود. لطفاً ابتدا یک پیام به ربات بفرستید یا دوباره تلاش کنید.")
    return {"sent": True, "lang":item.get("lang","fa"),"volume":item.get("volume",1)}

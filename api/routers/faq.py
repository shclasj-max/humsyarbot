"""❓ FAQ"""
from fastapi import APIRouter, Depends, Query
from api.auth import get_current_user
from database import db

router = APIRouter()
DEFAULT_FAQS = [
    {"category":"🔬 علوم پایه","question":"علوم پایه چیه؟","answer":"بخش علوم پایه شامل محتوای آموزشی دروس ترم ۱ تا ۵ است."},
    {"category":"🧪 بانک سوال","question":"بانک سوال چه بخش‌هایی داره؟","answer":"تمرین آزاد، نقاط ضعف، سطح سخت، آزمون سفارشی و طراحی سوال."},
    {"category":"💳 اشتراک","question":"اشتراک چطور کار می‌کنه؟","answer":"پلن انتخاب کنید و رسید پرداخت را از طریق ربات بفرستید."},
    {"category":"⚙️ مشکلات فنی","question":"ربات جواب نمی‌ده؟","answer":"/start بزنید. اگر ادامه داشت تیکت بزنید."},
]

@router.get("")
async def get_faq(user=Depends(get_current_user)):
    db_faqs = await db.faq_get_all()
    raw = [{"id":str(f["_id"]),"category":f.get("category","عمومی"),
            "question":f.get("question",""),"answer":f.get("answer","")} for f in db_faqs] if db_faqs else           [dict(f, id=str(i)) for i,f in enumerate(DEFAULT_FAQS)]
    cats = {}; cat_order = []
    for item in raw:
        cat = item["category"]
        if cat not in cats: cats[cat]=[]; cat_order.append(cat)
        cats[cat].append({"id":item["id"],"question":item["question"],"answer":item["answer"]})
    return {"categories":[{"name":c,"items":cats[c]} for c in cat_order]}

@router.get("/search")
async def search(user=Depends(get_current_user), q: str=Query(..., min_length=2)):
    db_faqs = await db.faq_get_all()
    source = db_faqs if db_faqs else DEFAULT_FAQS
    q_lower = q.lower()
    results = [{"id":str(f.get("_id","")),"category":f.get("category",""),
                "question":f.get("question",""),"answer":f.get("answer","")}
               for f in source if q_lower in f.get("question","").lower() or q_lower in f.get("answer","").lower()]
    return {"results": results}

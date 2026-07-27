"""📊 Grades"""
from fastapi import APIRouter, Depends
from api.auth import get_current_user
from database import db

router = APIRouter()

@router.get("/")
async def get_grades(user=Depends(get_current_user)):
    grades = await db.grade_list_for_student(user["id"])
    result = []
    for g in grades:
        score = g.get("score")
        mx = g.get("max_score", 20)
        result.append({"id": str(g.get("_id","")), "lesson": g.get("lesson",""),
            "exam_title": g.get("exam_title",""), "score": score, "max_score": mx,
            "exam_date": g.get("exam_date",""), "note": g.get("note",""),
            "percentage": round(score/mx*100) if score is not None else None})
    total = len(result)
    avg = round(sum(g["score"] for g in result if g["score"] is not None)/total, 2) if total else None
    return {"grades": result, "avg": avg, "total": total}

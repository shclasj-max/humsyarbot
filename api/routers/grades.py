"""Student grade endpoints for the Telegram Mini App."""

from fastapi import APIRouter, Depends

from api.auth import get_current_user
from database import db
from grade_utils import summarize_grades


router = APIRouter()


@router.get("")
async def get_grades(
    user=Depends(get_current_user),
):
    records = await db.grade_list_for_student(
        user["id"]
    )

    if not isinstance(records, list):
        records = []

    return summarize_grades(records)

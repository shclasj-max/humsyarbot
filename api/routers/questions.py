"""Question practice, persistent exams and designs."""

from __future__ import annotations

import random
import time
import uuid

from datetime import datetime
from html import escape
from typing import (
    Any,
    List,
    Mapping,
    Optional,
)

from bson import ObjectId

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from pydantic import (
    BaseModel,
    Field,
)

from api.auth import (
    ADMIN_ID,
    get_current_user,
)

from api.user_metrics import (
    non_negative_int,
)

from database import db


router = APIRouter()

exam_sessions = (
    db.client["medicalbot"]
    ["exam_sessions"]
)


def _pub_prestige(ev):
    """شکل‌دهی عمومی خروجی موتور Prestige برای کلاینت (افزایشی روی پاسخ‌های موجود).
    مهم: منطق در database.py است؛ این فقط «presentation» است (قرارداد §د)."""
    if not ev or ev.get('ignored'):
        return None
    d = ev.get('display') or {}
    e = ev.get('events') or {}
    celeb = None
    if e.get('rank_up'):
        ru = e['rank_up']
        celeb = {'kind': 'rank', 'title': ru.get('to'), 'from_title': ru.get('from'),
                 'icon': ru.get('icon'), 'roman': d.get('roman'),
                 'color': d.get('color'), 'gradient': d.get('gradient')}
    elif e.get('div_up'):
        du = e['div_up']
        celeb = {'kind': 'div', 'title': du.get('rank'), 'roman': du.get('roman'),
                 'icon': du.get('icon'),
                 'color': d.get('color'), 'gradient': d.get('gradient')}
    return {
        'xp_gained': ev.get('xp_gained', 0),
        'breakdown': ev.get('breakdown', []),
        'streak': ev.get('streak'),
        'display': d,
        'challenge_ready': bool(e.get('challenge_ready')),
        'celebration': celeb,
    }


async def _answer_first_time(user_id: int, question_id: str) -> bool:
    """پیش‌چک یک‌بارهرسؤال — باید **قبل** از db.save_answer صدا زده شود."""
    try:
        return (await db.answers.find_one(
            {'user_id': user_id, 'question_id': question_id}, {'_id': 1})) is None
    except Exception:
        return True


async def _answer_prestige(user_id: int, question: dict,
                           is_correct: bool, first_time: bool) -> dict:
    """رویداد موتور پس از ثبت پاسخ — هرگز قرارداد اصلی را نمی‌شکند (در خطا None)."""
    try:
        ev = await db.prestige_event(
            user_id, 'answer',
            {'is_correct': is_correct,
             'difficulty': question.get('difficulty', ''),
             'first_time': first_time})
        return _pub_prestige(ev)
    except Exception:
        return None

ALLOWED_DIFFICULTIES = {
    "آسان 🟢",
    "متوسط 🟡",
    "سخت 🔴",
}


async def ensure_indexes():
    await exam_sessions.create_index(
        "session_id",
        unique=True,
        background=True,
    )

    await exam_sessions.create_index(
        [
            ("user_id", 1),
            ("started_at", -1),
        ],
        background=True,
    )

    await db.answers.create_index(
        [
            ("user_id", 1),
            ("answered_at", -1),
        ],
        background=True,
    )


def text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    return str(value).strip()


def safe_question(
    document: Mapping[
        str,
        Any,
    ] | None,
) -> dict | None:
    if not isinstance(
        document,
        Mapping,
    ):
        return None

    options = document.get(
        "options"
    )

    if not isinstance(
        options,
        list,
    ):
        options = []

    return {
        "id": text(
            document.get("_id")
        ),

        "lesson": text(
            document.get("lesson")
        ),

        "topic": text(
            document.get("topic")
        ),

        "difficulty": (
            text(
                document.get(
                    "difficulty"
                )
            )
            or "متوسط 🟡"
        ),

        "question": text(
            document.get("question")
        ),

        "options": [
            str(item)
            for item in options
        ],
    }


def exclude_ids(
    value: str | None,
) -> list[str]:
    if not value:
        return []

    result = []

    for item in value.split(",")[:100]:
        item = item.strip()

        if ObjectId.is_valid(item):
            result.append(item)

    return result


def exam_summary(
    session: Mapping[
        str,
        Any,
    ],
) -> dict:
    question_ids = (
        session.get(
            "question_ids"
        )
        or []
    )

    total = len(question_ids)

    answered = non_negative_int(
        session.get("answered")
    )

    correct = min(
        non_negative_int(
            session.get("correct")
        ),
        answered,
    )

    return {
        "session_id": text(
            session.get(
                "session_id"
            )
        ),

        "lesson": text(
            session.get("lesson")
        ),

        "topic": text(
            session.get("topic")
        ),

        "status": (
            text(
                session.get(
                    "status"
                )
            )
            or "active"
        ),

        "started_at": text(
            session.get(
                "started_at"
            )
        ),

        "finished_at": text(
            session.get(
                "finished_at"
            )
        ),

        "minutes":
            non_negative_int(
                session.get(
                    "minutes"
                )
            ),

        "progress": min(
            non_negative_int(
                session.get("index")
            ),
            total,
        ),

        "correct": correct,

        "answered": answered,

        "total": total,

        "percentage": (
            round(
                correct
                / answered
                * 100
            )
            if answered
            else 0
        ),
    }


async def load_session(
    session_id: str,
    user_id: int,
) -> dict:
    session = (
        await exam_sessions.find_one(
            {
                "session_id":
                    session_id,

                "user_id":
                    user_id,
            }
        )
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="آزمون پیدا نشد",
        )

    return session


async def expire_if_needed(
    session: dict,
) -> dict:
    deadline = session.get(
        "deadline_ts"
    )

    if (
        session.get("status")
        == "active"
        and deadline
        and int(time.time())
        >= int(deadline)
    ):
        finished_at = (
            datetime.now()
            .isoformat()
        )

        await exam_sessions.update_one(
            {
                "_id": session["_id"],
                "status": "active",
            },

            {
                "$set": {
                    "status":
                        "expired",

                    "finished_at":
                        finished_at,
                }
            },
        )

        session["status"] = (
            "expired"
        )

        session["finished_at"] = (
            finished_at
        )

    return session


@router.get("/lessons")
async def get_lessons(
    user=Depends(
        get_current_user
    ),
):
    lessons = (
        await db.questions.distinct(
            "lesson",
            {
                "approved": True,
            },
        )
    )

    names = sorted({
        text(item)
        for item in lessons
        if text(item)
    })

    result = []

    for name in names:
        count = (
            await db.questions
            .count_documents(
                {
                    "lesson": name,
                    "approved": True,
                }
            )
        )

        result.append({
            "name": name,

            "count":
                non_negative_int(
                    count
                ),
        })

    return {
        "lessons": result,
    }


@router.get(
    "/topics/{lesson}"
)
async def get_topics(
    lesson: str,

    user=Depends(
        get_current_user
    ),
):
    lesson = lesson.strip()

    topics = (
        await db.questions.distinct(
            "topic",
            {
                "lesson": lesson,
                "approved": True,
            },
        )
    )

    names = sorted({
        text(item)
        for item in topics
        if text(item)
    })

    result = []

    for topic in names:
        count = (
            await db.questions
            .count_documents(
                {
                    "lesson": lesson,
                    "topic": topic,
                    "approved": True,
                }
            )
        )

        result.append({
            "name": topic,

            "count":
                non_negative_int(
                    count
                ),
        })

    return {
        "topics": result,
    }


@router.get("/practice")
async def practice(
    user=Depends(
        get_current_user
    ),

    lesson: str | None = Query(
        default=None,
        max_length=100,
    ),

    topic: str | None = Query(
        default=None,
        max_length=100,
    ),

    exclude: str | None = Query(
        default=None,
        max_length=2500,
    ),
):
    questions = (
        await db.get_questions(
            lesson=lesson,
            topic=topic,
            limit=10,

            exclude=exclude_ids(
                exclude
            ),
        )
    )

    formatted = [
        safe_question(item)
        for item in (questions or [])
    ]

    formatted = [
        item
        for item in formatted
        if (
            item
            and len(
                item["options"]
            ) >= 2
        )
    ]

    return {
        "question": (
            random.choice(formatted)
            if formatted
            else None
        ),
    }


@router.get("/weak")
async def weak(
    user=Depends(
        get_current_user
    ),
):
    questions = (
        await db.get_weak_questions(
            user["id"],
            limit=10,
        )
    )

    formatted = [
        safe_question(item)
        for item in (questions or [])
    ]

    formatted = [
        item
        for item in formatted
        if (
            item
            and len(
                item["options"]
            ) >= 2
        )
    ]

    return {
        "question": (
            random.choice(formatted)
            if formatted
            else None
        ),

        "message": (
            ""
            if formatted
            else
            "نقطه ضعفی ثبت نشده"
        ),
    }


@router.get("/hard")
async def hard(
    user=Depends(
        get_current_user
    ),

    exclude: str | None = Query(
        default=None,
        max_length=2500,
    ),
):
    questions = (
        await db.get_questions(
            difficulty="سخت 🔴",
            limit=10,

            exclude=exclude_ids(
                exclude
            ),
        )
    )

    formatted = [
        safe_question(item)
        for item in (questions or [])
    ]

    formatted = [
        item
        for item in formatted
        if (
            item
            and len(
                item["options"]
            ) >= 2
        )
    ]

    return {
        "question": (
            random.choice(formatted)
            if formatted
            else None
        ),
    }


class AnswerInput(BaseModel):
    question_id: str = Field(
        min_length=24,
        max_length=24,
    )

    selected: int = Field(
        ge=0,
        le=3,
    )


@router.post("/answer")
async def answer(
    body: AnswerInput,

    user=Depends(
        get_current_user
    ),
):
    question = (
        await db.get_question_by_id(
            body.question_id
        )
    )

    if (
        not question
        or not question.get(
            "approved"
        )
    ):
        raise HTTPException(
            status_code=404,
            detail="سؤال پیدا نشد",
        )

    correct_answer = int(
        question.get(
            "correct_answer",
            0,
        )
        or 0
    )

    is_correct = (
        body.selected
        == correct_answer
    )

    # 👑 Prestige: پیش‌چک قبل از ثبت، رویداد بعد از ثبت (افزایشی)
    first_time = await _answer_first_time(
        user["id"], body.question_id)

    await db.save_answer(
        user["id"],
        body.question_id,
        body.selected,
        is_correct,
    )

    prestige = await _answer_prestige(
        user["id"], question, is_correct, first_time)

    formatted = (
        safe_question(question)
        or {}
    )

    explanation = text(
        question.get(
            "explanation"
        )
    )

    return {
        "is_correct":
            is_correct,

        "correct_answer":
            correct_answer,

        "explanation":
            explanation,

        "question": {
            **formatted,

            "correct_answer":
                correct_answer,

            "explanation":
                explanation,
        },

        "prestige": prestige,
    }


@router.get("/history")
async def answer_history(
    user=Depends(
        get_current_user
    ),

    skip: int = Query(
        default=0,
        ge=0,
    ),

    limit: int = Query(
        default=30,
        ge=1,
        le=100,
    ),
):
    query = {
        "user_id": user["id"],
    }

    records = (
        await db.answers
        .find(query)
        .sort(
            "answered_at",
            -1,
        )
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )

    total = (
        await db.answers
        .count_documents(query)
    )

    result = []

    for record in records:
        question_id = text(
            record.get(
                "question_id"
            )
        )

        question = (
            await db.get_question_by_id(
                question_id
            )
        )

        if not question:
            continue

        result.append({
            "id": text(
                record.get("_id")
            ),

            "question_id":
                question_id,

            "lesson": text(
                question.get(
                    "lesson"
                )
            ),

            "topic": text(
                question.get(
                    "topic"
                )
            ),

            "question": text(
                question.get(
                    "question"
                )
            ),

            "selected":
                non_negative_int(
                    record.get(
                        "selected"
                    )
                ),

            "correct_answer":
                non_negative_int(
                    question.get(
                        "correct_answer"
                    )
                ),

            "is_correct": bool(
                record.get(
                    "is_correct"
                )
            ),

            "answered_at": text(
                record.get(
                    "answered_at"
                )
            ),
        })

    return {
        "answers": result,

        "total":
            non_negative_int(
                total
            ),
    }


@router.get(
    "/stats/by-lesson"
)
async def stats_by_lesson(
    user=Depends(
        get_current_user
    ),
):
    pipeline = [
        {
            "$match": {
                "user_id":
                    user["id"],
            }
        },

        {
            "$addFields": {
                "qid_object": {
                    "$convert": {
                        "input":
                            "$question_id",

                        "to":
                            "objectId",

                        "onError":
                            None,
                    }
                }
            }
        },

        {
            "$lookup": {
                "from":
                    "questions",

                "localField":
                    "qid_object",

                "foreignField":
                    "_id",

                "as":
                    "question",
            }
        },

        {
            "$unwind": {
                "path":
                    "$question",

                "preserveNullAndEmptyArrays":
                    False,
            }
        },

        {
            "$group": {
                "_id":
                    "$question.lesson",

                "total": {
                    "$sum": 1,
                },

                "correct": {
                    "$sum": {
                        "$cond": [
                            "$is_correct",
                            1,
                            0,
                        ]
                    }
                },
            }
        },

        {
            "$sort": {
                "total": -1,
            }
        },
    ]

    try:
        rows = (
            await db.answers
            .aggregate(pipeline)
            .to_list(100)
        )

    except Exception:
        rows = []

    result = []

    for row in rows:
        total = non_negative_int(
            row.get("total")
        )

        correct = (
            non_negative_int(
                row.get("correct")
            )
        )

        if total <= 0:
            continue

        result.append({
            "lesson": (
                text(
                    row.get("_id")
                )
                or "نامشخص"
            ),

            "total":
                total,

            "correct":
                correct,

            "percentage":
                round(
                    correct
                    / total
                    * 100
                ),
        })

    return {
        "lessons": result,
    }


class ExamStartInput(BaseModel):
    lesson: str = Field(
        min_length=1,
        max_length=100,
    )

    topic: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    count: int = Field(
        ge=5,
        le=40,
    )

    minutes: int = Field(
        ge=0,
        le=90,
    )

    # ⚔️ True ⇒ شروع چالش ارتقا (استخر/زمان/قواعد سرورمحور — فیلدهای بالا بی‌اثر)
    promotion: bool = False


@router.get(
    "/custom-exam/history"
)
async def exam_history(
    user=Depends(
        get_current_user
    ),

    limit: int = Query(
        default=30,
        ge=1,
        le=100,
    ),
):
    sessions = (
        await exam_sessions
        .find({
            "user_id":
                user["id"],
        })
        .sort(
            "started_at",
            -1,
        )
        .to_list(limit)
    )

    result = []

    for session in sessions:
        session = (
            await expire_if_needed(
                session
            )
        )

        result.append(
            exam_summary(session)
        )

    return {
        "exams": result,
    }


@router.post(
    "/custom-exam/start"
)
async def start_exam(
    body: ExamStartInput,

    user=Depends(
        get_current_user
    ),
):
    # ⚔️ جریان چالش ارتقا (Spec §۳.۱) — استخر و قواعد کاملاً سرورمحور است؛
    # lesson/topic/count/minutes از کلاینت در این حالت نادیده گرفته می‌شود.
    if getattr(body, "promotion", False):
        chk = await db.challenge_start_check(user["id"])
        if not chk.get("ok"):
            detail = {"code": chk.get("code") or "locked",
                      "view": chk.get("view") or {}}
            if chk.get("hours_left"):
                detail["hours_left"] = chk["hours_left"]
            if chk.get("pool_meta"):
                detail["pool_meta"] = chk["pool_meta"]
            raise HTTPException(status_code=409, detail=detail)
        if chk.get("resume"):
            prev = await exam_sessions.find_one(
                {"user_id": user["id"], "session_id": chk["session_id"]})
            return {
                "session_id": chk["session_id"],
                "total": len((prev or {}).get("question_ids") or []),
                "minutes": 0,
                "ends_at": None,
                "promotion": True,
                "resume": True,
                "index": int((prev or {}).get("index", 0) or 0),
                "target_rank": (prev or {}).get("target_rank"),
                "apex": bool((prev or {}).get("apex")),
                "expires_ts": (prev or {}).get("expires_ts"),
            }
        view = chk.get("view") or {}
        selected_ids = list(chk.get("pool") or [])
        apex = bool(chk.get("apex"))
        now_ts = int(time.time())
        document = {
            "session_id": uuid.uuid4().hex[:16],
            "user_id": user["id"],
            "lesson": "⚔️ چالش ارتقا",
            "topic": view.get("title") or "",
            "question_ids": selected_ids,
            "index": 0,
            "minutes": 0,
            "deadline_ts": None,
            "correct": 0,
            "answered": 0,
            "answers": [],
            "status": "active",
            "started_at": datetime.now().isoformat(),
            "finished_at": "",
            "promotion": True,
            "target_rank": view.get("target_rank") or "",
            "apex": apex,
            "expires_ts": now_ts + db.CH_TTL_HOURS * 3600,
        }
        await exam_sessions.insert_one(document)
        await db.users.update_one({"user_id": user["id"]},
            {"$set": {"challenge.target_rank": view.get("target_rank") or "",
                      "challenge.apex": apex}})
        return {
            "session_id": document["session_id"],
            "total": len(selected_ids),
            "minutes": 0,
            "ends_at": None,
            "promotion": True,
            "resume": False,
            "index": 0,
            "target_rank": view.get("target_rank"),
            "target_title": view.get("title"),
            "target_icon": view.get("icon"),
            "apex": apex,
            "pass_pct": db.CH_APEX_PASS_PCT if apex else db.CH_PASS_PCT,
            "expires_ts": document["expires_ts"],
        }

    lesson = (
        body.lesson.strip()
    )

    topic = (
        None
        if (
            not body.topic
            or body.topic.strip()
            == "همه"
        )
        else body.topic.strip()
    )

    query = {
        "approved": True,
        "lesson": lesson,
    }

    if topic:
        query["topic"] = topic

    questions = (
        await db.questions
        .find(query)
        .to_list(500)
    )

    questions = [
        item
        for item in questions
        if safe_question(item)
    ]

    if not questions:
        raise HTTPException(
            status_code=404,
            detail="سؤالی پیدا نشد",
        )

    random.shuffle(questions)

    selected = questions[
        :body.count
    ]

    session_id = (
        uuid.uuid4()
        .hex[:16]
    )

    deadline = (
        int(time.time())
        + body.minutes * 60
        if body.minutes
        else None
    )

    document = {
        "session_id":
            session_id,

        "user_id":
            user["id"],

        "lesson":
            lesson,

        "topic":
            topic or "همه",

        "question_ids": [
            text(item.get("_id"))
            for item in selected
        ],

        "index":
            0,

        "minutes":
            body.minutes,

        "deadline_ts":
            deadline,

        "correct":
            0,

        "answered":
            0,

        "answers":
            [],

        "status":
            "active",

        "started_at":
            datetime.now()
            .isoformat(),

        "finished_at":
            "",
    }

    await exam_sessions.insert_one(
        document
    )

    return {
        "session_id":
            session_id,

        "total":
            len(selected),

        "minutes":
            body.minutes,

        "ends_at":
            deadline,
    }


@router.get(
    "/custom-exam/"
    "{session_id}/next"
)
async def exam_next(
    session_id: str,

    user=Depends(
        get_current_user
    ),
):
    session = (
        await load_session(
            session_id,
            user["id"],
        )
    )

    session = (
        await expire_if_needed(
            session
        )
    )

    if (
        session.get("status")
        != "active"
    ):
        return {
            "finished": True,
            **exam_summary(session),
        }

    question_ids = (
        session.get(
            "question_ids"
        )
        or []
    )

    index = non_negative_int(
        session.get("index")
    )

    while index < len(
        question_ids
    ):
        question = (
            await db.get_question_by_id(
                question_ids[index]
            )
        )

        formatted = (
            safe_question(question)
        )

        if formatted:
            if session.get(
                "deadline_ts"
            ):
                seconds_left = max(
                    0,

                    int(
                        session[
                            "deadline_ts"
                        ]
                    )
                    - int(time.time()),
                )

            else:
                seconds_left = None

            return {
                "finished": False,

                "question":
                    formatted,

                "progress":
                    index + 1,

                "total":
                    len(
                        question_ids
                    ),

                "seconds_left":
                    seconds_left,
            }

        index += 1

        await exam_sessions.update_one(
            {
                "_id":
                    session["_id"],
            },

            {
                "$set": {
                    "index":
                        index,
                }
            },
        )

    finished_at = (
        datetime.now()
        .isoformat()
    )

    await exam_sessions.update_one(
        {
            "_id":
                session["_id"],
        },

        {
            "$set": {
                "status":
                    "finished",

                "finished_at":
                    finished_at,

                "index":
                    index,
            }
        },
    )

    session.update({
        "status":
            "finished",

        "finished_at":
            finished_at,

        "index":
            index,
    })

    return {
        "finished": True,
        **exam_summary(session),
    }


class ExamAnswerInput(BaseModel):
    selected: int = Field(
        ge=0,
        le=3,
    )


@router.post(
    "/custom-exam/"
    "{session_id}/answer"
)
async def exam_answer(
    session_id: str,
    body: ExamAnswerInput,

    user=Depends(
        get_current_user
    ),
):
    session = (
        await load_session(
            session_id,
            user["id"],
        )
    )

    session = (
        await expire_if_needed(
            session
        )
    )

    # ⚔️ TTL چالش ارتقا (۲۴ساعته) — انقضا = Fail خودکار سرورمحور
    if (
        session.get("promotion")
        and session.get("status") == "active"
        and session.get("expires_ts")
        and int(time.time()) >= int(session["expires_ts"])
    ):
        try:
            await db.challenge_expire_session(session)
        except Exception:
            pass
        _ans = int(session.get("answered", 0) or 0)
        _cor = int(session.get("correct", 0) or 0)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "promotion_failed_ttl",
                "win": False,
                "pct": round(_cor / _ans * 100, 1) if _ans else 0,
                "cooldown_h": (db.CH_APEX_COOLDOWN_H
                               if session.get("apex")
                               else db.CH_COOLDOWN_H),
            },
        )

    if (
        session.get("status")
        != "active"
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "زمان آزمون "
                "تمام شده است"
            ),
        )

    question_ids = (
        session.get(
            "question_ids"
        )
        or []
    )

    index = non_negative_int(
        session.get("index")
    )

    if index >= len(
        question_ids
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "آزمون تمام شده است"
            ),
        )

    question_id = (
        question_ids[index]
    )

    question = (
        await db.get_question_by_id(
            question_id
        )
    )

    if not question:
        raise HTTPException(
            status_code=404,
            detail="سؤال پیدا نشد",
        )

    correct_answer = (
        non_negative_int(
            question.get(
                "correct_answer"
            )
        )
    )

    is_correct = (
        body.selected
        == correct_answer
    )

    final_answer = (
        index + 1
        >= len(question_ids)
    )

    answered_at = (
        datetime.now()
        .isoformat()
    )

    update = {
        "$inc": {
            "index":
                1,

            "answered":
                1,

            "correct": (
                1
                if is_correct
                else 0
            ),
        },

        "$push": {
            "answers": {
                "question_id":
                    question_id,

                "selected":
                    body.selected,

                "correct_answer":
                    correct_answer,

                "is_correct":
                    is_correct,

                "answered_at":
                    answered_at,
            }
        },
    }

    if final_answer:
        update["$set"] = {
            "status":
                "finished",

            "finished_at":
                answered_at,
        }

    result = (
        await exam_sessions
        .update_one(
            {
                "_id":
                    session["_id"],

                "status":
                    "active",

                "index":
                    index,
            },

            update,
        )
    )

    if result.modified_count != 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "این سؤال قبلاً "
                "پاسخ داده شده است"
            ),
        )

    # 👑 Prestige: FT چک → ثبت → رویداد پاسخ → (در پایانی: رویداد تکمیل آزمون)
    first_time = await _answer_first_time(user["id"], question_id)

    await db.save_answer(
        user["id"],
        question_id,
        body.selected,
        is_correct,
    )

    prestige = await _answer_prestige(
        user["id"], question, is_correct, first_time)

    prestige_exam = None
    promotion_result = None
    if final_answer and session.get("promotion"):
        # ⚔️ پایان چالش: نتیجه‌ی سرورمحور — بدون رویداد exam_complete
        # (چالش جزو آمار/XP آزمون‌ها شمرده نمی‌شود؛ پاسخ‌ها XP خود را گرفته‌اند)
        try:
            new_correct = non_negative_int(session.get("correct")) + (1 if is_correct else 0)
            answered_now = index + 1
            pct = round(new_correct / answered_now * 100, 1) if answered_now else 0
            apex = bool(session.get("apex"))
            need = db.CH_APEX_COUNT if apex else db.CH_COUNT
            pass_pct = db.CH_APEX_PASS_PCT if apex else db.CH_PASS_PCT
            won = answered_now >= need and pct >= pass_pct
            res = await db.challenge_resolve(user["id"], session, won, pct)
            promotion_result = {
                "win": bool(res.get("win")),
                "pct": pct,
                "pass_pct": pass_pct,
                "need": need,
                "apex": apex,
                "reward": ((db.CH_APEX_WIN if apex else db.CH_CHALLENGE_WIN)
                           if res.get("win") else 0),
                "celebration": res.get("celebration"),
                "cooldown_h": res.get("cooldown_h"),
                "cooldown_until": res.get("cooldown_until"),
                "target_rank": (session.get("target_rank")
                                or (session.get("view") or {}).get("target_rank")),
            }
        except Exception:
            promotion_result = None
    elif final_answer:
        try:
            new_correct = non_negative_int(session.get("correct")) + (1 if is_correct else 0)
            answered_now = index + 1
            pct = round(new_correct / answered_now * 100, 1) if answered_now else 0
            ev = await db.prestige_event(
                user["id"], 'exam_complete',
                {'pct': pct, 'total': len(question_ids)})
            prestige_exam = _pub_prestige(ev)
        except Exception:
            prestige_exam = None

    return {
        "is_correct":
            is_correct,

        "correct_answer":
            correct_answer,

        "explanation":
            text(
                question.get(
                    "explanation"
                )
            ),

        "progress":
            index + 1,

        "total":
            len(question_ids),

        "finished":
            final_answer,

        "prestige": prestige,
        "prestige_exam": prestige_exam,
        "promotion_result": promotion_result,
    }


@router.delete(
    "/custom-exam/{session_id}"
)
async def abandon_exam(
    session_id: str,

    user=Depends(
        get_current_user
    ),
):
    # ⚔️ رها کردن چالش ارتقا = Fail + کول‌داون (ضدتقلب — Spec §۳.۱)
    sess_doc = await exam_sessions.find_one(
        {"session_id": session_id, "user_id": user["id"],
         "status": "active"})
    result = (
        await exam_sessions
        .update_one(
            {
                "session_id":
                    session_id,

                "user_id":
                    user["id"],

                "status":
                    "active",
            },

            {
                "$set": {
                    "status":
                        "abandoned",

                    "finished_at":
                        datetime.now()
                        .isoformat(),
                }
            },
        )
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail=(
                "آزمون فعال "
                "پیدا نشد"
            ),
        )

    promotion_result = None
    if (sess_doc or {}).get("promotion"):
        try:
            _ans = int(sess_doc.get("answered", 0) or 0)
            _cor = int(sess_doc.get("correct", 0) or 0)
            res = await db.challenge_resolve(
                user["id"], sess_doc, False,
                round(_cor / _ans * 100, 1) if _ans else 0)
            promotion_result = {
                "win": False,
                "pct": res.get("pct"),
                "cooldown_h": res.get("cooldown_h"),
                "cooldown_until": res.get("cooldown_until"),
            }
        except Exception:
            promotion_result = None

    return {
        "ok": True,
        "promotion_result": promotion_result,
    }


class QuestionDesignInput(
    BaseModel
):
    lesson: str = Field(
        min_length=1,
        max_length=100,
    )

    topic: str = Field(
        min_length=1,
        max_length=100,
    )

    question: str = Field(
        min_length=10,
        max_length=2000,
    )

    options: List[str] = Field(
        min_length=4,
        max_length=4,
    )

    correct: int = Field(
        ge=0,
        le=3,
    )

    explanation: Optional[str] = Field(
        default="",
        max_length=3000,
    )

    difficulty: str = (
        "متوسط 🟡"
    )


def design_data(
    body: QuestionDesignInput,
) -> dict:
    options = [
        " ".join(item.split())
        for item in body.options
    ]

    if (
        any(
            not item
            for item in options
        )
        or len(set(options)) != 4
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "چهار گزینه متفاوت "
                "و غیرخالی لازم است"
            ),
        )

    difficulty = (
        body.difficulty
        if body.difficulty
        in ALLOWED_DIFFICULTIES
        else "متوسط 🟡"
    )

    return {
        "lesson":
            " ".join(
                body.lesson.split()
            ),

        "topic":
            " ".join(
                body.topic.split()
            ),

        "difficulty":
            difficulty,

        "question":
            " ".join(
                body.question.split()
            ),

        "options":
            options,

        "correct_answer":
            body.correct,

        "explanation":
            str(
                body.explanation
                or ""
            ).strip(),
    }


@router.post("/design")
async def design(
    body: QuestionDesignInput,

    user=Depends(
        get_current_user
    ),
):
    data = design_data(body)

    database_user = user["_db"]

    privileged = (
        user["id"] == ADMIN_ID
        or database_user.get(
            "role"
        ) in {
            "admin",
            "content_admin",
        }
    )

    result = (
        await db.questions
        .insert_one({
            **data,

            "creator_id":
                user["id"],

            # 🏷 Identity v1 — سطح اجتماعی: display_name
            "creator_name":
                db.display_name_of(database_user)
                if isinstance(database_user, Mapping)
                else "",

            "approved":
                privileged,

            "source":
                "webapp",

            "created_at":
                datetime.now()
                .isoformat(),

            "attempt_count":
                0,

            "correct_count":
                0,
        })
    )

    if not privileged:
        try:
            collection = (
                db.client[
                    "medicalbot"
                ][
                    "bot_notifications"
                ]
            )

            await collection.insert_one({
                "type":
                    "new_question_design",

                "chat_id":
                    ADMIN_ID,

                "text": (
                    "🔔 <b>سؤال جدید</b>"

                    f"\n✏️ "
                    f"{escape(str(database_user.get('name', '')))}"

                    f"\n📚 "
                    f"{escape(data['lesson'])}"
                    f" — "
                    f"{escape(data['topic'])}"
                ),

                "sent":
                    False,

                "created_at":
                    datetime.now()
                    .isoformat(),
            })

        except Exception:
            pass

    return {
        "ok": True,

        "question_id":
            str(
                result.inserted_id
            ),

        "auto_approved":
            privileged,

        "message": (
            "✅ ثبت شد!"
            if privileged
            else
            "✅ بعد از تأیید ادمین نمایش داده می‌شود."
        ),
    }


@router.get("/my-designs")
async def my_designs(
    user=Depends(
        get_current_user
    ),
):
    documents = (
        await db.questions
        .find({
            "creator_id":
                user["id"],
        })
        .sort(
            "created_at",
            -1,
        )
        .to_list(100)
    )

    result = []

    for document in documents:
        formatted = (
            safe_question(
                document
            )
        )

        if not formatted:
            continue

        approved = bool(
            document.get(
                "approved"
            )
        )

        result.append({
            **formatted,

            "approved":
                approved,

            "status": (
                "approved"
                if approved
                else "pending"
            ),

            "created_at":
                text(
                    document.get(
                        "created_at"
                    )
                )[:10],

            "correct":
                non_negative_int(
                    document.get(
                        "correct_answer"
                    )
                ),

            "explanation":
                text(
                    document.get(
                        "explanation"
                    )
                ),
        })

    return {
        "questions": result,
    }


@router.put(
    "/my-designs/{question_id}"
)
async def update_my_design(
    question_id: str,
    body: QuestionDesignInput,

    user=Depends(
        get_current_user
    ),
):
    if not ObjectId.is_valid(
        question_id
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "شناسه سؤال "
                "نامعتبر است"
            ),
        )

    existing = (
        await db.questions.find_one(
            {
                "_id":
                    ObjectId(
                        question_id
                    ),

                "creator_id":
                    user["id"],
            }
        )
    )

    if not existing:
        raise HTTPException(
            status_code=404,
            detail="سؤال پیدا نشد",
        )

    if existing.get("approved"):
        raise HTTPException(
            status_code=409,
            detail=(
                "سؤال تأییدشده "
                "قابل ویرایش نیست"
            ),
        )

    await db.questions.update_one(
        {
            "_id":
                existing["_id"],
        },

        {
            "$set": {
                **design_data(body),

                "updated_at":
                    datetime.now()
                    .isoformat(),
            }
        },
    )

    return {
        "ok": True,
    }


@router.delete(
    "/my-designs/{question_id}"
)
async def delete_my_design(
    question_id: str,

    user=Depends(
        get_current_user
    ),
):
    if not ObjectId.is_valid(
        question_id
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "شناسه سؤال "
                "نامعتبر است"
            ),
        )

    result = (
        await db.questions
        .delete_one(
            {
                "_id":
                    ObjectId(
                        question_id
                    ),

                "creator_id":
                    user["id"],

                "approved": {
                    "$ne": True,
                },
            }
        )
    )

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail=(
                "فقط سؤال تأییدنشده "
                "قابل حذف است"
            ),
        )

    return {
        "ok": True,
    }

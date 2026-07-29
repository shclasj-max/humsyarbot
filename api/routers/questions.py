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

    await db.save_answer(
        user["id"],
        body.question_id,
        body.selected,
        is_correct,
    )

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

    await db.save_answer(
        user["id"],
        question_id,
        body.selected,
        is_correct,
    )

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

    return {
        "ok": True,
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

            "creator_name":
                database_user.get(
                    "name",
                    "",
                ),

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

"""Unified Mini App search across educational content."""

import asyncio
import re

from fastapi import (
    APIRouter,
    Depends,
    Query,
)

from api.auth import (
    get_current_user,
)

from database import db


router = APIRouter()


def text(
    value,
) -> str:
    return str(
        value or ""
    ).strip()


@router.get("")
async def search(
    q: str = Query(
        ...,
        min_length=2,
        max_length=100,
    ),

    user=Depends(
        get_current_user
    ),
):
    query = " ".join(
        q.split()
    )

    pattern = {
        "$regex":
            re.escape(query),

        "$options":
            "i",
    }


    (
        resources,
        questions,
        faqs,
        schedules,
        subjects,
        books,
        qbank,
    ) = await asyncio.gather(
        db.search_resources(
            query
        ),

        db.questions.find({
            "approved":
                True,

            "$or": [
                {
                    "question":
                        pattern,
                },

                {
                    "lesson":
                        pattern,
                },

                {
                    "topic":
                        pattern,
                },
            ],
        })
        .limit(10)
        .to_list(10),

        db.faq.find({
            "$or": [
                {
                    "question":
                        pattern,
                },

                {
                    "answer":
                        pattern,
                },
            ],
        })
        .limit(10)
        .to_list(10),

        db.schedules.find({
            "$or": [
                {
                    "lesson":
                        pattern,
                },

                {
                    "teacher":
                        pattern,
                },

                {
                    "notes":
                        pattern,
                },
            ],
        })
        .sort(
            "date",
            -1,
        )
        .limit(10)
        .to_list(10),

        db.ref_subjects.find({
            "name":
                pattern,
        })
        .limit(10)
        .to_list(10),

        db.ref_books.find({
            "name":
                pattern,
        })
        .limit(10)
        .to_list(10),

        db.qbank_files.find({
            "$or": [
                {
                    "lesson":
                        pattern,
                },

                {
                    "topic":
                        pattern,
                },

                {
                    "description":
                        pattern,
                },
            ],
        })
        .limit(10)
        .to_list(10),
    )


    results = []


    for item in (
        resources or []
    )[:10]:
        subtitle = " • ".join(
            filter(
                None,
                [
                    text(
                        item.get(
                            "lesson_name"
                        )
                    ),

                    text(
                        item.get(
                            "session_topic"
                        )
                    ),
                ],
            )
        )

        results.append({
            "id":
                text(
                    item.get("_id")
                ),

            "type":
                "resource",

            "icon":
                "📗",

            "title": (
                text(
                    item.get("name")
                )
                or "منبع آموزشی"
            ),

            "subtitle":
                subtitle,

            "route":
                "/learn/resources",
        })


    for item in questions:
        subtitle = " • ".join(
            filter(
                None,
                [
                    text(
                        item.get(
                            "lesson"
                        )
                    ),

                    text(
                        item.get(
                            "topic"
                        )
                    ),
                ],
            )
        )

        results.append({
            "id":
                text(
                    item.get("_id")
                ),

            "type":
                "question",

            "icon":
                "🧪",

            "title":
                text(
                    item.get(
                        "question"
                    )
                )[:140],

            "subtitle":
                subtitle,

            "route":
                "/learn/questions",
        })


    for item in faqs:
        results.append({
            "id":
                text(
                    item.get("_id")
                ),

            "type":
                "faq",

            "icon":
                "❓",

            "title":
                text(
                    item.get(
                        "question"
                    )
                ),

            "subtitle": (
                text(
                    item.get(
                        "category"
                    )
                )
                or "راهنما"
            ),

            "route":
                "/me/faq",
        })


    for item in schedules:
        subtitle = " • ".join(
            filter(
                None,
                [
                    text(
                        item.get(
                            "date"
                        )
                    ),

                    text(
                        item.get(
                            "time"
                        )
                    ),

                    text(
                        item.get(
                            "teacher"
                        )
                    ),
                ],
            )
        )

        results.append({
            "id":
                text(
                    item.get("_id")
                ),

            "type":
                "schedule",

            "icon":
                "📅",

            "title": (
                text(
                    item.get(
                        "lesson"
                    )
                )
                or "برنامه درسی"
            ),

            "subtitle":
                subtitle,

            "route":
                "/schedule",
        })


    for item in subjects:
        results.append({
            "id":
                text(
                    item.get("_id")
                ),

            "type":
                "reference",

            "icon":
                "📘",

            "title":
                text(
                    item.get("name")
                ),

            "subtitle":
                "موضوع رفرنس",

            "route":
                "/learn/references",
        })


    for item in books:
        results.append({
            "id":
                text(
                    item.get("_id")
                ),

            "type":
                "reference",

            "icon":
                "📕",

            "title":
                text(
                    item.get("name")
                ),

            "subtitle":
                "کتاب مرجع",

            "route":
                "/learn/references",
        })


    for item in qbank:
        title = " • ".join(
            filter(
                None,
                [
                    text(
                        item.get(
                            "lesson"
                        )
                    ),

                    text(
                        item.get(
                            "topic"
                        )
                    ),
                ],
            )
        )

        results.append({
            "id":
                text(
                    item.get("_id")
                ),

            "type":
                "qbank",

            "icon":
                "📦",

            "title": (
                title
                or "بانک فایل سؤال"
            ),

            "subtitle":
                text(
                    item.get(
                        "description"
                    )
                ),

            "route":
                "/learn/resources",
        })


    order = {
        "question": 0,
        "resource": 1,
        "qbank": 2,
        "reference": 3,
        "schedule": 4,
        "faq": 5,
    }


    results.sort(
        key=lambda item:
            order.get(
                item["type"],
                99,
            )
    )


    return {
        "query":
            query,

        "results":
            results[:50],

        "total":
            len(results),
    }

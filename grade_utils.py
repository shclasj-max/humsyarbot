"""Shared grade normalization helpers."""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping


def safe_text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    return str(value).strip()


def finite_number(
    value: Any,
) -> float | None:
    """Convert values to a finite number.

    Invalid, empty, infinite and boolean values
    return None and cannot crash calculations.
    """

    if (
        value is None
        or isinstance(value, bool)
    ):
        return None

    try:
        number = float(value)
    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        return None

    if not math.isfinite(number):
        return None

    return number


def display_number(
    value: float,
) -> int | float:
    """Remove unnecessary .0 from numbers."""

    rounded = round(value, 2)

    if rounded.is_integer():
        return int(rounded)

    return rounded


def normalize_grade(
    record: Mapping[str, Any] | None,
) -> dict | None:
    """Normalize one grade database record."""

    if not isinstance(record, Mapping):
        return None

    max_score = finite_number(
        record.get("max_score")
    )

    if (
        max_score is None
        or max_score <= 0
    ):
        max_score = 20.0

    score = finite_number(
        record.get("score")
    )

    if (
        score is not None
        and score < 0
    ):
        score = None

    if score is None:
        percentage = None
        normalized_score = None
        output_score = None

    else:
        raw_percentage = (
            score / max_score
        ) * 100

        percentage = round(
            max(
                0,
                min(
                    100,
                    raw_percentage,
                ),
            ),
            1,
        )

        raw_normalized = (
            score / max_score
        ) * 20

        normalized_score = round(
            max(
                0,
                min(
                    20,
                    raw_normalized,
                ),
            ),
            2,
        )

        output_score = display_number(
            score
        )

    exam_date = safe_text(
        record.get("exam_date")
    )

    if (
        len(exam_date) >= 10
        and exam_date[4:5] == "-"
        and exam_date[7:8] == "-"
    ):
        exam_date = exam_date[:10]

    return {
        "id": safe_text(
            record.get("_id")
        ),

        "lesson": safe_text(
            record.get("lesson")
        ),

        "exam_title": safe_text(
            record.get("exam_title")
        ),

        "score": output_score,

        "max_score": display_number(
            max_score
        ),

        "exam_date": exam_date,

        "note": safe_text(
            record.get("note")
        ),

        "percentage": percentage,

        "normalized_score":
            normalized_score,
    }


def summarize_grades(
    records: Iterable[Any] | None,
) -> dict:
    """Normalize grades and calculate average.

    The average:
    - ignores invalid and empty scores;
    - converts every grade to a score out of 20;
    - never divides by all rows when some grades
      are empty;
    - cannot crash on old malformed records.
    """

    grades = []
    normalized_scores = []

    if not records:
        records = []

    for record in records:
        grade = normalize_grade(record)

        if grade is None:
            continue

        grades.append(grade)

        normalized_score = grade.get(
            "normalized_score"
        )

        if normalized_score is not None:
            normalized_scores.append(
                normalized_score
            )

    graded_count = len(
        normalized_scores
    )

    if graded_count:
        average = round(
            sum(normalized_scores)
            / graded_count,
            2,
        )

        average_percentage = round(
            (average / 20) * 100,
            1,
        )

    else:
        average = None
        average_percentage = None

    for grade in grades:
        grade.pop(
            "normalized_score",
            None,
        )

    return {
        "grades": grades,
        "avg": average,

        "avg_percentage":
            average_percentage,

        "total": len(grades),

        "graded_count":
            graded_count,
    }

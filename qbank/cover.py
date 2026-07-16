"""
📇 qbank.cover — صفحه‌ی جلد آزمون

شامل: لوگوی سامانه، نام سامانه، عنوان آزمون، و جدول اطلاعات
(درس/فصل/مبحث/تعداد سوال/تاریخ/کد آزمون/نام دانشجو).
"""
from reportlab.lib.units import mm

from qbank.fonts_rtl import rtl, fa_digits, REGULAR, MEDIUM, BOLD
from qbank.styles import (
    PAGE_W, PAGE_H, NAVY, NAVY_LIGHT, BRAND_GREEN,
    GRAY, TEXT_DARK, WHITE, CARD_BG, CARD_BORDER,
)


def _draw_logo(c, cx, cy, r):
    """
    لوگوی وکتوریِ ساده‌ی سامانه (بدون وابستگی به فایل تصویر خارجی —
    همیشه چاپ‌پذیر و با کیفیت بالا، در هر اندازه‌ای بدون افت کیفیت).
    """
    c.setFillColor(BRAND_GREEN)
    c.circle(cx, cy, r, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont(BOLD, r * 0.9)
    c.drawCentredString(cx, cy - r * 0.32, rtl("ها"))


def _today_jalali() -> str:
    try:
        from utils import fmt_jalali, now_tehran
        return fmt_jalali(now_tehran().strftime('%Y-%m-%d'))
    except Exception:
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d')


def draw_cover_page(c, meta, question_count: int):
    """صفحه‌ی اول PDF را کامل رسم می‌کند (فرض بر این‌ست که c تازه showPage شده یا صفحه‌ی خالی اول است)"""
    cy = PAGE_H - 55 * mm
    _draw_logo(c, PAGE_W / 2, cy, 14 * mm)

    c.setFont(BOLD, 20)
    c.setFillColor(NAVY)
    c.drawCentredString(PAGE_W / 2, cy - 24 * mm, rtl("هامزیار"))

    c.setFont(REGULAR, 10)
    c.setFillColor(GRAY)
    c.drawCentredString(PAGE_W / 2, cy - 30 * mm, rtl("@humsyarbot  —  سامانه‌ی آموزشی دانشجویان پزشکی"))

    # خط جداکننده
    y = cy - 42 * mm
    c.setStrokeColor(CARD_BORDER)
    c.setLineWidth(1)
    c.line(PAGE_W / 2 - 30 * mm, y, PAGE_W / 2 + 30 * mm, y)

    # عنوان آزمون
    y -= 14 * mm
    c.setFont(BOLD, 18)
    c.setFillColor(TEXT_DARK)
    c.drawCentredString(PAGE_W / 2, y, rtl(f"آزمون بانک سوال — {meta.lesson}"))

    # جدول اطلاعات
    y -= 18 * mm
    rows = [("درس", meta.lesson)]
    if meta.chapter:
        rows.append(("فصل", meta.chapter))
    rows.append(("مبحث", meta.topic if meta.topic and meta.topic != 'همه' else 'همه‌ی مباحث'))
    if meta.difficulty:
        rows.append(("سطح سختی", meta.difficulty))
    rows.append(("تعداد سوالات", fa_digits(question_count)))
    rows.append(("تاریخ تولید", _today_jalali()))
    rows.append(("کد آزمون", meta.exam_code))
    if meta.student_name:
        rows.append(("نام دانشجو", meta.student_name))

    box_w = 120 * mm
    row_h = 9 * mm
    box_h = row_h * len(rows)
    box_x = (PAGE_W - box_w) / 2
    box_top = y

    c.setFillColor(CARD_BG)
    c.roundRect(box_x, box_top - box_h, box_w, box_h, 3 * mm, fill=1, stroke=0)
    c.setStrokeColor(CARD_BORDER)
    c.setLineWidth(0.8)
    c.roundRect(box_x, box_top - box_h, box_w, box_h, 3 * mm, fill=0, stroke=1)

    ry = box_top - row_h / 2 - 3
    for i, (label, value) in enumerate(rows):
        if i > 0:
            c.setStrokeColor(CARD_BORDER)
            c.setLineWidth(0.5)
            c.line(box_x + 6 * mm, box_top - i * row_h, box_x + box_w - 6 * mm, box_top - i * row_h)
        c.setFont(MEDIUM, 10)
        c.setFillColor(GRAY)
        c.drawRightString(box_x + box_w - 6 * mm, ry, rtl(label))
        c.setFont(BOLD, 10.5)
        c.setFillColor(NAVY_LIGHT)
        c.drawString(box_x + 6 * mm, ry, rtl(str(value)))
        ry -= row_h

    # پانویس جلد
    c.setFont(REGULAR, 8.5)
    c.setFillColor(GRAY)
    c.drawCentredString(PAGE_W / 2, 20 * mm,
                         rtl("این آزمون به‌صورت خودکار توسط ربات هامیار تولید شده است."))

"""
📅 schedule_pdf — خروجی زیبای PDF از برنامه‌ی کلاس/امتحان/جبرانی

از همون موتور فونت فارسی (Vazirmatn) و رنگ‌های برند هامزیار که برای
PDF بانک سوال (qbank/) ساخته شده استفاده می‌کند تا کاملاً یکدست و
هم‌خانواده با بقیه‌ی خروجی‌های ربات باشد — بدون تکرار کدِ فونت/رنگ.
"""
import io
import logging
from datetime import datetime

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor

from qbank.fonts_rtl import ensure_fonts, rtl, fa_digits, wrap_rtl, REGULAR, MEDIUM, BOLD
from qbank.styles import (
    PAGE_W, PAGE_H, MARGIN, CONTENT_W, MIN_Y, FOOTER_Y,
    NAVY, NAVY_LIGHT, BRAND_GREEN, GRAY, TEXT_DARK, WHITE, CARD_BORDER,
)

logger = logging.getLogger(__name__)

_EXAM_RED = HexColor('#c62828')
_ZEBRA_BG = HexColor('#f7f8fa')

# ── رنگ هر نوع برنامه (هم‌خانواده با آیکون‌های TYPE_NAMES در schedule.py) ──
TYPE_STYLE = {
    'class':  ('📖', 'کلاس',   NAVY_LIGHT),
    'exam':   ('📝', 'امتحان', _EXAM_RED),
    'makeup': ('🔄', 'جبرانی', BRAND_GREEN),
}

_COL = {
    'type': 20 * mm, 'lesson': 44 * mm, 'date': 38 * mm,
    'time': 20 * mm, 'location': 30 * mm,
}
_COL['teacher'] = CONTENT_W - sum(_COL.values())
ROW_H = 12 * mm


def _draw_logo(c, cx, cy, r):
    c.setFillColor(BRAND_GREEN)
    c.circle(cx, cy, r, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont(BOLD, r * 0.9)
    c.drawCentredString(cx, cy - r * 0.32, rtl("ها"))


def _weekday_fa(date_str: str) -> str:
    try:
        from utils import jalali_weekday_index, JALALI_WEEK_SAT_FIRST
        return JALALI_WEEK_SAT_FIRST[jalali_weekday_index(date_str)]
    except Exception:
        return ''


def _today_jalali() -> str:
    try:
        from utils import fmt_jalali
        return fmt_jalali(datetime.now().strftime('%Y-%m-%d'))
    except Exception:
        return datetime.now().strftime('%Y-%m-%d')


def _draw_header(c, group_label: str, student_name: str, count: int) -> float:
    cy = PAGE_H - 30 * mm
    _draw_logo(c, PAGE_W / 2, cy, 11 * mm)

    c.setFont(BOLD, 17)
    c.setFillColor(NAVY)
    c.drawCentredString(PAGE_W / 2, cy - 18 * mm, rtl("هامزیار"))

    c.setFont(REGULAR, 9)
    c.setFillColor(GRAY)
    c.drawCentredString(PAGE_W / 2, cy - 23.5 * mm, rtl("@humsyarbot  —  سامانه‌ی آموزشی دانشجویان پزشکی"))

    y = cy - 33 * mm
    c.setFont(BOLD, 15)
    c.setFillColor(TEXT_DARK)
    c.drawCentredString(PAGE_W / 2, y, rtl("📅 برنامه‌ی کلاس‌ها و امتحانات"))

    y -= 7 * mm
    meta_parts = [f"گروه {group_label}", f"{fa_digits(count)} مورد", _today_jalali()]
    if student_name:
        meta_parts.insert(0, student_name)
    c.setFont(MEDIUM, 9.5)
    c.setFillColor(NAVY_LIGHT)
    c.drawCentredString(PAGE_W / 2, y, rtl("  •  ".join(meta_parts)))

    y -= 8 * mm
    c.setStrokeColor(CARD_BORDER)
    c.setLineWidth(1)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    return y - 10 * mm


def _draw_table_header(c, y: float) -> float:
    x = PAGE_W - MARGIN
    c.setFillColor(NAVY)
    c.roundRect(MARGIN, y - ROW_H, CONTENT_W, ROW_H, 2 * mm, fill=1, stroke=0)
    c.setFont(BOLD, 9.5)
    c.setFillColor(WHITE)
    labels = [('type', 'نوع'), ('lesson', 'درس'), ('date', 'تاریخ'),
              ('time', 'ساعت'), ('location', 'مکان'), ('teacher', 'استاد')]
    cx = x
    mid = y - ROW_H / 2 - 1.6
    for key, label in labels:
        w = _COL[key]
        c.drawCentredString(cx - w / 2, mid, rtl(label))
        cx -= w
    return y - ROW_H


def _draw_row(c, item: dict, y: float, zebra: bool):
    from utils import fmt_jalali
    x = PAGE_W - MARGIN
    if zebra:
        c.setFillColor(_ZEBRA_BG)
        c.rect(MARGIN, y - ROW_H, CONTENT_W, ROW_H, fill=1, stroke=0)
    c.setStrokeColor(CARD_BORDER)
    c.setLineWidth(0.5)
    c.line(MARGIN, y - ROW_H, PAGE_W - MARGIN, y - ROW_H)

    mid = y - ROW_H / 2 - 1.6
    icon, type_label, type_color = TYPE_STYLE.get(item.get('type', 'class'), TYPE_STYLE['class'])

    # نوع (بج رنگی)
    cx = x
    w = _COL['type']
    badge_w, badge_h = w - 6 * mm, 6.5 * mm
    c.setFillColor(type_color)
    c.roundRect(cx - w / 2 - badge_w / 2, y - ROW_H / 2 - badge_h / 2, badge_w, badge_h, 2 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont(BOLD, 8)
    c.drawCentredString(cx - w / 2, y - ROW_H / 2 - 1.4, rtl(f"{icon} {type_label}"))
    cx -= w

    # درس
    w = _COL['lesson']
    c.setFont(BOLD, 9.5)
    c.setFillColor(TEXT_DARK)
    lesson_lines = wrap_rtl(item.get('lesson', ''), BOLD, 9.5, w - 4 * mm)[:2]
    ly = mid + (2 if len(lesson_lines) > 1 else 0)
    for line in lesson_lines:
        c.drawCentredString(cx - w / 2, ly, line)
        ly -= 4 * mm
    cx -= w

    # تاریخ (+ روز هفته)
    w = _COL['date']
    wd = _weekday_fa(item.get('date', ''))
    c.setFont(MEDIUM, 9)
    c.setFillColor(NAVY_LIGHT)
    c.drawCentredString(cx - w / 2, mid + 1.8, fa_digits(fmt_jalali(item.get('date', ''))))
    c.setFont(REGULAR, 7.5)
    c.setFillColor(GRAY)
    c.drawCentredString(cx - w / 2, mid - 2.8, rtl(wd))
    cx -= w

    # ساعت
    w = _COL['time']
    c.setFont(MEDIUM, 9.5)
    c.setFillColor(TEXT_DARK)
    c.drawCentredString(cx - w / 2, mid, fa_digits(item.get('time', '')))
    cx -= w

    # مکان
    w = _COL['location']
    c.setFont(REGULAR, 8.5)
    c.setFillColor(TEXT_DARK)
    loc_lines = wrap_rtl(item.get('location', ''), REGULAR, 8.5, w - 4 * mm)[:1]
    for line in loc_lines:
        c.drawCentredString(cx - w / 2, mid, line)
    cx -= w

    # استاد
    w = _COL['teacher']
    c.setFont(REGULAR, 8.5)
    c.setFillColor(TEXT_DARK)
    teacher_lines = wrap_rtl(item.get('teacher', ''), REGULAR, 8.5, w - 4 * mm)[:1]
    for line in teacher_lines:
        c.drawCentredString(cx - w / 2, mid, line)


def _draw_footer(c, page_num: int):
    c.setStrokeColor(CARD_BORDER)
    c.setLineWidth(0.6)
    c.line(MARGIN, FOOTER_Y, PAGE_W - MARGIN, FOOTER_Y)
    c.setFont(REGULAR, 8)
    c.setFillColor(GRAY)
    c.drawCentredString(PAGE_W / 2, FOOTER_Y - 5.5 * mm,
                         rtl(f"تولید شده توسط ربات هامزیار (@humsyarbot)  •  صفحه {fa_digits(page_num)}"))


def generate_schedule_pdf(items: list, group_label: str, student_name: str = '') -> bytes:
    """
    items: خروجی db.get_schedules() — لیست دیکشنری با کلیدهای
    type/lesson/teacher/date/time/location (date به فرمت %Y-%m-%d میلادی)
    """
    ensure_fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    page_num = 1

    y = _draw_header(c, group_label, student_name, len(items))
    y = _draw_table_header(c, y)

    for i, item in enumerate(items):
        if y - ROW_H < MIN_Y:
            _draw_footer(c, page_num)
            c.showPage()
            page_num += 1
            y = PAGE_H - MARGIN
            y = _draw_table_header(c, y)
        _draw_row(c, item, y, zebra=(i % 2 == 1))
        y -= ROW_H

    _draw_footer(c, page_num)
    c.save()
    buf.seek(0)
    return buf.getvalue()

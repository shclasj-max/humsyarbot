"""
🏗️ qbank.builder — Orchestrator نهایی

این تنها ماژولی است که همه‌ی بخش‌ها (کاور، کارت سوال، پاسخنامه، پاسخ
تشریحی) را کنار هم می‌چیند و خروجی نهایی PDF (bytes) را می‌سازد. خودش
هیچ منطق رسم مستقیمی ندارد — فقط تصمیم می‌گیرد «کِی» و «کدام» بخش
رسم شود و کِی صفحه عوض شود.

دو حالت پشتیبانی می‌شود:
    mode='practice' (پیش‌فرض) → پاسخ و تحلیل بلافاصله زیر هر سوال
        (دقیقاً همان استایلی که در تصویر نمونه دیده شد — برای تمرین آزاد)
    mode='exam' → سوالات بدون پاسخ، سپس یک صفحه‌ی «پاسخنامه»، سپس
        صفحات «پاسخ تشریحی» — دقیقاً مثل یک دفترچه‌ی آزمون رسمی

هر دو حالت کاور یکسان دارند (لوگو، عنوان، جدول اطلاعات، کد آزمون).
"""
import io
import logging

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from qbank.fonts_rtl import ensure_fonts, rtl, fa_digits, REGULAR, BOLD
from qbank.styles import PAGE_W, PAGE_H, MARGIN, MIN_Y, FOOTER_Y, NAVY_LIGHT, GRAY, CARD_BORDER
from qbank.query import ExamMeta
from qbank.cover import draw_cover_page
from qbank.question_card import draw_question_card, measure_card_height
from qbank.answer_key import draw_answer_key_header, draw_answer_key_grid, CELL_H
from qbank.explanations import draw_explanations_header, draw_explanation_block, measure_explanation_height

logger = logging.getLogger(__name__)


def _draw_footer(c, page_num: int):
    c.setStrokeColor(CARD_BORDER)
    c.setLineWidth(0.6)
    c.line(MARGIN, FOOTER_Y, PAGE_W - MARGIN, FOOTER_Y)
    c.setFont(REGULAR, 8)
    c.setFillColor(GRAY)
    c.drawCentredString(PAGE_W / 2, FOOTER_Y - 5.5 * mm,
                         rtl(f"تولید شده توسط ربات هامزیار (@humsyarbot)  •  صفحه {fa_digits(page_num)}"))


def _draw_section_header(c, lesson: str, topic: str) -> float:
    """هدر فشرده‌ی صفحات دوم‌به‌بعدِ بخش سوالات"""
    y = PAGE_H - MARGIN
    c.setFont(BOLD, 13)
    c.setFillColor(NAVY_LIGHT)
    title = f"بانک سوال — {lesson}" + (f" ({topic})" if topic and topic != 'همه' else '')
    c.drawRightString(PAGE_W - MARGIN, y, rtl(title))
    y -= 6 * mm
    c.setStrokeColor(CARD_BORDER)
    c.setLineWidth(0.8)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    return y - 9 * mm


def generate_exam_pdf(questions: list, meta: ExamMeta, mode: str = 'practice',
                       question_images: dict = None, answer_images: dict = None) -> bytes:
    """
    نقطه‌ی ورود اصلی. همه‌چیز را می‌سازد و bytes نهایی PDF را برمی‌گرداند.

    questions: خروجی qbank.query.fetch_exam_questions (لیست دیکشنری)
    meta: qbank.query.ExamMeta
    mode: 'practice' یا 'exam'
    question_images/answer_images: dict اختیاری {question_id: ImageReader}
        — این ماژول کاملاً از تلگرام/دانلود فایل بی‌خبر است؛ فراخوان
        (questions.py) مسئول دانلود و آماده‌سازی ImageReader است. این
        جداسازی یعنی بعداً می‌شود منبع تصویر را بدون تغییر این فایل
        عوض کرد.
    """
    ensure_fonts()
    question_images = question_images or {}
    answer_images = answer_images or {}
    show_answer_inline = (mode == 'practice')

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    page_num = 1

    # ── جلد ──
    draw_cover_page(c, meta, len(questions))
    _draw_footer(c, page_num)
    c.showPage()
    page_num += 1

    # ── صفحات سوالات ──
    y = _draw_section_header(c, meta.lesson, meta.topic)
    for i, q in enumerate(questions, 1):
        qid = str(q.get('_id', i))
        q_img = question_images.get(qid)
        a_img = answer_images.get(qid) if show_answer_inline else None

        needed = measure_card_height(q, show_answer_inline, q_img)
        if y - needed < MIN_Y:
            _draw_footer(c, page_num)
            c.showPage()
            page_num += 1
            y = _draw_section_header(c, meta.lesson, meta.topic)

        y = draw_question_card(c, q, i, y, show_answer=show_answer_inline,
                                question_image=q_img, answer_image=a_img)

    if mode == 'exam':
        # ── پاسخنامه ──
        _draw_footer(c, page_num)
        c.showPage()
        page_num += 1
        y = draw_answer_key_header(c, meta.exam_code)
        remaining = questions
        while remaining:
            rows_left = int((y - MIN_Y) // CELL_H)
            take = min(len(remaining), max(rows_left, 1) * 5)
            chunk, remaining = remaining[:take], remaining[take:]
            y = draw_answer_key_grid(c, chunk, y)
            if remaining:
                _draw_footer(c, page_num)
                c.showPage()
                page_num += 1
                y = PAGE_H - MARGIN

        # ── پاسخ تشریحی ──
        _draw_footer(c, page_num)
        c.showPage()
        page_num += 1
        y = draw_explanations_header(c)
        for i, q in enumerate(questions, 1):
            qid = str(q.get('_id', i))
            a_img = answer_images.get(qid)
            needed = measure_explanation_height(q, a_img)
            if y - needed < MIN_Y:
                _draw_footer(c, page_num)
                c.showPage()
                page_num += 1
                y = draw_explanations_header(c)
            y = draw_explanation_block(c, q, i, y, answer_image=a_img)

    _draw_footer(c, page_num)
    c.save()
    buf.seek(0)
    return buf.getvalue()

"""
📊 سیستم نمرات
  ✅ ثبت دسته‌ای با اسم دانشجو (نه یکی‌یکی)
  ✅ درس‌ها از همون لیست دروس موجود در دیتابیس (bs_lessons) — چیز جدیدی تعریف نمی‌شود
  ✅ نقش «نماینده‌ی ورودی» فقط می‌تواند برای دانشجویان همان ورودی ثبت کند
  ✅ نوتیف فوری به هر دانشجو بعد از ثبت نمره
"""
import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from utils import fmt_jalali_dt, safe_send

logger = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))


async def _get_intake_scope(uid: int):
    """None برای ADMIN_ID (بدون محدودیت) — کد ورودی برای نماینده"""
    if uid == ADMIN_ID:
        return None
    role_doc = await db.get_admin_role(uid)
    if role_doc and role_doc.get('role') == 'grade_rep':
        return role_doc.get('scope_intake')
    return '__no_access__'


# ══════════════════════════════════════════════════
#  مرحله ۱: انتخاب درس
# ══════════════════════════════════════════════════

async def _start_new_grade(query, context):
    scope = await _get_intake_scope(query.from_user.id)
    if scope == '__no_access__':
        await query.answer("❌ دسترسی ندارید.", show_alert=True)
        return
    context.user_data['grade_intake_scope'] = scope

    lessons = await db.get_lessons()
    if not lessons:
        await query.answer("❌ هنوز هیچ درسی توی دیتابیس تعریف نشده.", show_alert=True)
        return
    context.user_data['grades_lesson_options'] = lessons
    keyboard = [[InlineKeyboardButton(l, callback_data=f'grades:lesson_pick:{i}')] for i, l in enumerate(lessons)]
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:main')])
    scope_txt = f"\nمحدود به ورودی: <b>{scope}</b>" if scope else ""
    await query.edit_message_text(
        f"📊 <b>ثبت نمره‌ی جدید</b>\n━━━━━━━━━━━━━━━━\n\nاول درس رو انتخاب کن:{scope_txt}",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _pick_lesson(query, context, idx: int):
    lessons = context.user_data.get('grades_lesson_options', [])
    if idx >= len(lessons):
        await query.answer("❌ منقضی شد، دوباره از اول شروع کن.", show_alert=True)
        return
    context.user_data['grade_lesson'] = lessons[idx]
    context.user_data['mode'] = 'grades_exam_title'
    await query.edit_message_text(
        f"📚 درس: <b>{lessons[idx]}</b>\n\n"
        "حالا عنوان امتحان رو بنویس (مثلاً «میان‌ترم» یا «پایان‌ترم بهمن ۱۴۰۳»):",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='admin:main')]])
    )


async def handle_exam_title_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("❌ عنوان نمی‌تواند خالی باشد.")
        return
    context.user_data['grade_exam_title'] = title
    context.user_data['mode'] = 'grades_bulk_list'
    scope = context.user_data.get('grade_intake_scope')
    scope_txt = f"\n\n⚠️ فقط دانشجویان ورودی <b>{scope}</b> پیدا می‌شوند." if scope else ""
    await update.message.reply_text(
        "📋 <b>لیست نمرات رو بفرست</b>\n\n"
        "هر خط یک نفر، به این فرم:\n"
        "<code>نام دانشجو: نمره</code>\n\n"
        "مثال:\n<code>علی رضایی: 18.5\nسارا محمدی: 15\nحسین کریمی: 12.75</code>"
        f"{scope_txt}",
        parse_mode='HTML'
    )


# ══════════════════════════════════════════════════
#  مرحله ۲: پارس لیست + تطبیق نام + پیش‌نمایش تأیید
# ══════════════════════════════════════════════════

async def handle_bulk_list_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text
    scope = context.user_data.get('grade_intake_scope')
    lesson = context.user_data.get('grade_lesson')
    exam_title = context.user_data.get('grade_exam_title')
    if not lesson or not exam_title:
        await update.message.reply_text("❌ چیزی گم شده، دوباره از «📊 ثبت نمره‌ی جدید» شروع کن.")
        return

    matched, not_found, ambiguous = [], [], []
    for line in raw.splitlines():
        line = line.strip()
        if not line or ':' not in line:
            continue
        name_part, score_part = line.rsplit(':', 1)
        name = name_part.strip()
        try:
            score = float(score_part.strip())
        except ValueError:
            not_found.append(f"{name} (نمره نامعتبر: «{score_part.strip()}»)")
            continue
        if not (0 <= score <= 20):
            not_found.append(f"{name} (نمره باید بین ۰ تا ۲۰ باشد: {score})")
            continue

        candidates = await db.find_students_by_name(name, intake=scope)
        if len(candidates) == 1:
            matched.append({'user_id': candidates[0]['user_id'], 'name': candidates[0].get('name', name), 'score': score})
        elif len(candidates) == 0:
            not_found.append(name)
        else:
            ambiguous.append(name)

    if not matched and not not_found and not ambiguous:
        await update.message.reply_text(
            "❌ هیچ خطی به فرم درست شناسایی نشد.\nهر خط باید مثل این باشد: <code>نام: نمره</code>",
            parse_mode='HTML'
        )
        return

    context.user_data.pop('mode', None)
    context.user_data['grade_matched'] = matched

    lines = [f"📊 <b>پیش‌نمایش ثبت نمره</b>\n📚 {lesson} — {exam_title}\n━━━━━━━━━━━━━━━━"]
    if matched:
        lines.append(f"\n✅ <b>{len(matched)} نفر پیدا شد:</b>")
        for m in matched[:20]:
            lines.append(f"   • {m['name']}: {m['score']}")
        if len(matched) > 20:
            lines.append(f"   … و {len(matched)-20} نفر دیگر")
    if ambiguous:
        lines.append(f"\n⚠️ <b>{len(ambiguous)} نفر چند نتیجه داشتند (نادیده گرفته می‌شوند):</b>")
        lines.extend(f"   • {n}" for n in ambiguous[:10])
        lines.append("   (برای این‌ها از شماره دانشجویی/نام کامل‌تر دوباره بفرست)")
    if not_found:
        lines.append(f"\n❌ <b>{len(not_found)} نفر پیدا نشدند:</b>")
        lines.extend(f"   • {n}" for n in not_found[:10])

    if not matched:
        await update.message.reply_text("\n".join(lines), parse_mode='HTML')
        return

    keyboard = [
        [InlineKeyboardButton(f"✅ تأیید و ثبت {len(matched)} نفر", callback_data='grades:confirm')],
        [InlineKeyboardButton("❌ انصراف", callback_data='admin:main')],
    ]
    await update.message.reply_text("\n".join(lines), parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _confirm_and_save(query, context):
    matched = context.user_data.pop('grade_matched', [])
    lesson = context.user_data.pop('grade_lesson', None)
    exam_title = context.user_data.pop('grade_exam_title', None)
    context.user_data.pop('grade_intake_scope', None)
    context.user_data.pop('grades_lesson_options', None)
    if not matched or not lesson:
        await query.answer("❌ چیزی برای ثبت نبود.", show_alert=True)
        return

    exam_date = datetime.now().isoformat()
    entries = [{'user_id': m['user_id'], 'score': m['score']} for m in matched]
    saved = await db.grade_bulk_upsert(entries, lesson, exam_title, exam_date, query.from_user.id)

    sent = 0
    for rec in saved:
        verb = "به‌روزرسانی شد" if rec.get('_is_update') else "ثبت شد"
        ok = await safe_send(
            query.get_bot(), rec['student_id'],
            f"📊 <b>نمره‌ات {verb}!</b>\n\n"
            f"📚 درس: {lesson}\n📝 امتحان: {exam_title}\n"
            f"🎯 نمره: <b>{rec['score']}/20</b>",
            parse_mode='HTML'
        )
        if ok:
            sent += 1

    await query.edit_message_text(
        f"✅ <b>{len(saved)} نمره ثبت شد.</b>\nبه {sent} نفر نوتیف رفت.",
        parse_mode='HTML'
    )


# ══════════════════════════════════════════════════
#  مرور نمرات ثبت‌شده (ادمین/نماینده)
# ══════════════════════════════════════════════════

_PAGE_SIZE = 10


async def _show_recent_grades(query, page: int):
    scope = await _get_intake_scope(query.from_user.id)
    if scope == '__no_access__':
        await query.answer("❌ دسترسی ندارید.", show_alert=True)
        return
    total = await db.grade_count_recent(intake=scope)
    items = await db.grade_list_recent(skip=page * _PAGE_SIZE, limit=_PAGE_SIZE, intake=scope)

    lines = [f"📋 <b>نمرات ثبت‌شده</b> ({total})\n━━━━━━━━━━━━━━━━"]
    if not items:
        lines.append("چیزی ثبت نشده.")
    for g in items:
        user = await db.get_user(g['student_id'])
        name = user.get('name', str(g['student_id'])) if user else str(g['student_id'])
        lines.append(f"• {name} — {g['lesson']} ({g['exam_title']}): <b>{g['score']}/20</b>")

    keyboard = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f'grades:list:{page-1}'))
    if (page + 1) * _PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f'grades:list:{page+1}'))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:main')])
    await query.edit_message_text("\n".join(lines), parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════════
#  نمای دانشجو — «📊 نمرات من»
# ══════════════════════════════════════════════════

async def show_my_grades_msg(update: Update):
    uid = update.effective_user.id
    text = await _build_my_grades_text(uid)
    await update.message.reply_text(text, parse_mode='HTML')


async def _build_my_grades_text(uid: int) -> str:
    grades = await db.grade_list_for_student(uid)
    if not grades:
        return "📊 هنوز هیچ نمره‌ای برات ثبت نشده."
    lines = ["📊 <b>نمرات من</b>\n━━━━━━━━━━━━━━━━"]
    total = 0
    for g in grades:
        lines.append(f"📚 {g['lesson']} — {g['exam_title']}\n   🎯 <b>{g['score']}/20</b>  |  {fmt_jalali_dt(g.get('exam_date',''), with_time=False)}")
        total += g['score']
    avg = round(total / len(grades), 2)
    lines.append(f"\n━━━━━━━━━━━━━━━━\n📈 میانگین کل: <b>{avg}/20</b>")
    return "\n".join(lines)


# ══════════════════════════════════════════════════
#  callback اصلی
# ══════════════════════════════════════════════════

async def grades_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(':')
    action = parts[1] if len(parts) > 1 else 'new'

    if action == 'new':
        await _start_new_grade(query, context)
    elif action == 'lesson_pick':
        await _pick_lesson(query, context, int(parts[2]))
    elif action == 'confirm':
        await _confirm_and_save(query, context)
    elif action == 'list':
        await _show_recent_grades(query, int(parts[2]))
    elif action == 'mine':
        text = await _build_my_grades_text(query.from_user.id)
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data='dashboard:refresh')]]
        try:
            await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            await query.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

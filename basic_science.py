"""
🔬 علوم پایه — دانشجو
  ✅ فیکس دکمه‌های بازگشت — هر لایه به لایه قبل
  ✅ context.user_data برای نگهداری مسیر
  ✅ نمایش سریع با asyncio
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from utils import TERMS, CONTENT_ICONS

logger = logging.getLogger(__name__)


async def basic_science_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    data   = query.data
    parts  = data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    if action == 'main':
        context.user_data['bs_from_admin'] = False
        await _show_terms(query, back_cb='resources:menu')

    elif action == 'main_admin':
        context.user_data['bs_from_admin'] = True
        await _show_terms(query, back_cb='admin:main')

    elif action == 'term':
        idx  = int(parts[2])
        term = TERMS[idx]
        context.user_data.update({'bs_term': term, 'bs_term_idx': idx})
        fa   = context.user_data.get('bs_from_admin', False)
        back = 'bs:main_admin' if fa else 'bs:main'
        await _show_lessons(query, term, idx, back_cb=back)

    elif action == 'lesson':
        lesson_id = parts[2]
        context.user_data['bs_lesson_id'] = lesson_id
        idx       = context.user_data.get('bs_term_idx', 0)
        await _show_sessions(query, lesson_id, back_cb=f'bs:term:{idx}')

    elif action == 'session':
        session_id = parts[2]
        context.user_data['bs_session_id'] = session_id
        lesson_id  = context.user_data.get('bs_lesson_id', '')
        await _show_content(query, session_id, back_cb=f'bs:lesson:{lesson_id}')

    # دانلود محتوا — با پیشوند bs_dl:
    elif data.startswith('bs_dl:'):
        content_id = parts[1]
        await _download_content(query, content_id, update.effective_user.id)


# ══════════════════════════════════════════════════
#  نمایش‌دهنده‌ها
# ══════════════════════════════════════════════════

async def _show_terms(query, back_cb: str = 'resources:menu'):
    keyboard = []
    for i in range(0, len(TERMS), 2):
        row = [InlineKeyboardButton(f"📘 {TERMS[i]}", callback_data=f'bs:term:{i}')]
        if i + 1 < len(TERMS):
            row.append(InlineKeyboardButton(f"📘 {TERMS[i+1]}", callback_data=f'bs:term:{i+1}'))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb)])
    await query.edit_message_text(
        "🔬 <b>علوم پایه پزشکی</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "ترم تحصیلی خود را انتخاب کنید:\n\n"
        "<i>⚠️ واحدهای هر ترم بر اساس چارت پیشنهادی است.</i>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_lessons(query, term: str, term_idx: int, back_cb: str):
    lessons  = await db.bs_get_lessons(term)
    keyboard = []
    for l in lessons:
        lid         = str(l['_id'])
        teacher_txt = f" | {l.get('teacher', '')}" if l.get('teacher') else ''
        keyboard.append([InlineKeyboardButton(
            f"📖 {l['name']}{teacher_txt}", callback_data=f'bs:lesson:{lid}'
        )])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb)])

    if not lessons:
        await query.edit_message_text(
            f"📘 <b>{term}</b>\n\n❌ هنوز درسی تعریف نشده.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    await query.edit_message_text(
        f"📘 <b>{term}</b>\n━━━━━━━━━━━━━━━━\nدرس مورد نظر را انتخاب کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_sessions(query, lesson_id: str, back_cb: str):
    lesson   = await db.bs_get_lesson(lesson_id)
    if not lesson:
        await query.answer("❌ درس پیدا نشد!", show_alert=True)
        return
    sessions = await db.bs_get_sessions(lesson_id)
    keyboard = []
    for s in sessions:
        sid = str(s['_id'])
        keyboard.append([InlineKeyboardButton(
            f"📌 جلسه {s['number']} — {s.get('topic', '')[:30]}",
            callback_data=f'bs:session:{sid}'
        )])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb)])

    if not sessions:
        await query.edit_message_text(
            f"📖 <b>{lesson['name']}</b>\n\n❌ هنوز جلسه‌ای ثبت نشده.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    await query.edit_message_text(
        f"📖 <b>{lesson['name']}</b>\n"
        f"👨‍🏫 {lesson.get('teacher', '') or '—'}\n"
        f"━━━━━━━━━━━━━━━━\nجلسه مورد نظر را انتخاب کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_content(query, session_id: str, back_cb: str):
    session  = await db.bs_get_session(session_id)
    if not session:
        await query.answer("❌ جلسه پیدا نشد!", show_alert=True)
        return
    contents = await db.bs_get_content(session_id)
    keyboard = []

    if contents:
        by_type: dict = {}
        for c in contents:
            by_type.setdefault(c.get('type', 'pdf'), []).append(c)

        for ctype, items in by_type.items():
            icon_label = CONTENT_ICONS.get(ctype, '📎 فایل')
            for item in items:
                cid   = str(item['_id'])
                desc  = item.get('description', '')[:20]
                label = icon_label + (f" — {desc}" if desc else '')
                keyboard.append([InlineKeyboardButton(
                    label, callback_data=f'bs_dl:{cid}'
                )])
        content_list = '\n'.join(
            f"  {CONTENT_ICONS.get(t, '📎')} {len(v)} فایل"
            for t, v in by_type.items()
        )
    else:
        content_list = "❌ محتوایی بارگذاری نشده"

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb)])
    await query.edit_message_text(
        f"📌 <b>جلسه {session['number']}</b>\n"
        f"📚 {session.get('topic', '')}\n"
        f"👨‍🏫 {session.get('teacher', '') or '—'}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{content_list}\n\n"
        "برای دانلود کلیک کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _download_content(query, content_id: str, uid: int):
    item = await db.bs_get_content_item(content_id)
    if not item:
        await query.answer("❌ فایل پیدا نشد!", show_alert=True)
        return
    await db.bs_inc_download(content_id, uid)

    ctype  = item.get('type', 'pdf')
    parts  = [CONTENT_ICONS.get(ctype, '📎')]
    if item.get('description'):
        parts.append(f"📝 {item['description']}")
    if item.get('extra_info'):
        parts.append(item['extra_info'])
    parts.append(f"📥 {item.get('downloads', 0)} دانلود")
    caption = '\n'.join(parts)

    # FIX جدید: دکمه گزارش ایراد جزوه زیر فایل ارسالی
    report_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚠️ گزارش ایراد جزوه", callback_data=f'report:resource:{content_id}')
    ]])
    try:
        if ctype == 'video':
            await query.message.reply_video(
                item['file_id'], caption=caption, parse_mode='HTML', reply_markup=report_kb
            )
        elif ctype == 'voice':
            await query.message.reply_voice(
                item['file_id'], caption=caption, parse_mode='HTML', reply_markup=report_kb
            )
        else:
            await query.message.reply_document(
                item['file_id'], caption=caption, parse_mode='HTML', reply_markup=report_kb
            )
    except Exception:
        try:
            await query.message.reply_document(
                item['file_id'], caption=caption, parse_mode='HTML', reply_markup=report_kb
            )
        except Exception:
            await query.answer("❌ خطا در ارسال فایل!", show_alert=True)

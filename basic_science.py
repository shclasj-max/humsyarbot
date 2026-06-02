"""علوم پایه — دانشجو"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db

logger = logging.getLogger(__name__)
TERMS = ['ترم ۱', 'ترم ۲', 'ترم ۳', 'ترم ۴', 'ترم ۵']
CONTENT_ICONS = {
    'video': '🎥 ویدیو کلاس', 'ppt': '📊 پاورپوینت',
    'pdf':   '📄 جزوه PDF',   'note': '📝 نکات',
    'test':  '🧪 تست',        'voice': '🎙 ویس استاد'
}

# دکمه بازگشت پیش‌فرض — به منوی منابع
BACK_TO_RESOURCES = 'resources:menu'


async def basic_science_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data
    parts = data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    # منبع فراخوانی (admin panel یا student panel)
    came_from_admin = context.user_data.get('bs_from_admin', False)

    if action == 'main':
        # تشخیص از کجا آمده
        context.user_data['bs_from_admin'] = False
        await _show_terms(query, back_cb='resources:menu')

    elif action == 'main_admin':
        context.user_data['bs_from_admin'] = True
        await _show_terms(query, back_cb='admin:main')

    elif action == 'term':
        idx  = int(parts[2])
        term = TERMS[idx]
        context.user_data['bs_term']     = term
        context.user_data['bs_term_idx'] = idx
        back = 'bs:main_admin' if came_from_admin else 'bs:main'
        await _show_lessons(query, context, term, back_terms=back)

    elif action == 'lesson':
        lesson_id = parts[2]
        context.user_data['bs_lesson_id'] = lesson_id
        idx  = context.user_data.get('bs_term_idx', 0)
        await _show_sessions(query, context, lesson_id, back_term=f'bs:term:{idx}')

    elif action == 'session':
        session_id = parts[2]
        context.user_data['bs_session_id'] = session_id
        lesson_id  = context.user_data.get('bs_lesson_id', '')
        await _show_content(query, context, session_id, back_lesson=f'bs:lesson:{lesson_id}')

    elif data.startswith('bs_dl:'):
        content_id = parts[1]
        await _download_content(query, content_id, update.effective_user.id)


async def _show_terms(query, back_cb='resources:menu'):
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
        "⚠️ <i>واحدهای هر ترم بر اساس چارت پیشنهادی دانشگاه است و ممکن است با انتخاب واحد شما متفاوت باشد.</i>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_lessons(query, context, term, back_terms='bs:main'):
    lessons = await db.bs_get_lessons(term)
    if not lessons:
        await query.edit_message_text(
            f"📘 <b>{term}</b>\n\n❌ هنوز درسی برای این ترم تعریف نشده.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=back_terms)]]))
        return
    keyboard = []
    for l in lessons:
        lid = str(l['_id'])
        teacher_txt = f" | {l.get('teacher','')}" if l.get('teacher') else ''
        keyboard.append([InlineKeyboardButton(f"📖 {l['name']}{teacher_txt}", callback_data=f'bs:lesson:{lid}')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back_terms)])
    await query.edit_message_text(
        f"📘 <b>{term}</b>\n━━━━━━━━━━━━━━━━\nدرس مورد نظر را انتخاب کنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_sessions(query, context, lesson_id, back_term='bs:main'):
    lesson = await db.bs_get_lesson(lesson_id)
    if not lesson:
        await query.answer("❌ درس پیدا نشد!", show_alert=True); return
    sessions = await db.bs_get_sessions(lesson_id)
    term = context.user_data.get('bs_term', '')
    if not sessions:
        await query.edit_message_text(
            f"📖 <b>{lesson['name']}</b>\n\n❌ هنوز جلسه‌ای ثبت نشده.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=back_term)]]))
        return
    keyboard = []
    for s in sessions:
        sid = str(s['_id'])
        keyboard.append([InlineKeyboardButton(
            f"📌 جلسه {s['number']} — {s.get('topic','')[:30]}",
            callback_data=f'bs:session:{sid}'
        )])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back_term)])
    await query.edit_message_text(
        f"📖 <b>{lesson['name']}</b>\n"
        f"👨‍🏫 {lesson.get('teacher','')} | {term}\n"
        f"━━━━━━━━━━━━━━━━\nجلسه مورد نظر را انتخاب کنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_content(query, context, session_id, back_lesson='bs:main'):
    session = await db.bs_get_session(session_id)
    if not session:
        await query.answer("❌ جلسه پیدا نشد!", show_alert=True); return
    contents = await db.bs_get_content(session_id)
    if not contents:
        await query.edit_message_text(
            f"📌 <b>جلسه {session['number']}</b> — {session.get('topic','')}\n\n❌ محتوایی بارگذاری نشده.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=back_lesson)]]))
        return
    by_type = {}
    for c in contents:
        by_type.setdefault(c.get('type', 'pdf'), []).append(c)
    keyboard = []
    for ctype, items in by_type.items():
        icon_label = CONTENT_ICONS.get(ctype, '📎 فایل')
        for item in items:
            cid   = str(item['_id'])
            desc  = item.get('description', '')[:20]
            label = f"{icon_label}" + (f" — {desc}" if desc else '')
            keyboard.append([InlineKeyboardButton(label, callback_data=f'bs_dl:{cid}')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back_lesson)])
    content_list = '\n'.join(f"  {CONTENT_ICONS.get(t,'📎')} {len(v)} فایل" for t, v in by_type.items())
    await query.edit_message_text(
        f"📌 <b>جلسه {session['number']}</b>\n"
        f"📚 {session.get('topic','')}\n"
        f"👨‍🏫 {session.get('teacher','')}\n"
        f"━━━━━━━━━━━━━━━━\n{content_list}\n\nبرای دانلود کلیک کنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _download_content(query, content_id, uid):
    item = await db.bs_get_content_item(content_id)
    if not item:
        await query.answer("❌ فایل پیدا نشد!", show_alert=True); return
    await db.bs_inc_download(content_id, uid)
    ctype   = item.get('type', 'pdf')
    # کپشن: نوع فایل + توضیح (اگه داشت) + توضیح اضافه (اگه داشت) + دانلود
    parts = [CONTENT_ICONS.get(ctype,'📎')]
    if item.get('description'):
        parts.append(f"📝 {item['description']}")
    if item.get('extra_info'):
        parts.append(f"\n{item['extra_info']}")
    parts.append(f"📥 {item.get('downloads',0)} دانلود")
    caption = '\n'.join(parts)
    try:
        if ctype == 'video':
            await query.message.reply_video(item['file_id'], caption=caption, parse_mode='HTML')
        elif ctype == 'voice':
            await query.message.reply_audio(item['file_id'], caption=caption, parse_mode='HTML')
        else:
            await query.message.reply_document(item['file_id'], caption=caption, parse_mode='HTML')
    except:
        try:
            await query.message.reply_document(item['file_id'], caption=caption, parse_mode='HTML')
        except:
            await query.answer("❌ خطا در ارسال فایل!", show_alert=True)

"""
بانک سوال — نسخه نهایی بهینه‌سازی‌شده
✅ فیکس دکمه‌های بازگشت در همه مسیرها
✅ آزمون سفارشی (تعداد + زمان دلخواه)
✅ خروجی فایل txt از سوالات
✅ طراحی سوال توسط دانشجو و ادمین محتوا
✅ نمایش طراح سوال
✅ فیلتر درس + مبحث
✅ آمار پیشرفته
✅ بهینه‌سازی سرعت — کش لیست درس‌ها و مباحث
"""
import os, io, asyncio, logging, time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from utils import send_audit_log, fmt_jalali_dt

logger     = logging.getLogger(__name__)
ADMIN_ID   = int(os.getenv('ADMIN_ID', '0'))
ANSWERING  = 4
CREATING_Q = 6

DIFF_EMOJI = {'آسان 🟢': '🟢', 'متوسط 🟡': '🟡', 'سخت 🔴': '🔴'}
LETTERS    = ['🅐', '🅑', '🅒', '🅓']


# ══════════════════════════════════════════════════════════
#  ابزارهای کمکی
# ══════════════════════════════════════════════════════════

def _back(label: str, cb: str) -> list:
    """ردیف دکمه بازگشت استاندارد"""
    return [InlineKeyboardButton(label, callback_data=cb)]


# ══════════════════════════════════════════════════════════
#  تابع ورودی از ReplyKeyboard (message_router)
# ══════════════════════════════════════════════════════════

async def _main_menu_msg(message):
    """نمایش منوی اصلی از طریق message (نه callback)"""
    keyboard = [
        [InlineKeyboardButton("📁 بانک فایل سوالات",     callback_data='questions:file_bank')],
        [InlineKeyboardButton("🧪 تمرین سریع",            callback_data='questions:practice')],
        [InlineKeyboardButton("📝 آزمون سفارشی",          callback_data='questions:custom_exam')],
        [InlineKeyboardButton("📄 خروجی فایل سوالات",    callback_data='questions:pdf_menu')],
        [InlineKeyboardButton("✏️ طراحی سوال",            callback_data='questions:create')],
        [InlineKeyboardButton("📊 آمار و پیشرفت من",      callback_data='questions:stats')],
    ]
    await message.reply_text(
        "🧪 <b>بانک سوال</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📁 <b>بانک فایل:</b> دانلود PDF سوالات\n"
        "🧪 <b>تمرین سریع:</b> سوال چهارگزینه‌ای\n"
        "📝 <b>آزمون سفارشی:</b> تعداد و زمان دلخواه\n"
        "📄 <b>خروجی فایل:</b> سوالات را دانلود کنید\n"
        "✏️ <b>طراحی سوال:</b> سوال خودتان بسازید\n"
        "📊 <b>آمار:</b> پیشرفت و نقاط ضعف",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════════════════
#  Callback اصلی
# ══════════════════════════════════════════════════════════

async def questions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    data   = query.data
    parts  = data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'
    uid    = update.effective_user.id

    # FIX جدید: دفاع لایه‌دوم اشتراک — اکشن‌های ca_* (بررسی سوال توسط
    # ادمین محتوا) از این گیت مستثنی‌اند، چون کار مدیریتی است نه مصرف محتوا
    if not action.startswith('ca_'):
        from subscription import has_access
        if not await has_access(uid):
            await query.answer("🔒 اول باید اشتراک فعال کنی — از «🧪 بانک سوال» شروع کن.", show_alert=True)
            return
    await query.answer()

    # ── منوی اصلی ──
    if action == 'main':
        await _main_menu(query)

    # ── بانک فایل ──
    elif action == 'file_bank':
        await _fb_term_select(query, context)

    elif action == 'fb_term':
        term_idx = int(parts[2])
        await _fb_lessons(query, context, term_idx)

    elif action == 'fb_lesson':
        idx     = int(parts[2])
        lessons = context.user_data.get('_fb_lessons', [])
        if idx < len(lessons):
            context.user_data['fb_lesson'] = lessons[idx]
            await _fb_topics(query, context, lessons[idx])

    elif action == 'fb_topic':
        lesson = context.user_data.get('fb_lesson', '')
        topics = context.user_data.get('_fb_topics', [])
        topic  = None if parts[2] == 'all' else (topics[int(parts[2])] if int(parts[2]) < len(topics) else None)
        context.user_data['fb_topic'] = topic
        await _fb_files(query, context, lesson, topic)

    elif data.startswith('download_qbank:'):
        fid  = parts[1]
        item = await db.get_qbank_file(fid)
        if not item:
            await query.answer("فایل پیدا نشد!", show_alert=True); return
        await db.inc_qbank_download(fid, uid)
        caption = (f"📁 <b>بانک سوال</b>\n📚 {item.get('lesson','')} — {item.get('topic','')}\n"
                   f"📝 {item.get('description','')}\n⬇️ {item.get('downloads',0)} دانلود")
        protect = await db.get_setting('protect_content_enabled', True)
        try:
            await query.message.reply_document(item['file_id'], caption=caption, parse_mode='HTML', protect_content=protect)
        except:
            try:    await query.message.reply_photo(item['file_id'], caption=caption, parse_mode='HTML', protect_content=protect)
            except: await query.answer("خطا در ارسال فایل!", show_alert=True)
        return

    # ── آزمون سفارشی ──
    elif action == 'custom_exam':
        await _custom_exam_menu(query, context)

    elif action == 'cx_lesson':
        idx     = int(parts[2])
        lessons = context.user_data.get('_cx_lessons', [])
        if idx < len(lessons):
            context.user_data.setdefault('cx', {})['lesson'] = lessons[idx]
            context.user_data['cx_lesson_idx'] = idx
            await _cx_topic_select(query, context, lessons[idx])

    elif action == 'cx_topic':
        topics = context.user_data.get('_cx_topics', [])
        topic  = 'همه' if parts[2] == 'all' else (topics[int(parts[2])] if int(parts[2]) < len(topics) else 'همه')
        context.user_data.setdefault('cx', {})['topic'] = topic
        await _cx_count_select(query, context)

    elif action == 'cx_count':
        count = int(parts[2])
        context.user_data.setdefault('cx', {})['count'] = count
        await _cx_time_select(query, context)

    elif action == 'cx_back_count':
        await _cx_count_select(query, context)

    elif action == 'cx_time':
        minutes = int(parts[2])
        context.user_data.setdefault('cx', {})['time'] = minutes
        await _cx_start(query, context, uid)

    # ── تمرین آزاد ──
    elif action == 'practice':
        await _practice_menu(query)

    elif action == 'free':
        await _term_select(query, context, 'free')

    elif action == 'weak':
        context.user_data['quiz'] = {'mode': 'weak', 'answered': [], 'correct': 0, 'total': 999}
        await _next_q(query, context, uid)

    elif action == 'hard':
        context.user_data['quiz'] = {'mode': 'hard', 'difficulty': 'سخت 🔴', 'answered': [], 'correct': 0, 'total': 999}
        await _next_q(query, context, uid)

    elif action == 'exam':
        await _term_select(query, context, 'exam')

    elif action == 'sel_term':
        mode = parts[2]; term_idx = int(parts[3])
        await _lesson_select(query, context, mode, term_idx)

    elif action == 'sel_term_back':
        mode = parts[2]
        await _term_select(query, context, mode)

    elif action == 'sel_lesson':
        mode    = parts[2]; idx = int(parts[3])
        lessons = context.user_data.get('_lessons', [])
        if idx < len(lessons):
            lesson = lessons[idx]
            context.user_data['sel_lesson']     = lesson
            context.user_data['sel_lesson_idx'] = idx
            context.user_data['quiz'] = {
                'mode': mode, 'lesson': lesson,
                'answered': [], 'correct': 0,
                'total': 20 if mode == 'exam' else 999
            }
            await _topic_select(query, context, lesson, mode)

    elif action == 'sel_topic':
        mode   = parts[2]
        topics = context.user_data.get('_topics', [])
        topic  = 'همه' if parts[3] == 'all' else (topics[int(parts[3])] if int(parts[3]) < len(topics) else 'همه')
        lesson = context.user_data.get('sel_lesson', '')
        context.user_data.setdefault('quiz', {}).update({
            'lesson': lesson, 'topic': topic, 'mode': mode,
            'answered': [], 'correct': 0,
            'total': 20 if mode == 'exam' else 999
        })
        await _next_q(query, context, uid)

    elif action == 'next':
        await _next_q(query, context, uid)

    elif action == 'stats':
        await _quiz_stats(query, uid)

    # ── طراحی سوال ──
    elif action in ('create', 'create_ca'):
        is_ca = (action == 'create_ca') or await db.is_content_admin(uid)
        context.user_data['creating_as_ca'] = is_ca
        await _create_start(query, context)

    elif action == 'cr_lesson':
        idx     = int(parts[2])
        lessons = context.user_data.get('_lessons', [])
        if idx < len(lessons):
            lesson = lessons[idx]
            context.user_data['new_q']     = {'lesson': lesson}
            context.user_data['cr_lesson'] = lesson
            await _create_topic_select(query, context, lesson)

    elif action == 'cr_topic':
        topics = context.user_data.get('_topics', [])
        idx    = int(parts[2])
        topic  = topics[idx] if idx < len(topics) else ''
        context.user_data.setdefault('new_q', {})['topic'] = topic
        context.user_data['mode']        = 'creating_question'
        context.user_data['create_step'] = 'question'
        await query.edit_message_text(
            f"✏️ <b>طراحی سوال</b>\n"
            f"📚 {context.user_data.get('cr_lesson','')} — {topic}\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📝 <b>گام ۱ از ۵ — متن سوال</b>\n\nسوال خود را بنویسید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='questions:main')
            ]]))
        return CREATING_Q

    # ── خروجی فایل سوالات ──
    elif action == 'pdf_menu':
        await _pdf_menu(query, context)

    elif action == 'pdf_lesson':
        idx     = int(parts[2])
        lessons = context.user_data.get('_pdf_lessons', [])
        if idx < len(lessons):
            context.user_data['pdf_lesson'] = lessons[idx]
            await _pdf_chapter_select(query, context, lessons[idx])

    elif action == 'pdf_chapter':
        chapters = context.user_data.get('_pdf_chapters', [])
        chapter  = None if parts[2] == 'all' else (chapters[int(parts[2])] if int(parts[2]) < len(chapters) else None)
        context.user_data['pdf_chapter'] = chapter
        lesson = context.user_data.get('pdf_lesson', '')
        await _pdf_topic_select(query, context, lesson, chapter)

    elif action == 'pdf_topic':
        topics = context.user_data.get('_pdf_topics', [])
        topic  = 'همه' if parts[2] == 'all' else (topics[int(parts[2])] if int(parts[2]) < len(topics) else 'همه')
        lesson  = context.user_data.get('pdf_lesson', '')
        chapter = context.user_data.get('pdf_chapter')
        context.user_data['pdf_topic'] = topic
        await _pdf_difficulty_select(query, context, lesson, chapter, topic)

    elif action == 'pdf_diff':
        diffs = context.user_data.get('_pdf_diffs', [])
        difficulty = None if parts[2] == 'all' else (diffs[int(parts[2])] if int(parts[2]) < len(diffs) else None)
        context.user_data['pdf_difficulty'] = difficulty
        lesson = context.user_data.get('pdf_lesson', '')
        topic  = context.user_data.get('pdf_topic', 'همه')
        await _pdf_count_select(query, context, lesson, topic)

    elif action == 'pdf_count':
        count = int(parts[2])
        context.user_data['pdf_count'] = count
        await _pdf_mode_select(query, context)

    elif action == 'pdf_mode':
        await query.edit_message_text("⏳ در حال ساخت فایل...", parse_mode='HTML')
        await _generate_pdf_v2(query, context, uid, mode=parts[2])

    elif action == 'pdf_topic_sel':
        topics = context.user_data.get('_pdf_topics', [])
        topic  = 'همه' if parts[2] == 'all' else (topics[int(parts[2])] if int(parts[2]) < len(topics) else 'همه')
        context.user_data['pdf_topic'] = topic
        lesson  = context.user_data.get('pdf_lesson','')
        chapter = context.user_data.get('pdf_chapter')
        await _pdf_difficulty_select(query, context, lesson, chapter, topic)

    # ── دکمه‌های بازگشت یک‌قدمی در ویزارد PDF (بدون گم‌کردن انتخاب‌های قبلی) ──
    elif action == 'pdf_back_chapter':
        lesson = context.user_data.get('pdf_lesson', '')
        await _pdf_chapter_select(query, context, lesson)

    elif action == 'pdf_back_topic':
        lesson  = context.user_data.get('pdf_lesson', '')
        chapter = context.user_data.get('pdf_chapter')
        await _pdf_topic_select(query, context, lesson, chapter)

    elif action == 'pdf_back_diff':
        lesson  = context.user_data.get('pdf_lesson', '')
        chapter = context.user_data.get('pdf_chapter')
        topic   = context.user_data.get('pdf_topic', 'همه')
        await _pdf_difficulty_select(query, context, lesson, chapter, topic)

    elif action == 'pdf_back_count':
        lesson = context.user_data.get('pdf_lesson', '')
        topic  = context.user_data.get('pdf_topic', 'همه')
        await _pdf_count_select(query, context, lesson, topic)

    # ── مدیریت سوالات توسط ادمین محتوا/ادمین ──
    elif action == 'ca_q_list':
        await _ca_question_list(query, uid, context)

    elif action == 'ca_q_view':
        qid = parts[2] if len(parts) > 2 else ''
        await _ca_question_view(query, uid, qid)

    elif action == 'ca_q_del':
        qid = parts[2] if len(parts) > 2 else ''
        if await db.is_content_admin(uid):
            # FIX طبق سند: حذف سوال در پنل محتوا قبلاً اصلاً لاگ نمی‌شد
            q_doc = await db.get_question_by_id(qid)
            await db.delete_question(qid)
            await query.answer("🗑 سوال حذف شد!", show_alert=True)
            actor = await db.get_user(uid)
            actor_name = actor.get('name', 'ادمین محتوا') if actor else 'ادمین محتوا'
            actor_role = await db.get_actor_role_label(uid)
            await send_audit_log(
                context.bot, 'content', actor_name, uid,
                "حذف سوال", module='Questions', severity='HIGH',
                actor_role=actor_role,
                target_id=qid, target_type='question',
                target_label=(q_doc.get('question', '')[:60] if q_doc else ''),
                tags=['حذف_سوال']
            )
            await _ca_question_list(query, uid, context)

    elif action == 'ca_q_approve':
        qid = parts[2] if len(parts) > 2 else ''
        if await db.is_content_admin(uid):
            q_doc_approve = await db.get_question_by_id(qid)
            await db.approve_question(qid)
            await query.answer("✅ تأیید شد!", show_alert=True)
            actor = await db.get_user(uid)
            actor_name = actor.get('name', 'ادمین محتوا') if actor else 'ادمین محتوا'
            actor_role = await db.get_actor_role_label(uid)
            await send_audit_log(
                context.bot, 'content', actor_name, uid,
                "تأیید سوال", module='Questions', severity='INFO',
                actor_role=actor_role, target_id=qid, target_type='question',
                target_label=(q_doc_approve.get('question', '')[:60] if q_doc_approve else ''),
                tags=['تایید_سوال']
            )
            await _ca_question_list(query, uid, context)

    elif action == 'ca_q_filter':
        # فیلتر: ca_q_filter:type:value
        ftype = parts[2] if len(parts) > 2 else 'all'
        fval  = parts[3] if len(parts) > 3 else ''
        context.user_data[f'caq_filter_{ftype}'] = fval
        await _ca_question_list(query, uid, context)

    elif data.startswith('answer:'):
        await handle_question_answer(update, context)


# ══════════════════════════════════════════════════════════
#  منوها
# ══════════════════════════════════════════════════════════

async def _main_menu(query):
    keyboard = [
        [InlineKeyboardButton("📁 بانک فایل سوالات",     callback_data='questions:file_bank')],
        [InlineKeyboardButton("🧪 تمرین سریع",            callback_data='questions:practice')],
        [InlineKeyboardButton("📝 آزمون سفارشی",          callback_data='questions:custom_exam')],
        [InlineKeyboardButton("📄 خروجی فایل سوالات",    callback_data='questions:pdf_menu')],
        [InlineKeyboardButton("✏️ طراحی سوال",            callback_data='questions:create')],
        [InlineKeyboardButton("📊 آمار و پیشرفت من",      callback_data='questions:stats')],
        _back("🔙 داشبورد", "dashboard:refresh"),
    ]
    await query.edit_message_text(
        "🧪 <b>بانک سوال</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📁 <b>بانک فایل:</b> دانلود PDF سوالات\n"
        "🧪 <b>تمرین سریع:</b> سوال چهارگزینه‌ای\n"
        "📝 <b>آزمون سفارشی:</b> تعداد و زمان دلخواه\n"
        "📄 <b>خروجی فایل:</b> سوالات را دانلود کنید\n"
        "✏️ <b>طراحی سوال:</b> سوال خودتان بسازید\n"
        "📊 <b>آمار:</b> پیشرفت و نقاط ضعف",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _practice_menu(query):
    keyboard = [
        [InlineKeyboardButton("📖 تمرین آزاد",                callback_data='questions:free')],
        [InlineKeyboardButton("⚡ نقاط ضعف من",               callback_data='questions:weak')],
        [InlineKeyboardButton("📝 شبیه‌سازی امتحان (۲۰ سوال)", callback_data='questions:exam')],
        [InlineKeyboardButton("🔴 سوالات سطح سخت",            callback_data='questions:hard')],
        _back("🔙 بازگشت", "questions:main"),
    ]
    await query.edit_message_text(
        "🧪 <b>تمرین سریع</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📖 <b>آزاد:</b> هر درس و مبحث دلخواه\n"
        "⚡ <b>نقاط ضعف:</b> سوالاتی که اشتباه زدید\n"
        "📝 <b>شبیه امتحان:</b> ۲۰ سوال پشت سر هم\n"
        "🔴 <b>سخت:</b> چالشی‌ترین سوالات",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════════════════
#  آزمون سفارشی
# ══════════════════════════════════════════════════════════

async def _custom_exam_menu(query, context):
    lessons = await db.get_lessons()
    if not lessons:
        await query.edit_message_text(
            "❌ هنوز سوالی در بانک موجود نیست.",
            reply_markup=InlineKeyboardMarkup([
                _back("🔙 بازگشت", "questions:main")
            ])); return
    context.user_data['_cx_lessons'] = lessons
    context.user_data['cx'] = {}
    keyboard = []
    for i in range(0, len(lessons), 2):
        row = [InlineKeyboardButton(f"📚 {lessons[i]}", callback_data=f'questions:cx_lesson:{i}')]
        if i+1 < len(lessons):
            row.append(InlineKeyboardButton(f"📚 {lessons[i+1]}", callback_data=f'questions:cx_lesson:{i+1}'))
        keyboard.append(row)
    keyboard.append(_back("🔙 بازگشت", "questions:main"))
    await query.edit_message_text(
        "📝 <b>آزمون سفارشی</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "<b>گام ۱ از ۴:</b> درس را انتخاب کنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _cx_topic_select(query, context, lesson):
    topics = await db.get_topics(lesson)
    context.user_data['_cx_topics'] = topics
    keyboard = [[InlineKeyboardButton(f"📌 {t}", callback_data=f'questions:cx_topic:{i}')]
                for i, t in enumerate(topics)]
    keyboard.append([InlineKeyboardButton("📂 همه مباحث", callback_data='questions:cx_topic:all')])
    keyboard.append(_back("🔙 بازگشت", "questions:custom_exam"))
    await query.edit_message_text(
        f"📝 <b>آزمون سفارشی</b>\n📚 {lesson}\n\n"
        "<b>گام ۲ از ۴:</b> مبحث را انتخاب کنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _cx_count_select(query, context):
    cx     = context.user_data.get('cx', {})
    lesson = cx.get('lesson', '')
    topic  = cx.get('topic', 'همه')
    t_label = f" — {topic}" if topic != 'همه' else ''
    lesson_idx = context.user_data.get('cx_lesson_idx', 0)
    keyboard = [
        [InlineKeyboardButton("5 سوال",  callback_data='questions:cx_count:5'),
         InlineKeyboardButton("10 سوال", callback_data='questions:cx_count:10')],
        [InlineKeyboardButton("15 سوال", callback_data='questions:cx_count:15'),
         InlineKeyboardButton("20 سوال", callback_data='questions:cx_count:20')],
        [InlineKeyboardButton("30 سوال", callback_data='questions:cx_count:30'),
         InlineKeyboardButton("40 سوال", callback_data='questions:cx_count:40')],
        _back("🔙 بازگشت", f'questions:cx_lesson:{lesson_idx}'),
    ]
    await query.edit_message_text(
        f"📝 <b>آزمون سفارشی</b>\n📚 {lesson}{t_label}\n\n"
        "<b>گام ۳ از ۴:</b> تعداد سوالات:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _cx_time_select(query, context):
    cx    = context.user_data.get('cx', {})
    count = cx.get('count', 10)
    lesson = cx.get('lesson', '')
    topic  = cx.get('topic', 'همه')
    t_label = f" — {topic}" if topic != 'همه' else ''
    keyboard = [
        [InlineKeyboardButton("بدون محدودیت ⏳", callback_data='questions:cx_time:0')],
        [InlineKeyboardButton("۱۰ دقیقه ⏱",  callback_data='questions:cx_time:10'),
         InlineKeyboardButton("۲۰ دقیقه ⏱",  callback_data='questions:cx_time:20')],
        [InlineKeyboardButton("۳۰ دقیقه ⏱",  callback_data='questions:cx_time:30'),
         InlineKeyboardButton("۴۵ دقیقه ⏱",  callback_data='questions:cx_time:45')],
        [InlineKeyboardButton("۶۰ دقیقه ⏱",  callback_data='questions:cx_time:60'),
         InlineKeyboardButton("۹۰ دقیقه ⏱",  callback_data='questions:cx_time:90')],
        _back("🔙 بازگشت", "questions:cx_back_count"),
    ]
    await query.edit_message_text(
        f"📝 <b>آزمون سفارشی</b>\n📚 {lesson}{t_label}\n🔢 {count} سوال\n\n"
        "<b>گام ۴ از ۴:</b> زمان آزمون:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _cx_start(query, context, uid):
    cx      = context.user_data.get('cx', {})
    lesson  = cx.get('lesson', '')
    topic   = cx.get('topic', 'همه')
    count   = cx.get('count', 10)
    minutes = cx.get('time', 0)

    context.user_data['quiz'] = {
        'mode':     'custom',
        'lesson':   lesson,
        'topic':    topic if topic != 'همه' else None,
        'answered': [],
        'correct':  0,
        'total':    count,
        'start_ts': time.time(),
        'duration': minutes * 60 if minutes else 0,
    }
    await _next_q(query, context, uid)


# ══════════════════════════════════════════════════════════
#  سوال بعدی و جواب
# ══════════════════════════════════════════════════════════

async def _next_q(query, context, uid):
    quiz    = context.user_data.get('quiz', {})
    mode    = quiz.get('mode', 'free')
    lesson  = quiz.get('lesson')
    topic   = quiz.get('topic')
    diff    = quiz.get('difficulty')
    done    = quiz.get('answered', [])
    total   = quiz.get('total', 999)
    start   = quiz.get('start_ts', 0)
    dur     = quiz.get('duration', 0)

    # تعیین دکمه بازگشت بر اساس mode
    back_cb = 'questions:custom_exam' if mode == 'custom' else 'questions:practice'

    # بررسی زمان
    if dur and start and (time.time() - start) > dur:
        correct = quiz.get('correct', 0)
        pct     = round(correct / len(done) * 100) if done else 0
        elapsed = int(time.time() - start) // 60
        await query.edit_message_text(
            f"⏰ <b>زمان آزمون تمام شد!</b>\n\n"
            f"✅ صحیح: <b>{correct}</b> از <b>{len(done)}</b>\n"
            f"📊 درصد: <b>{pct}%</b>\n"
            f"⏱ زمان: {elapsed} دقیقه\n\n"
            f"{'🏆 عالی!' if pct>=80 else '👍 خوب!' if pct>=60 else '📖 بیشتر مطالعه کنید'}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 دوباره", callback_data=back_cb),
                 InlineKeyboardButton("📊 آمار",   callback_data='questions:stats'),
                 InlineKeyboardButton("🏠 منو",    callback_data='questions:main')]
            ]))
        return

    if len(done) >= total:
        correct = quiz.get('correct', 0)
        pct     = round(correct / len(done) * 100) if done else 0
        elapsed = int(time.time() - start) // 60 if start else 0
        time_txt = f"\n⏱ زمان: {elapsed} دقیقه" if start else ""
        await query.edit_message_text(
            f"🏁 <b>پایان آزمون</b>\n\n"
            f"✅ صحیح: <b>{correct}</b> از <b>{len(done)}</b>\n"
            f"📊 درصد: <b>{pct}%</b>{time_txt}\n\n"
            f"{'🏆 عالی!' if pct>=80 else '👍 خوب!' if pct>=60 else '📖 بیشتر مطالعه کنید'}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 دوباره",    callback_data=back_cb),
                 InlineKeyboardButton("📊 آمار کلی",  callback_data='questions:stats'),
                 InlineKeyboardButton("🏠 منو",       callback_data='questions:main')]
            ]))
        return

    if mode == 'weak':
        qs = await db.get_weak_questions(uid, limit=1)
    else:
        qs = await db.get_questions(lesson=lesson, topic=topic, difficulty=diff, limit=1, exclude=done)

    if not qs:
        await query.edit_message_text(
            "❌ سوال دیگری یافت نشد!\nتمام سوالات موجود را پاسخ دادید.",
            reply_markup=InlineKeyboardMarkup([
                _back("🔙 بازگشت", back_cb)
            ]))
        return

    q   = qs[0]
    qid = str(q['_id'])
    context.user_data.setdefault('quiz', {}).setdefault('answered', []).append(qid)

    diff_icon = DIFF_EMOJI.get(q.get('difficulty', ''), '⚪')
    num       = len(done) + 1
    total_str = f"/{total}" if total < 999 else ""

    # اطلاعات طراح
    creator_id  = q.get('creator_id')
    by_bot      = q.get('by_bot', False)
    if by_bot:
        creator_line = "\n<i>🤖 طراحی شده توسط بات</i>"
    elif creator_id:
        user = await db.get_user(creator_id)
        cname = user.get('name', '') if user else ''
        creator_line = f"\n<i>✏️ طراح: {cname}</i>" if cname else ""
    else:
        creator_line = ""

    # نمایش زمان باقیمانده
    time_line = ""
    if dur and start:
        remain = max(0, int(dur - (time.time() - start)))
        m, s   = divmod(remain, 60)
        time_line = f"\n⏱ <b>{m:02d}:{s:02d}</b> باقیمانده"

    keyboard = []
    for i, opt in enumerate(q['options']):
        keyboard.append([InlineKeyboardButton(
            f"{LETTERS[i]} {opt}", callback_data=f'answer:{qid}:{i}')])
    keyboard.append([
        InlineKeyboardButton("⚠️ گزارش ایراد سوال", callback_data=f'report:question:{qid}'),
    ])
    keyboard.append([
        InlineKeyboardButton("🏠 منو", callback_data='questions:main'),
    ])

    await query.edit_message_text(
        f"📝 <b>سوال {num}{total_str}</b>  {diff_icon}{time_line}\n"
        f"📚 {q.get('lesson','')} — {q.get('topic','')}\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"{q['question']}"
        f"{creator_line}",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_question_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid   = update.effective_user.id
    parts = query.data.split(':')
    qid   = parts[1]
    sel   = int(parts[2])

    q_doc = await db.get_question_by_id(qid)
    if not q_doc:
        await query.edit_message_text("❌ سوال پیدا نشد!"); return

    correct_idx = q_doc.get('correct_answer', 0)
    is_correct  = (sel == correct_idx)
    await db.save_answer(uid, qid, sel, is_correct)

    quiz = context.user_data.setdefault('quiz', {})
    if is_correct:
        quiz['correct'] = quiz.get('correct', 0) + 1

    opts    = q_doc.get('options', [])
    expl    = q_doc.get('explanation', '')
    icon    = "✅" if is_correct else "❌"

    options_text = ""
    for i, opt in enumerate(opts):
        if i == correct_idx:                   marker = "✅"
        elif i == sel and not is_correct:      marker = "❌"
        else:                                  marker = "⚫"
        options_text += f"{marker} {opt}\n"

    text = (f"{icon} <b>{'صحیح!' if is_correct else 'اشتباه!'}</b>\n\n"
            f"{q_doc['question']}\n\n{options_text}")
    if expl:
        text += f"\n💡 <b>توضیح:</b> {expl}"

    # تعیین دکمه بازگشت صحیح
    mode    = quiz.get('mode', 'free')
    back_cb = 'questions:custom_exam' if mode == 'custom' else 'questions:practice'

    keyboard = [[
        InlineKeyboardButton("➡️ سوال بعدی", callback_data='questions:next'),
        InlineKeyboardButton("🏠 منو",        callback_data='questions:main')
    ]]
    await query.edit_message_text(text, parse_mode='HTML',
                                  reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════════════════
#  بانک فایل
# ══════════════════════════════════════════════════════════

async def _fb_term_select(query, context):
    """FIX جدید: لایه انتخاب ترم برای بانک فایل — مثل منابع علوم پایه"""
    from utils import TERMS
    keyboard = []
    for i in range(0, len(TERMS), 2):
        row = [InlineKeyboardButton(f"📘 {TERMS[i]}", callback_data=f'questions:fb_term:{i}')]
        if i+1 < len(TERMS):
            row.append(InlineKeyboardButton(f"📘 {TERMS[i+1]}", callback_data=f'questions:fb_term:{i+1}'))
        keyboard.append(row)
    keyboard.append(_back("🔙 بازگشت", "questions:main"))
    await query.edit_message_text("📁 <b>بانک فایل سوالات</b>\n\nترم را انتخاب کنید:",
                                  parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _fb_lessons(query, context, term_idx: int = None):
    from utils import TERMS
    term = TERMS[term_idx] if term_idx is not None and term_idx < len(TERMS) else None
    context.user_data['fb_term_idx'] = term_idx
    lessons = await db.get_lessons(term=term)
    back_cb = 'questions:file_bank' if term_idx is not None else 'questions:main'
    if not lessons:
        await query.edit_message_text(
            f"📁 <b>بانک فایل</b>\n\n❌ هنوز فایلی برای {term or 'این بخش'} آپلود نشده.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                _back("🔙 بازگشت", back_cb)
            ])); return
    context.user_data['_fb_lessons'] = lessons
    keyboard = []
    for i in range(0, len(lessons), 2):
        row = [InlineKeyboardButton(f"📚 {lessons[i]}", callback_data=f'questions:fb_lesson:{i}')]
        if i+1 < len(lessons):
            row.append(InlineKeyboardButton(f"📚 {lessons[i+1]}", callback_data=f'questions:fb_lesson:{i+1}'))
        keyboard.append(row)
    keyboard.append(_back("🔙 بازگشت", back_cb))
    term_label = f" — {term}" if term else ""
    await query.edit_message_text(f"📁 <b>بانک فایل سوالات{term_label}</b>\n\nدرس را انتخاب کنید:",
                                  parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _fb_topics(query, context, lesson):
    topics = await db.get_topics(lesson)
    context.user_data['_fb_topics'] = topics
    # FIX جدید: بازگشت به لیست درس‌های همان ترم، نه به لیست ترم‌ها
    term_idx = context.user_data.get('fb_term_idx')
    back_cb  = f'questions:fb_term:{term_idx}' if term_idx is not None else 'questions:file_bank'
    keyboard = [[InlineKeyboardButton(f"📌 {t}", callback_data=f'questions:fb_topic:{i}')]
                for i, t in enumerate(topics)]
    keyboard.append([InlineKeyboardButton("📂 همه مباحث", callback_data='questions:fb_topic:all')])
    keyboard.append(_back("🔙 بازگشت", back_cb))
    await query.edit_message_text(f"📁 <b>{lesson}</b>\n\nمبحث را انتخاب کنید:",
                                  parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _fb_files(query, context, lesson, topic):
    files = await db.get_qbank_files(lesson=lesson, topic=topic)
    # بازگشت صحیح: به لیست مباحث همان درس
    back_cb = f'questions:fb_lesson:{context.user_data.get("_fb_lessons", []).index(lesson)}' \
        if lesson in context.user_data.get('_fb_lessons', []) else 'questions:file_bank'

    if not files:
        await query.edit_message_text(
            f"📁 <b>{lesson}{' — '+topic if topic else ''}</b>\n\n❌ فایلی آپلود نشده.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                _back("🔙 بازگشت", back_cb)
            ])); return
    keyboard = []
    for f in files:
        fid   = str(f['_id'])
        label = f"📥 {f.get('topic','')} | {f.get('description','')[:25]} | ⬇️{f.get('downloads',0)}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f'download_qbank:{fid}')])
    keyboard.append(_back("🔙 بازگشت", back_cb))
    await query.edit_message_text(
        f"📁 <b>{lesson}{' — '+topic if topic else ''}</b>\n{len(files)} فایل:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════════════════
#  خروجی فایل سوالات
# ══════════════════════════════════════════════════════════

async def _pdf_menu(query, context):
    lessons = await db.get_qbank_lessons()
    if not lessons:
        await query.edit_message_text(
            "❌ هنوز سوالی موجود نیست.",
            reply_markup=InlineKeyboardMarkup([
                _back("🔙 بازگشت", "questions:main")
            ])); return
    context.user_data['_pdf_lessons'] = lessons
    keyboard = []
    for i in range(0, len(lessons), 2):
        row = [InlineKeyboardButton(f"📚 {lessons[i]}", callback_data=f'questions:pdf_lesson:{i}')]
        if i+1 < len(lessons):
            row.append(InlineKeyboardButton(f"📚 {lessons[i+1]}", callback_data=f'questions:pdf_lesson:{i+1}'))
        keyboard.append(row)
    keyboard.append(_back("🔙 بازگشت", "questions:main"))
    await query.edit_message_text(
        "📄 <b>بانک سوالات — ساخت آزمون PDF</b>\n\n"
        "درس مورد نظر را انتخاب کنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _pdf_chapter_select(query, context, lesson):
    """
    🆕 مرحله‌ی جدید (اختیاری): انتخاب فصل.
    اگه سوالات این درس فصل‌بندی نشده باشن (چون این یک فیلد جدید و
    اختیاریه)، این مرحله کاملاً و بی‌صدا رد می‌شه — رفتار قبلی حفظ
    می‌شه، بدون این‌که کاربر یک مرحله‌ی خالی ببینه.
    """
    chapters = await db.get_qbank_chapters(lesson)
    if not chapters:
        context.user_data['pdf_chapter'] = None
        await _pdf_topic_select(query, context, lesson, None)
        return
    context.user_data['_pdf_chapters'] = chapters
    keyboard = [[InlineKeyboardButton(f"📖 {c}", callback_data=f'questions:pdf_chapter:{i}')]
                for i, c in enumerate(chapters)]
    keyboard.append([InlineKeyboardButton("📂 همه فصل‌ها", callback_data='questions:pdf_chapter:all')])
    keyboard.append(_back("🔙 بازگشت", "questions:pdf_menu"))
    await query.edit_message_text(f"📄 <b>{lesson}</b>\n\nفصل را انتخاب کنید:",
                                  parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _pdf_topic_select(query, context, lesson, chapter=None):
    topics = await db.get_qbank_topics(lesson, chapter)
    context.user_data['_pdf_topics'] = topics
    keyboard = [[InlineKeyboardButton(f"📌 {t}", callback_data=f'questions:pdf_topic_sel:{i}')]
                for i, t in enumerate(topics)]
    keyboard.append([InlineKeyboardButton("📂 همه مباحث", callback_data='questions:pdf_topic_sel:all')])
    back_cb = 'questions:pdf_back_chapter' if context.user_data.get('_pdf_chapters') else 'questions:pdf_menu'
    keyboard.append(_back("🔙 بازگشت", back_cb))
    c_label = f" — {chapter}" if chapter else ''
    await query.edit_message_text(f"📄 <b>{lesson}{c_label}</b>\n\nمبحث را انتخاب کنید:",
                                  parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _pdf_difficulty_select(query, context, lesson, chapter, topic):
    """
    🆕 مرحله‌ی جدید (اختیاری): انتخاب سطح سختی.
    اگه فقط یک سطح سختی (یا هیچ‌کدام) برای این فیلتر موجود باشه، این
    مرحله خودکار رد می‌شه — کاربر مجبور به انتخاب چیزی که فرقی نداره
    نمی‌شه.
    """
    from qbank.styles import normalize_difficulty
    raw_diffs = await db.get_qbank_difficulties(lesson, chapter, topic)
    seen, diffs = set(), []
    for d in raw_diffs:
        key = normalize_difficulty(d)
        if key not in seen:
            seen.add(key)
            diffs.append(d)
    if len(diffs) <= 1:
        context.user_data['pdf_difficulty'] = None
        await _pdf_count_select(query, context, lesson, topic)
        return
    context.user_data['_pdf_diffs'] = diffs
    icon = {'آسان': '🟢', 'متوسط': '🟡', 'سخت': '🔴'}
    keyboard = [[InlineKeyboardButton(f"{icon.get(normalize_difficulty(d),'')} {normalize_difficulty(d)}",
                                       callback_data=f'questions:pdf_diff:{i}')]
                for i, d in enumerate(diffs)]
    keyboard.append([InlineKeyboardButton("📂 همه سطوح", callback_data='questions:pdf_diff:all')])
    keyboard.append(_back("🔙 بازگشت", "questions:pdf_back_topic"))
    t_label = f" — {topic}" if topic != 'همه' else ''
    await query.edit_message_text(f"📄 <b>{lesson}{t_label}</b>\n\nسطح سختی را انتخاب کنید:",
                                  parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _pdf_count_select(query, context, lesson, topic):
    context.user_data['pdf_lesson'] = lesson
    context.user_data['pdf_topic']  = topic
    t_label = f" — {topic}" if topic != 'همه' else ''
    diffs = context.user_data.get('_pdf_diffs')
    back_cb = 'questions:pdf_back_diff' if diffs and len(diffs) > 1 else 'questions:pdf_back_topic'
    keyboard = [
        [InlineKeyboardButton("۱۰ سوال",  callback_data='questions:pdf_count:10'),
         InlineKeyboardButton("۲۰ سوال",  callback_data='questions:pdf_count:20')],
        [InlineKeyboardButton("۳۰ سوال",  callback_data='questions:pdf_count:30'),
         InlineKeyboardButton("۵۰ سوال",  callback_data='questions:pdf_count:50')],
        _back("🔙 بازگشت", back_cb),
    ]
    await query.edit_message_text(
        f"📄 <b>{lesson}{t_label}</b>\n\nتعداد سوالات:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _pdf_mode_select(query, context):
    """
    🆕 مرحله‌ی جدید: انتخاب قالب خروجی.
    - تمرین: پاسخ و تحلیل بلافاصله زیر هر سوال (مناسب مرور شخصی)
    - آزمون: سوالات بدون پاسخ + پاسخنامه‌ی جدا + پاسخ تشریحی در انتها
      (مناسب چاپ و خودآزمایی واقعی)
    """
    lesson = context.user_data.get('pdf_lesson', '')
    count  = context.user_data.get('pdf_count', 20)
    keyboard = [
        [InlineKeyboardButton("🎯 تمرین (پاسخ زیر هر سوال)", callback_data='questions:pdf_mode:practice')],
        [InlineKeyboardButton("📝 آزمون (پاسخنامه در انتها)", callback_data='questions:pdf_mode:exam')],
        _back("🔙 بازگشت", "questions:pdf_back_count"),
    ]
    await query.edit_message_text(
        f"📄 <b>{lesson}</b> — {count} سوال\n\nقالب خروجی را انتخاب کنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _resolve_question_images(context, questions: list) -> tuple:
    """
    دانلود تصاویر سوال/پاسخ (در صورت وجود file_id تلگرام) و تبدیل به
    ImageReader آماده برای reportlab. qbank هیچ‌وقت مستقیم با تلگرام
    کار نمی‌کند؛ این تابع همان لایه‌ی واسط است.
    فعلاً فرم طراحی سوال، آپلود تصویر را جمع‌آوری نمی‌کند، پس این
    دیکشنری‌ها معمولاً خالی می‌مانند — اما اگر یک سوال فیلد
    question_image/answer_image داشته باشد (مثلاً به‌صورت دستی یا در
    نسخه‌ی بعدی فرم طراحی سوال ثبت شود)، همین الان هم به‌درستی و
    Responsive در PDF نمایش داده می‌شود.
    """
    from reportlab.lib.utils import ImageReader
    q_images, a_images = {}, {}
    for q in questions:
        qid = str(q.get('_id', ''))
        for field, target in (('question_image', q_images), ('answer_image', a_images)):
            file_id = q.get(field)
            if not file_id:
                continue
            try:
                tg_file = await context.bot.get_file(file_id)
                raw = await tg_file.download_as_bytearray()
                target[qid] = ImageReader(io.BytesIO(bytes(raw)))
            except Exception:
                logger.warning(f"qbank: could not download image for question {qid}")
    return q_images, a_images


async def _generate_pdf_v2(query, context, uid, mode: str = 'practice'):
    """
    ساخت آزمون PDF کامل با معماری ماژولار qbank (کاور + سوالات +
    در حالت آزمون: پاسخنامه + پاسخ تشریحی جدا). جایگزین کامل نسخه‌ی
    قبلی که فقط یک فایل txt ساده می‌ساخت.
    """
    lesson     = context.user_data.get('pdf_lesson', '')
    chapter    = context.user_data.get('pdf_chapter')
    topic      = context.user_data.get('pdf_topic', 'همه')
    difficulty = context.user_data.get('pdf_difficulty')
    count      = context.user_data.get('pdf_count', 20)

    from qbank.query import fetch_exam_questions, ExamMeta
    qs = await fetch_exam_questions(
        db, lesson=lesson, chapter=chapter, topic=topic if topic != 'همه' else None,
        difficulty=difficulty, count=count, randomize=True,
    )
    if not qs:
        await query.edit_message_text(
            "❌ سوالی برای این فیلتر پیدا نشد.",
            reply_markup=InlineKeyboardMarkup([
                _back("🔙 بازگشت", "questions:pdf_menu")
            ])); return

    user = await db.get_user(uid)
    student_name = user.get('name', '') if user else ''

    q_images, a_images = await _resolve_question_images(context, qs)

    try:
        from qbank import generate_exam_pdf
        meta = ExamMeta(lesson=lesson, chapter=chapter, topic=topic,
                         difficulty=difficulty, student_name=student_name)
        # 🧵 ساخت PDF (reportlab) کاملاً همزمان/CPU-bound است و اگر مستقیم
        # await شود، event loop اصلی ربات را برای چند ثانیه بلاک می‌کند —
        # یعنی در همان لحظه هیچ کاربر دیگری (حتی /start) پاسخ نمی‌گیرد.
        # با asyncio.to_thread آن را در یک ترد جدا اجرا می‌کنیم تا لوپ آزاد بماند.
        pdf_bytes = await asyncio.to_thread(
            generate_exam_pdf, qs, meta, mode=mode,
            question_images=q_images, answer_images=a_images,
        )
    except Exception as e:
        logger.exception("qbank exam PDF generation failed")
        await query.edit_message_text(
            f"❌ خطا در ساخت PDF: {e}",
            reply_markup=InlineKeyboardMarkup([
                _back("🔙 بازگشت", "questions:main")
            ])); return

    for k in ('pdf_chapter', 'pdf_difficulty', 'pdf_count', '_pdf_chapters', '_pdf_diffs'):
        context.user_data.pop(k, None)

    t_label = f" — {topic}" if topic and topic != 'همه' else ''
    mode_label = "تمرین" if mode == 'practice' else "آزمون"
    file_obj = io.BytesIO(pdf_bytes)
    fname = f"qbank_{lesson}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    file_obj.name = fname

    try:
        protect = await db.get_setting('protect_content_enabled', True)
        await query.message.reply_document(
            document=file_obj,
            caption=f"📄 <b>{mode_label} بانک سوال</b>\n📚 {lesson}{t_label}\n🔢 {len(qs)} سوال\n"
                    f"🔖 کد: {meta.exam_code}",
            parse_mode='HTML',
            filename=fname,
            protect_content=protect)
        await query.edit_message_text(
            f"✅ فایل PDF ({mode_label}) ارسال شد!\n📚 {lesson}\n🔢 {len(qs)} سوال",
            reply_markup=InlineKeyboardMarkup([
                _back("🔙 بازگشت به منو", "questions:main")
            ]))
    except Exception as e:
        await query.edit_message_text(f"❌ خطا: {e}",
            reply_markup=InlineKeyboardMarkup([
                _back("🔙 بازگشت", "questions:main")
            ]))


# ══════════════════════════════════════════════════════════
#  انتخاب درس/مبحث برای تمرین
# ══════════════════════════════════════════════════════════

async def _term_select(query, context, mode):
    """
    FIX جدید: لایه‌ی انتخاب ترم قبل از درس — مثل بخش منابع علوم پایه.
    قبلاً همه دروس همه ترم‌ها یکجا و تخت نشان داده می‌شد که گیج‌کننده
    و طولانی بود؛ حالا اول ترم، بعد فقط دروس همان ترم.
    """
    from utils import TERMS
    keyboard = []
    for i in range(0, len(TERMS), 2):
        row = [InlineKeyboardButton(f"📘 {TERMS[i]}", callback_data=f'questions:sel_term:{mode}:{i}')]
        if i+1 < len(TERMS):
            row.append(InlineKeyboardButton(f"📘 {TERMS[i+1]}", callback_data=f'questions:sel_term:{mode}:{i+1}'))
        keyboard.append(row)
    keyboard.append(_back("🔙 بازگشت", "questions:practice"))
    label = "شبیه‌سازی امتحان" if mode == 'exam' else "تمرین آزاد"
    await query.edit_message_text(
        f"📚 <b>{label}</b>\n\nترم را انتخاب کنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _lesson_select(query, context, mode, term_idx: int = None):
    from utils import TERMS
    term = TERMS[term_idx] if term_idx is not None and term_idx < len(TERMS) else None
    context.user_data['sel_term_idx'] = term_idx
    lessons = await db.get_lessons(term=term)
    back_cb = f'questions:sel_term_back:{mode}' if term_idx is not None else 'questions:practice'
    if not lessons:
        await query.edit_message_text(
            f"❌ هنوز درسی برای {term or 'این بخش'} ثبت نشده.",
            reply_markup=InlineKeyboardMarkup([
                _back("🔙 بازگشت", back_cb)
            ])); return
    context.user_data['_lessons'] = lessons
    keyboard = []
    for i in range(0, len(lessons), 2):
        row = [InlineKeyboardButton(f"📚 {lessons[i]}", callback_data=f'questions:sel_lesson:{mode}:{i}')]
        if i+1 < len(lessons):
            row.append(InlineKeyboardButton(f"📚 {lessons[i+1]}", callback_data=f'questions:sel_lesson:{mode}:{i+1}'))
        keyboard.append(row)
    keyboard.append(_back("🔙 بازگشت", back_cb))
    label = "شبیه‌سازی امتحان" if mode == 'exam' else "تمرین آزاد"
    term_label = f" — {term}" if term else ""
    await query.edit_message_text(f"📚 <b>{label}{term_label}</b>\n\nدرس را انتخاب کنید:",
                                  parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _topic_select(query, context, lesson, mode):
    topics = await db.get_topics(lesson)
    context.user_data['_topics'] = topics
    # بازگشت به لیست درس‌های همان ترم (نه شروع دوباره از انتخاب ترم)
    term_idx = context.user_data.get('sel_term_idx')
    if term_idx is not None:
        back_cb = f'questions:sel_term:{mode}:{term_idx}'
    else:
        back_cb = f'questions:{"exam" if mode=="exam" else "free"}'
    keyboard = [[InlineKeyboardButton(f"📌 {t}", callback_data=f'questions:sel_topic:{mode}:{i}')]
                for i, t in enumerate(topics)]
    keyboard.append([InlineKeyboardButton("📂 همه مباحث", callback_data=f'questions:sel_topic:{mode}:all')])
    keyboard.append(_back("🔙 بازگشت", back_cb))
    await query.edit_message_text(f"📚 <b>{lesson}</b>\n\nمبحث را انتخاب کنید:",
                                  parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════════════════
#  آمار
# ══════════════════════════════════════════════════════════

async def _quiz_stats(query, uid):
    stats   = await db.user_stats(uid)
    total   = stats['total_answers']
    correct = stats['correct_answers']
    pct     = stats['percentage']
    weak    = stats.get('weak_topics', [])[:5]
    bar     = '█' * int(pct/10) + '░' * (10 - int(pct/10))

    designed = await db.questions.count_documents({'creator_id': uid})

    text = (
        f"📊 <b>آمار تمرین من</b>\n━━━━━━━━━━━━━━━━\n\n"
        f"🧪 کل سوالات: <b>{total}</b>\n"
        f"✅ صحیح: <b>{correct}</b>  ❌ اشتباه: <b>{total-correct}</b>\n\n"
        f"📈 درصد صحیح:\n  {bar} <b>{pct}%</b>\n\n"
        f"✏️ سوالات طراحی شده توسط شما: <b>{designed}</b>\n"
    )
    if weak:
        text += f"\n⚡ <b>نقاط ضعف:</b>\n" + "".join(f"  • {w}\n" for w in weak)
    else:
        text += "\n🎉 هیچ نقطه ضعف ثبت‌شده‌ای ندارید!"

    await query.edit_message_text(text, parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            _back("🔙 بازگشت", "questions:main")
        ]))


# ══════════════════════════════════════════════════════════
#  طراحی سوال
# ══════════════════════════════════════════════════════════

async def _create_start(query, context):
    lessons = await db.get_lessons()
    if not lessons:
        await query.edit_message_text(
            "❌ هنوز درسی تعریف نشده.",
            reply_markup=InlineKeyboardMarkup([
                _back("🔙 بازگشت", "questions:main")
            ])); return
    context.user_data['_lessons'] = lessons
    keyboard = []
    for i in range(0, len(lessons), 2):
        row = [InlineKeyboardButton(f"📚 {lessons[i]}", callback_data=f'questions:cr_lesson:{i}')]
        if i+1 < len(lessons):
            row.append(InlineKeyboardButton(f"📚 {lessons[i+1]}", callback_data=f'questions:cr_lesson:{i+1}'))
        keyboard.append(row)
    keyboard.append(_back("🔙 بازگشت", "questions:main"))
    is_ca = context.user_data.get('creating_as_ca', False)
    note  = "\n🤖 سوال شما با برچسب «طراحی توسط بات» ثبت می‌شود." if is_ca else \
            "\n⏳ سوال شما پس از تأیید ادمین در بانک قرار می‌گیرد."
    await query.edit_message_text(
        f"✏️ <b>طراحی سوال جدید</b>{note}\n\nدرس را انتخاب کنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _create_topic_select(query, context, lesson):
    topics = await db.get_topics(lesson)
    if not topics:
        context.user_data.setdefault('new_q', {})['topic'] = lesson
        context.user_data['mode']        = 'creating_question'
        context.user_data['create_step'] = 'question'
        await query.edit_message_text(
            f"✏️ <b>طراحی سوال</b>\n📚 {lesson}\n\n"
            "📝 <b>گام ۱ از ۵ — متن سوال</b>\n\nسوال را بنویسید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='questions:main')
            ]]))
        return CREATING_Q
    context.user_data['_topics'] = topics
    keyboard = [[InlineKeyboardButton(f"📌 {t}", callback_data=f'questions:cr_topic:{i}')]
                for i, t in enumerate(topics)]
    keyboard.append(_back("🔙 بازگشت", "questions:create"))
    await query.edit_message_text(f"✏️ <b>{lesson}</b>\n\nمبحث را انتخاب کنید:",
                                  parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_create_question_steps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    step = context.user_data.get('create_step', '')
    q    = context.user_data.setdefault('new_q', {})

    if text in ('❌ لغو', '/start', '/cancel'):
        context.user_data.pop('mode', None)
        context.user_data.pop('create_step', None)
        await update.message.reply_text("❌ طراحی سوال لغو شد.")
        return ConversationHandler.END

    if step == 'question':
        if len(text) < 10:
            await update.message.reply_text("⚠️ متن سوال باید حداقل ۱۰ کاراکتر باشد.")
            return CREATING_Q
        q['question'] = text
        context.user_data['create_step'] = 'opt1'
        await update.message.reply_text(
            "📝 <b>گام ۲ از ۵ — گزینه الف</b>\n\nگزینه اول را بنویسید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='questions:main')
            ]]))

    elif step in ('opt1', 'opt2', 'opt3', 'opt4'):
        opts = q.setdefault('options', [])
        opts.append(text)
        next_map = {'opt1': ('opt2', 'ب', 3), 'opt2': ('opt3', 'ج', 4), 'opt3': ('opt4', 'د', 4)}
        if step == 'opt4':
            context.user_data['create_step'] = 'correct'
            opt_list = "\n".join(f"  {LETTERS[i]} {o}" for i, o in enumerate(opts))
            await update.message.reply_text(
                f"✅ گزینه‌ها:\n{opt_list}\n\n"
                "📝 <b>گام ۴ از ۵ — گزینه صحیح</b>\n\nشماره گزینه صحیح را بنویسید (1-4):",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ لغو", callback_data='questions:main')
                ]]))
        else:
            ns, label, step_n = next_map[step]
            context.user_data['create_step'] = ns
            await update.message.reply_text(
                f"📝 <b>گام {step_n} از ۵ — گزینه {label}</b>\n\nگزینه بعدی را بنویسید:",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ لغو", callback_data='questions:main')
                ]]))

    elif step == 'correct':
        if text not in ('1', '2', '3', '4'):
            await update.message.reply_text("⚠️ عدد ۱ تا ۴ وارد کنید.")
            return CREATING_Q
        q['correct'] = int(text) - 1
        context.user_data['create_step'] = 'difficulty'
        keyboard = [
            [InlineKeyboardButton("🟢 آسان",  callback_data='qd:easy')],
            [InlineKeyboardButton("🟡 متوسط", callback_data='qd:medium')],
            [InlineKeyboardButton("🔴 سخت",   callback_data='qd:hard')],
        ]
        await update.message.reply_text(
            "📝 <b>گام ۵ از ۵ — سطح سختی</b>\n\nسطح سختی را انتخاب کنید:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    elif step == 'explanation':
        q['explanation'] = '' if text == '-' else text
        await _save_question(update, context)
        return ConversationHandler.END

    return CREATING_Q


async def handle_difficulty_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    diff_map = {'easy': 'آسان 🟢', 'medium': 'متوسط 🟡', 'hard': 'سخت 🔴'}
    diff = diff_map.get(query.data.split(':')[1], 'متوسط 🟡')
    context.user_data.setdefault('new_q', {})['difficulty'] = diff
    context.user_data['create_step'] = 'explanation'
    await query.edit_message_text(
        "📝 <b>گام آخر — توضیح پاسخ</b>\n\n"
        "توضیح پاسخ صحیح را بنویسید.\n"
        "اگر توضیحی ندارید <code>-</code> بزنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ لغو", callback_data='questions:main')
        ]]))
    return CREATING_Q


async def _save_question(update, context):
    uid       = update.effective_user.id
    q         = context.user_data.get('new_q', {})
    is_ca     = context.user_data.get('creating_as_ca', False)
    is_admin  = (uid == ADMIN_ID)
    auto      = is_ca or is_admin
    by_bot    = is_ca

    # دریافت نام طراح
    creator_user = await db.get_user(uid)
    creator_name = creator_user.get('name', '') if creator_user else ''

    result = await db.questions.insert_one({
        'lesson':         q.get('lesson', ''),
        'topic':          q.get('topic', ''),
        'difficulty':     q.get('difficulty', 'متوسط 🟡'),
        'question':       q.get('question', ''),
        'options':        q.get('options', []),
        'correct_answer': q.get('correct', 0),
        'explanation':    q.get('explanation', ''),
        'creator_id':     uid,
        'creator_name':   creator_name,
        'by_bot':         by_bot,
        'approved':       auto,
        'created_at':     datetime.now().isoformat(),
        'attempt_count':  0,
        'correct_count':  0,
    })
    qid = str(result.inserted_id)

    for k in ['new_q', 'create_step', 'mode', 'cr_lesson', 'creating_as_ca']:
        context.user_data.pop(k, None)

    if auto:
        msg = "✅ <b>سوال با موفقیت در بانک سوال ثبت شد!</b>"
        if by_bot:
            msg += "\n\n<i>🤖 برچسب: طراحی شده توسط ادمین محتوا</i>"
    else:
        msg = (
            "✅ <b>سوال ارسال شد و در انتظار تأیید ادمین است.</b>\n"
            "پس از تأیید در بانک سوال نمایش داده می‌شود.\n\n"
            f"<i>✏️ طراح: {creator_name}</i>"
        )
        # FIX: اطلاع‌رسانی به ادمین برای تأیید
        try:
            opts   = q.get('options', [])
            ltrs   = ['الف', 'ب', 'ج', 'د']
            ca_idx = q.get('correct', 0)
            opts_text = '\n'.join(
                f"  {'✅' if i == ca_idx else '▪️'} {ltrs[i]}) {opt}"
                for i, opt in enumerate(opts[:4])
            )
            diff_map = {'آسان 🟢': '🟢 آسان', 'متوسط 🟡': '🟡 متوسط', 'سخت 🔴': '🔴 سخت'}
            diff_txt = diff_map.get(q.get('difficulty', ''), q.get('difficulty', ''))
            admin_notif = (
                f"🔔 <b>سوال جدید برای تأیید</b>\n\n"
                f"✏️ طراح: <b>{creator_name}</b>\n"
                f"📚 {q.get('lesson','')} — {q.get('topic','')}\n"
                f"📊 {diff_txt}\n\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"❓ <b>{q.get('question', '')}</b>\n\n"
                f"{opts_text}\n\n"
                f"📝 توضیح: {q.get('explanation','') or '—'}"
            )
            await context.bot.send_message(
                ADMIN_ID, admin_notif, parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ تأیید", callback_data=f'admin:approve_q:{qid}'),
                    InlineKeyboardButton("🗑 رد",    callback_data=f'admin:reject_q:{qid}'),
                ]])
            )
        except Exception as e:
            logger.warning(f"Admin notification failed: {e}")

    await update.message.reply_text(
        msg, parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            _back("🔙 بازگشت به بانک سوال", "questions:main")
        ]))


# ══════════════════════════════════════════════════════════
#  مدیریت سوالات توسط ادمین محتوا
# ══════════════════════════════════════════════════════════

async def _ca_question_list(query, uid: int, context):
    """لیست سوالات با قابلیت فیلتر — برای ادمین محتوا و ادمین"""
    if not await db.is_content_admin(uid):
        await query.answer("❌ دسترسی ندارید!", show_alert=True)
        return

    # فیلترها
    f_status = context.user_data.get('caq_filter_status', 'all')  # all/approved/pending
    f_source = context.user_data.get('caq_filter_source', 'all')  # all/bot/student

    # ساخت query
    q_filter = {}
    if f_status == 'approved':
        q_filter['approved'] = True
    elif f_status == 'pending':
        q_filter['approved'] = False

    if f_source == 'bot':
        q_filter['by_bot'] = True
    elif f_source == 'student':
        q_filter['by_bot'] = {'$ne': True}

    questions = await db.questions.find(q_filter).sort('created_at', -1).to_list(200)

    # آمار
    total    = len(questions)
    approved = sum(1 for q in questions if q.get('approved'))
    pending  = total - approved
    by_bot_c = sum(1 for q in questions if q.get('by_bot'))
    by_stu_c = total - by_bot_c

    # دکمه‌های فیلتر
    status_labels = {
        'all':      f"{'✅' if f_status=='all' else '⬜'} همه",
        'approved': f"{'✅' if f_status=='approved' else '⬜'} تأییدشده",
        'pending':  f"{'✅' if f_status=='pending' else '⬜'} در انتظار",
    }
    source_labels = {
        'all':     f"{'✅' if f_source=='all' else '⬜'} همه منابع",
        'bot':     f"{'✅' if f_source=='bot' else '⬜'} توسط بات",
        'student': f"{'✅' if f_source=='student' else '⬜'} توسط دانشجو",
    }

    keyboard = [
        [
            InlineKeyboardButton(status_labels['all'],      callback_data='questions:ca_q_filter:status:all'),
            InlineKeyboardButton(status_labels['approved'], callback_data='questions:ca_q_filter:status:approved'),
            InlineKeyboardButton(status_labels['pending'],  callback_data='questions:ca_q_filter:status:pending'),
        ],
        [
            InlineKeyboardButton(source_labels['all'],     callback_data='questions:ca_q_filter:source:all'),
            InlineKeyboardButton(source_labels['bot'],     callback_data='questions:ca_q_filter:source:bot'),
            InlineKeyboardButton(source_labels['student'], callback_data='questions:ca_q_filter:source:student'),
        ],
    ]

    # لیست سوالات (حداکثر ۱۵ تا)
    for q in questions[:15]:
        qid     = str(q['_id'])
        status  = "✅" if q.get('approved') else "⏳"
        source  = "🤖" if q.get('by_bot') else "✏️"
        creator = q.get('creator_name', '') or ''
        lesson  = q.get('lesson', '')
        text_q  = q.get('question', '')[:30]
        creator_tag = f" | {creator}" if (creator and not q.get('by_bot')) else ''
        keyboard.append([InlineKeyboardButton(
            f"{status}{source} {text_q} | {lesson}{creator_tag}",
            callback_data=f'questions:ca_q_view:{qid}'
        )])

    back_cb = 'ca:main' if uid != int(__import__('os').getenv('ADMIN_ID', '0')) else 'admin:main'
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb)])

    header = (
        f"🧪 <b>مدیریت سوالات</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 مجموع: <b>{total}</b>  ✅ تأیید: <b>{approved}</b>  ⏳ انتظار: <b>{pending}</b>\n"
        f"🤖 توسط بات: <b>{by_bot_c}</b>  ✏️ توسط دانشجو: <b>{by_stu_c}</b>\n\n"
        f"<i>روی هر سوال بزنید برای مشاهده و مدیریت</i>"
    )

    try:
        await query.edit_message_text(
            header, parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        pass


async def _ca_question_view(query, uid: int, qid: str):
    """نمایش کامل یک سوال با دکمه‌های مدیریت"""
    if not await db.is_content_admin(uid):
        await query.answer("❌ دسترسی ندارید!", show_alert=True)
        return

    q = await db.get_question_by_id(qid)
    if not q:
        await query.answer("❌ سوال پیدا نشد!", show_alert=True)
        return

    opts    = q.get('options', [])
    ltrs    = ['الف', 'ب', 'ج', 'د']
    ca_idx  = q.get('correct_answer', 0)
    opts_text = '\n'.join(
        f"  {'✅' if i == ca_idx else '▪️'} {ltrs[i]}) {opt}"
        for i, opt in enumerate(opts[:4])
    )

    diff_map = {'آسان 🟢': '🟢 آسان', 'متوسط 🟡': '🟡 متوسط', 'سخت 🔴': '🔴 سخت'}
    diff_txt = diff_map.get(q.get('difficulty', ''), q.get('difficulty', ''))

    status = "✅ تأیید شده" if q.get('approved') else "⏳ در انتظار تأیید"

    # تگ طراح
    if q.get('by_bot'):
        creator_line = "🤖 <b>طراح:</b> ادمین محتوا (بات)"
    elif q.get('creator_name'):
        creator_line = f"✏️ <b>طراح:</b> {q['creator_name']}"
    else:
        creator_line = "✏️ <b>طراح:</b> نامشخص"

    text = (
        f"🧪 <b>مشاهده سوال</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📚 {q.get('lesson','')} — {q.get('topic','')}\n"
        f"📊 {diff_txt}  |  {status}\n"
        f"{creator_line}\n"
        f"📅 {fmt_jalali_dt(q.get('created_at',''), with_time=False)}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"❓ <b>{q.get('question','')}</b>\n\n"
        f"{opts_text}\n\n"
        f"📝 <b>توضیح:</b> {q.get('explanation','') or '—'}\n\n"
        f"📈 آمار: {q.get('attempt_count',0)} بار — {q.get('correct_count',0)} صحیح"
    )

    keyboard = []

    # دکمه تأیید/رد
    if not q.get('approved'):
        keyboard.append([
            InlineKeyboardButton("✅ تأیید",  callback_data=f'questions:ca_q_approve:{qid}'),
            InlineKeyboardButton("🗑 حذف",    callback_data=f'questions:ca_q_del:{qid}'),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("🗑 حذف سوال", callback_data=f'questions:ca_q_del:{qid}'),
        ])

    keyboard.append([InlineKeyboardButton("🔙 بازگشت به لیست", callback_data='questions:ca_q_list')])

    try:
        await query.edit_message_text(
            text, parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        pass

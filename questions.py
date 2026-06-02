"""
بانک سوال — نسخه حرفه‌ای
✅ آزمون سفارشی (تعداد + زمان دلخواه)
✅ خروجی PDF از سوالات
✅ طراحی سوال توسط دانشجو و ادمین محتوا
✅ نمایش طراح سوال (کوچک)
✅ فیلتر درس + مبحث
✅ آمار پیشرفته
"""
import os, io, logging, time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db

logger     = logging.getLogger(__name__)
ADMIN_ID   = int(os.getenv('ADMIN_ID', '0'))
ANSWERING  = 4
CREATING_Q = 6

DIFF_EMOJI = {'آسان 🟢': '🟢', 'متوسط 🟡': '🟡', 'سخت 🔴': '🔴'}
LETTERS    = ['🅐', '🅑', '🅒', '🅓']


# ══════════════════════════════════════════════════════════
#  Callback اصلی
# ══════════════════════════════════════════════════════════
async def questions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    data   = query.data
    parts  = data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'
    uid    = update.effective_user.id

    # ── منوی اصلی ──
    if action == 'main':
        await _main_menu(query)

    # ── بانک فایل ──
    elif action == 'file_bank':
        await _fb_lessons(query, context)

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
        await _fb_files(query, context, lesson, topic)

    elif data.startswith('download_qbank:'):
        fid  = parts[1]
        item = await db.get_qbank_file(fid)
        if not item:
            await query.answer("فایل پیدا نشد!", show_alert=True); return
        await db.inc_qbank_download(fid, uid)
        caption = (f"📁 <b>بانک سوال</b>\n📚 {item.get('lesson','')} — {item.get('topic','')}\n"
                   f"📝 {item.get('description','')}\n⬇️ {item.get('downloads',0)} دانلود")
        try:
            await query.message.reply_document(item['file_id'], caption=caption, parse_mode='HTML')
        except:
            try:    await query.message.reply_photo(item['file_id'], caption=caption, parse_mode='HTML')
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

    elif action == 'cx_time':
        minutes = int(parts[2])
        context.user_data.setdefault('cx', {})['time'] = minutes
        await _cx_start(query, context, uid)

    # ── تمرین آزاد ──
    elif action == 'practice':
        await _practice_menu(query)

    elif action == 'free':
        await _lesson_select(query, context, 'free')

    elif action == 'weak':
        context.user_data['quiz'] = {'mode': 'weak', 'answered': [], 'correct': 0, 'total': 999}
        await _next_q(query, context, uid)

    elif action == 'hard':
        context.user_data['quiz'] = {'mode': 'hard', 'difficulty': 'سخت 🔴', 'answered': [], 'correct': 0, 'total': 999}
        await _next_q(query, context, uid)

    elif action == 'exam':
        await _lesson_select(query, context, 'exam')

    elif action == 'sel_lesson':
        mode    = parts[2]; idx = int(parts[3])
        lessons = context.user_data.get('_lessons', [])
        if idx < len(lessons):
            lesson = lessons[idx]
            context.user_data['sel_lesson'] = lesson
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

    # ── خروجی PDF ──
    elif action == 'pdf_menu':
        await _pdf_menu(query, context)

    elif action == 'pdf_lesson':
        idx     = int(parts[2])
        lessons = context.user_data.get('_pdf_lessons', [])
        if idx < len(lessons):
            context.user_data['pdf_lesson'] = lessons[idx]
            await _pdf_topic_select(query, context, lessons[idx])

    elif action == 'pdf_topic':
        topics = context.user_data.get('_pdf_topics', [])
        topic  = 'همه' if parts[2] == 'all' else (topics[int(parts[2])] if int(parts[2]) < len(topics) else 'همه')
        lesson = context.user_data.get('pdf_lesson', '')
        await _pdf_count_select(query, context, lesson, topic)

    elif action == 'pdf_count':
        lesson = context.user_data.get('pdf_lesson', '')
        topic  = context.user_data.get('pdf_topic', 'همه')
        count  = int(parts[2])
        await query.edit_message_text("⏳ در حال ساخت PDF...", parse_mode='HTML')
        await _generate_pdf(query, context, uid, lesson, topic, count)

    elif action == 'pdf_topic_sel':
        topics = context.user_data.get('_pdf_topics', [])
        topic  = 'همه' if parts[2] == 'all' else (topics[int(parts[2])] if int(parts[2]) < len(topics) else 'همه')
        context.user_data['pdf_topic'] = topic
        lesson = context.user_data.get('pdf_lesson','')
        await _pdf_count_select(query, context, lesson, topic)

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
        [InlineKeyboardButton("📄 خروجی PDF سوالات",      callback_data='questions:pdf_menu')],
        [InlineKeyboardButton("✏️ طراحی سوال",            callback_data='questions:create')],
        [InlineKeyboardButton("📊 آمار و پیشرفت من",      callback_data='questions:stats')],
    ]
    await query.edit_message_text(
        "🧪 <b>بانک سوال</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📁 <b>بانک فایل:</b> دانلود PDF سوالات\n"
        "🧪 <b>تمرین سریع:</b> سوال چهارگزینه‌ای\n"
        "📝 <b>آزمون سفارشی:</b> تعداد و زمان دلخواه\n"
        "📄 <b>خروجی PDF:</b> سوالات را چاپ کنید\n"
        "✏️ <b>طراحی سوال:</b> سوال خودتان بسازید\n"
        "📊 <b>آمار:</b> پیشرفت و نقاط ضعف",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _practice_menu(query):
    keyboard = [
        [InlineKeyboardButton("📖 تمرین آزاد",                callback_data='questions:free')],
        [InlineKeyboardButton("⚡ نقاط ضعف من",               callback_data='questions:weak')],
        [InlineKeyboardButton("📝 شبیه‌سازی امتحان (۲۰ سوال)", callback_data='questions:exam')],
        [InlineKeyboardButton("🔴 سوالات سطح سخت",            callback_data='questions:hard')],
        [InlineKeyboardButton("🔙 بازگشت",                    callback_data='questions:main')],
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
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='questions:main')
            ]])); return
    context.user_data['_cx_lessons'] = lessons
    context.user_data['cx'] = {}
    keyboard = []
    for i in range(0, len(lessons), 2):
        row = [InlineKeyboardButton(f"📚 {lessons[i]}", callback_data=f'questions:cx_lesson:{i}')]
        if i+1 < len(lessons):
            row.append(InlineKeyboardButton(f"📚 {lessons[i+1]}", callback_data=f'questions:cx_lesson:{i+1}'))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='questions:main')])
    await query.edit_message_text(
        "📝 <b>آزمون سفارشی</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "<b>گام ۱ از ۳:</b> درس را انتخاب کنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _cx_topic_select(query, context, lesson):
    topics = await db.get_topics(lesson)
    context.user_data['_cx_topics'] = topics
    keyboard = [[InlineKeyboardButton(f"📌 {t}", callback_data=f'questions:cx_topic:{i}')]
                for i, t in enumerate(topics)]
    keyboard.append([InlineKeyboardButton("📂 همه مباحث", callback_data='questions:cx_topic:all')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='questions:custom_exam')])
    await query.edit_message_text(
        f"📝 <b>آزمون سفارشی</b>\n📚 {lesson}\n\n"
        "<b>گام ۲ از ۳:</b> مبحث را انتخاب کنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _cx_count_select(query, context):
    cx     = context.user_data.get('cx', {})
    lesson = cx.get('lesson', '')
    topic  = cx.get('topic', 'همه')
    keyboard = [
        [InlineKeyboardButton("5 سوال",  callback_data='questions:cx_count:5'),
         InlineKeyboardButton("10 سوال", callback_data='questions:cx_count:10')],
        [InlineKeyboardButton("15 سوال", callback_data='questions:cx_count:15'),
         InlineKeyboardButton("20 سوال", callback_data='questions:cx_count:20')],
        [InlineKeyboardButton("30 سوال", callback_data='questions:cx_count:30'),
         InlineKeyboardButton("40 سوال", callback_data='questions:cx_count:40')],
        [InlineKeyboardButton("🔙 بازگشت", callback_data='questions:custom_exam')],
    ]
    t_label = f" — {topic}" if topic != 'همه' else ''
    await query.edit_message_text(
        f"📝 <b>آزمون سفارشی</b>\n📚 {lesson}{t_label}\n\n"
        "<b>گام ۳ از ۴:</b> تعداد سوالات:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _cx_time_select(query, context):
    cx    = context.user_data.get('cx', {})
    count = cx.get('count', 10)
    keyboard = [
        [InlineKeyboardButton("بدون محدودیت ⏳", callback_data='questions:cx_time:0')],
        [InlineKeyboardButton("۱۰ دقیقه ⏱",  callback_data='questions:cx_time:10'),
         InlineKeyboardButton("۲۰ دقیقه ⏱",  callback_data='questions:cx_time:20')],
        [InlineKeyboardButton("۳۰ دقیقه ⏱",  callback_data='questions:cx_time:30'),
         InlineKeyboardButton("۴۵ دقیقه ⏱",  callback_data='questions:cx_time:45')],
        [InlineKeyboardButton("۶۰ دقیقه ⏱",  callback_data='questions:cx_time:60'),
         InlineKeyboardButton("۹۰ دقیقه ⏱",  callback_data='questions:cx_time:90')],
        [InlineKeyboardButton("🔙 بازگشت", callback_data='questions:custom_exam')],
    ]
    await query.edit_message_text(
        f"📝 <b>آزمون سفارشی</b>\n🔢 {count} سوال\n\n"
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
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 دوباره", callback_data='questions:custom_exam'),
                InlineKeyboardButton("🏠 منو",    callback_data='questions:main')
            ]]))
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
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 دوباره",    callback_data='questions:practice'),
                InlineKeyboardButton("📊 آمار کلی",  callback_data='questions:stats'),
                InlineKeyboardButton("🏠 منو",       callback_data='questions:main')
            ]]))
        return

    if mode == 'weak':
        qs = await db.get_weak_questions(uid, limit=1)
    else:
        qs = await db.get_questions(lesson=lesson, topic=topic, difficulty=diff, limit=1, exclude=done)

    if not qs:
        await query.edit_message_text(
            "❌ سوال دیگری یافت نشد!\nتمام سوالات موجود را پاسخ دادید.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='questions:practice')
            ]]))
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
        if i == correct_idx:     marker = "✅"
        elif i == sel and not is_correct: marker = "❌"
        else:                    marker = "⚫"
        options_text += f"{marker} {opt}\n"

    text = (f"{icon} <b>{'صحیح!' if is_correct else 'اشتباه!'}</b>\n\n"
            f"{q_doc['question']}\n\n{options_text}")
    if expl:
        text += f"\n💡 <b>توضیح:</b> {expl}"

    keyboard = [[
        InlineKeyboardButton("➡️ سوال بعدی", callback_data='questions:next'),
        InlineKeyboardButton("🏠 منو",        callback_data='questions:main')
    ]]
    await query.edit_message_text(text, parse_mode='HTML',
                                  reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════════════════
#  بانک فایل ادمین
# ══════════════════════════════════════════════════════════

async def _fb_lessons(query, context):
    lessons = await db.get_lessons()
    if not lessons:
        await query.edit_message_text(
            "📁 <b>بانک فایل</b>\n\n❌ هنوز فایلی آپلود نشده.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='questions:main')
            ]])); return
    context.user_data['_fb_lessons'] = lessons
    keyboard = []
    for i in range(0, len(lessons), 2):
        row = [InlineKeyboardButton(f"📚 {lessons[i]}", callback_data=f'questions:fb_lesson:{i}')]
        if i+1 < len(lessons):
            row.append(InlineKeyboardButton(f"📚 {lessons[i+1]}", callback_data=f'questions:fb_lesson:{i+1}'))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='questions:main')])
    await query.edit_message_text("📁 <b>بانک فایل سوالات</b>\n\nدرس را انتخاب کنید:",
                                  parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _fb_topics(query, context, lesson):
    topics = await db.get_topics(lesson)
    context.user_data['_fb_topics'] = topics
    keyboard = [[InlineKeyboardButton(f"📌 {t}", callback_data=f'questions:fb_topic:{i}')]
                for i, t in enumerate(topics)]
    keyboard.append([InlineKeyboardButton("📂 همه مباحث", callback_data='questions:fb_topic:all')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='questions:file_bank')])
    await query.edit_message_text(f"📁 <b>{lesson}</b>\n\nمبحث را انتخاب کنید:",
                                  parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _fb_files(query, context, lesson, topic):
    files = await db.get_qbank_files(lesson=lesson, topic=topic)
    if not files:
        await query.edit_message_text(
            f"📁 <b>{lesson}{' — '+topic if topic else ''}</b>\n\n❌ فایلی آپلود نشده.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='questions:file_bank')
            ]])); return
    keyboard = []
    for f in files:
        fid   = str(f['_id'])
        label = f"📥 {f.get('topic','')} | {f.get('description','')[:25]} | ⬇️{f.get('downloads',0)}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f'download_qbank:{fid}')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='questions:file_bank')])
    await query.edit_message_text(
        f"📁 <b>{lesson}{' — '+topic if topic else ''}</b>\n{len(files)} فایل:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════════════════
#  خروجی PDF
# ══════════════════════════════════════════════════════════

async def _pdf_menu(query, context):
    lessons = await db.get_lessons()
    if not lessons:
        await query.edit_message_text(
            "❌ هنوز سوالی موجود نیست.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='questions:main')
            ]])); return
    context.user_data['_pdf_lessons'] = lessons
    keyboard = []
    for i in range(0, len(lessons), 2):
        row = [InlineKeyboardButton(f"📚 {lessons[i]}", callback_data=f'questions:pdf_lesson:{i}')]
        if i+1 < len(lessons):
            row.append(InlineKeyboardButton(f"📚 {lessons[i+1]}", callback_data=f'questions:pdf_lesson:{i+1}'))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='questions:main')])
    await query.edit_message_text(
        "📄 <b>خروجی PDF سوالات</b>\n\n"
        "درس مورد نظر را انتخاب کنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _pdf_topic_select(query, context, lesson):
    topics = await db.get_topics(lesson)
    context.user_data['_pdf_topics'] = topics
    keyboard = [[InlineKeyboardButton(f"📌 {t}", callback_data=f'questions:pdf_topic_sel:{i}')]
                for i, t in enumerate(topics)]
    keyboard.append([InlineKeyboardButton("📂 همه مباحث", callback_data='questions:pdf_topic_sel:all')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='questions:pdf_menu')])
    await query.edit_message_text(f"📄 <b>{lesson}</b>\n\nمبحث را انتخاب کنید:",
                                  parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _pdf_count_select(query, context, lesson, topic):
    context.user_data['pdf_lesson'] = lesson
    context.user_data['pdf_topic']  = topic
    t_label = f" — {topic}" if topic != 'همه' else ''
    keyboard = [
        [InlineKeyboardButton("۱۰ سوال",  callback_data='questions:pdf_count:10'),
         InlineKeyboardButton("۲۰ سوال",  callback_data='questions:pdf_count:20')],
        [InlineKeyboardButton("۳۰ سوال",  callback_data='questions:pdf_count:30'),
         InlineKeyboardButton("۵۰ سوال",  callback_data='questions:pdf_count:50')],
        [InlineKeyboardButton("🔙 بازگشت", callback_data='questions:pdf_menu')],
    ]
    await query.edit_message_text(
        f"📄 <b>{lesson}{t_label}</b>\n\nتعداد سوالات PDF:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _generate_pdf(query, context, uid, lesson, topic, count):
    """ساخت PDF متنی از سوالات"""
    qs = await db.get_questions_for_pdf(lesson=lesson, topic=topic if topic != 'همه' else None, count=count)
    if not qs:
        await query.edit_message_text(
            "❌ سوالی برای این فیلتر پیدا نشد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='questions:pdf_menu')
            ]])); return

    # ساخت متن PDF ساده (txt با فرمت‌بندی)
    lines = []
    t_label = f" — {topic}" if topic and topic != 'همه' else ''
    lines.append(f"بانک سوال — {lesson}{t_label}")
    lines.append(f"تاریخ: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"تعداد سوالات: {len(qs)}")
    lines.append("=" * 50)
    lines.append("")

    for i, q in enumerate(qs, 1):
        diff = q.get('difficulty', '')
        lines.append(f"سوال {i} | {q.get('lesson','')} — {q.get('topic','')} | {diff}")
        lines.append("")
        lines.append(q['question'])
        lines.append("")
        for j, opt in enumerate(q.get('options', [])):
            marker = "✓" if j == q.get('correct_answer', 0) else " "
            lines.append(f"  {['الف','ب','ج','د'][j]}) {opt}  {marker}")
        expl = q.get('explanation', '')
        if expl:
            lines.append(f"  توضیح: {expl}")
        lines.append("-" * 40)
        lines.append("")

    text_content = "\n".join(lines)
    file_bytes   = text_content.encode('utf-8')
    file_obj     = io.BytesIO(file_bytes)
    fname        = f"qbank_{lesson}_{datetime.now().strftime('%Y%m%d')}.txt"
    file_obj.name = fname

    try:
        await query.message.reply_document(
            document=file_obj,
            caption=f"📄 <b>بانک سوال</b>\n📚 {lesson}{t_label}\n🔢 {len(qs)} سوال",
            parse_mode='HTML',
            filename=fname)
        await query.edit_message_text(
            f"✅ فایل سوالات ارسال شد!\n📚 {lesson}\n🔢 {len(qs)} سوال",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت به منو", callback_data='questions:main')
            ]]))
    except Exception as e:
        await query.edit_message_text(f"❌ خطا: {e}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='questions:main')
            ]]))


# ══════════════════════════════════════════════════════════
#  انتخاب درس/مبحث برای تمرین
# ══════════════════════════════════════════════════════════

async def _lesson_select(query, context, mode):
    lessons = await db.get_lessons()
    if not lessons:
        await query.edit_message_text("❌ هنوز سوالی موجود نیست.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='questions:practice')
            ]])); return
    context.user_data['_lessons'] = lessons
    keyboard = []
    for i in range(0, len(lessons), 2):
        row = [InlineKeyboardButton(f"📚 {lessons[i]}", callback_data=f'questions:sel_lesson:{mode}:{i}')]
        if i+1 < len(lessons):
            row.append(InlineKeyboardButton(f"📚 {lessons[i+1]}", callback_data=f'questions:sel_lesson:{mode}:{i+1}'))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='questions:practice')])
    label = "شبیه‌سازی امتحان" if mode == 'exam' else "تمرین آزاد"
    await query.edit_message_text(f"📚 <b>{label}</b>\n\nدرس را انتخاب کنید:",
                                  parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _topic_select(query, context, lesson, mode):
    topics = await db.get_topics(lesson)
    context.user_data['_topics'] = topics
    keyboard = [[InlineKeyboardButton(f"📌 {t}", callback_data=f'questions:sel_topic:{mode}:{i}')]
                for i, t in enumerate(topics)]
    keyboard.append([InlineKeyboardButton("📂 همه مباحث", callback_data=f'questions:sel_topic:{mode}:all')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f'questions:{"exam" if mode=="exam" else "free"}')])
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

    # تعداد سوالات طراحی شده توسط این کاربر
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
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 بازگشت", callback_data='questions:main')
        ]]))


# ══════════════════════════════════════════════════════════
#  طراحی سوال
# ══════════════════════════════════════════════════════════

async def _create_start(query, context):
    lessons = await db.get_lessons()
    if not lessons:
        await query.edit_message_text(
            "❌ هنوز درسی تعریف نشده.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='questions:main')
            ]])); return
    context.user_data['_lessons'] = lessons
    keyboard = []
    for i in range(0, len(lessons), 2):
        row = [InlineKeyboardButton(f"📚 {lessons[i]}", callback_data=f'questions:cr_lesson:{i}')]
        if i+1 < len(lessons):
            row.append(InlineKeyboardButton(f"📚 {lessons[i+1]}", callback_data=f'questions:cr_lesson:{i+1}'))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='questions:main')])
    is_ca = context.user_data.get('creating_as_ca', False)
    note  = "\n🤖 سوال شما با برچسب «طراحی توسط بات» ثبت می‌شود." if is_ca else \
            "\n⏳ سوال شما پس از تأیید ادمین در بانک قرار می‌گیرد."
    await query.edit_message_text(
        f"✏️ <b>طراحی سوال جدید</b>{note}\n\nدرس را انتخاب کنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _create_topic_select(query, context, lesson):
    topics = await db.get_topics(lesson)
    if not topics:
        # اگه مبحث نداشت، مستقیم به step سوال برو
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
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='questions:create')])
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
    uid  = update.effective_user.id
    q    = context.user_data.get('new_q', {})
    is_ca     = context.user_data.get('creating_as_ca', False)
    is_admin  = (uid == ADMIN_ID)
    auto      = is_ca or is_admin
    by_bot    = is_ca

    await db.questions.insert_one({
        'lesson':      q.get('lesson', ''),
        'topic':       q.get('topic', ''),
        'difficulty':  q.get('difficulty', 'متوسط 🟡'),
        'question':    q.get('question', ''),
        'options':     q.get('options', []),
        'correct_answer': q.get('correct', 0),
        'explanation': q.get('explanation', ''),
        'creator_id':  uid,
        'by_bot':      by_bot,
        'approved':    auto,
        'created_at':  datetime.now().isoformat(),
        'attempt_count': 0,
        'correct_count': 0,
    })

    for k in ['new_q', 'create_step', 'mode', 'cr_lesson', 'creating_as_ca']:
        context.user_data.pop(k, None)

    if auto:
        msg = "✅ <b>سوال با موفقیت در بانک سوال ثبت شد!</b>"
    else:
        msg = "✅ <b>سوال ارسال شد و در انتظار تأیید ادمین است.</b>\nپس از تأیید در بانک سوال نمایش داده می‌شود."

    await update.message.reply_text(msg, parse_mode='HTML')

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db

logger = logging.getLogger(__name__)
SEARCH = 3


async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    mode = context.user_data.pop('search_mode', 'resources')
    context.user_data.pop('awaiting_search', None)

    if mode == 'resources':
        results = await db.search_resources(text)
        if not results:
            await update.message.reply_text(f"🔍 نتیجه‌ای برای «{text}» پیدا نشد.")
            return ConversationHandler.END
        keyboard = []
        for r in results[:10]:
            rid = str(r['_id'])
            label = f"📄 {r.get('lesson','')} → {r.get('topic','')} | {r.get('type','')}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f'download_resource:{rid}')])
        await update.message.reply_text(
            f"🔍 <b>{len(results)} نتیجه برای «{text}»</b>",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif mode == 'add_question':
        await _add_question(update, context, text)

    elif mode == 'add_schedule':
        await _add_schedule(update, context, text)

    return ConversationHandler.END


async def _add_question(update, context, text):
    import os
    ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
    try:
        parts = [p.strip() for p in text.split('|')]
        if len(parts) < 9:
            raise ValueError("حداقل ۹ بخش لازم است")
        lesson, topic, difficulty, question = parts[0], parts[1], parts[2], parts[3]
        options = parts[4:8]
        correct = int(parts[8])
        if correct < 1 or correct > 4:
            raise ValueError("شماره جواب باید 1 تا 4 باشد")
        explanation = parts[9] if len(parts) > 9 else ''
        await db.add_question(lesson, topic, difficulty, question, options, correct, explanation, update.effective_user.id)
        await update.message.reply_text(
            f"✅ سوال اضافه شد و منتظر تأیید ادمین است.\n📌 {lesson} — {topic}"
        )
    except ValueError as e:
        await update.message.reply_text(
            f"❌ خطا: {e}\n\nفرمت صحیح:\n"
            "<code>درس|مبحث|سختی|سوال|گ۱|گ۲|گ۳|گ۴|جواب|توضیح</code>",
            parse_mode='HTML'
        )
    context.user_data.pop('mode', None)


async def _add_schedule(update, context, text):
    import os
    from datetime import datetime
    ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
    stype = context.user_data.pop('schedule_type', 'class')
    try:
        parts = [p.strip() for p in text.split(',')]
        if len(parts) < 5:
            raise ValueError("حداقل ۵ فیلد لازم است")
        lesson, teacher, date, time, location = parts[:5]
        notes = parts[5] if len(parts) > 5 else ''
        datetime.strptime(date, '%Y-%m-%d')
        await db.add_schedule(stype, lesson, teacher, date, time, location, notes)

        users = await db.notif_users('schedule' if stype != 'exam' else 'exam')
        count = 0
        for u in users:
            if u['user_id'] != ADMIN_ID:
                try:
                    type_fa = {'class': 'کلاس', 'exam': 'امتحان', 'makeup': 'جبرانی'}.get(stype, '')
                    await context.bot.send_message(u['user_id'],
                        f"📅 <b>{type_fa} جدید:</b> {lesson}\n👨‍🏫 {teacher} | {date} {time}",
                        parse_mode='HTML')
                    count += 1
                except: pass

        await update.message.reply_text(
            f"✅ برنامه اضافه شد!\n📌 {lesson} | {date} {time}\n🔔 {count} نفر مطلع شدند."
        )
    except ValueError as e:
        await update.message.reply_text(
            f"❌ خطا: {e}\nمثال: آناتومی, دکتر محمدی, 2024-03-20, 09:00, کلاس A2"
        )
    context.user_data.pop('mode', None)

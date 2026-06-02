"""🩺 ربات پزشکی — نسخه نهایی"""
import os, sys, logging, asyncio
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ConversationHandler
)

from start import (start_handler, register_start_callback,
                   step_name_handler,
                   REGISTER, STEP_NAME, STEP_GROUP)
from dashboard import dashboard_callback
from questions import (questions_callback, handle_question_answer, ANSWERING,
                       handle_create_question_steps, handle_difficulty_choice, CREATING_Q)
from schedule import schedule_callback
from stats import stats_callback
from notifications import notifications_callback
from admin import admin_callback, admin_broadcast_handler, upload_file_handler, BROADCAST
from backup import backup_callback, backup_file_handler, backup_confirm_restore
from utils import cancel_handler
from profile import profile_callback, profile_text_handler, PROFILE_EDIT_WAITING
from search import search_handler, SEARCH
from message_router import route_message
from basic_science import basic_science_callback
from references import references_callback
from content_admin import content_admin_callback, ca_file_handler, ca_text_handler, CA_WAITING_FILE, CA_WAITING_TEXT
from faq import faq_callback
from ticket import ticket_callback, ticket_message_handler, TICKET_WAITING, TICKET_REPLY_WAITING
from database import db

logging.basicConfig(format='%(asctime)s [%(levelname)s] %(name)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN    = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

if not TOKEN:
    logger.error("❌ TELEGRAM_TOKEN تنظیم نشده!")
    sys.exit(1)


async def send_exam_reminders(app):
    while True:
        now = datetime.now()
        next_run = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if now >= next_run:
            from datetime import timedelta
            next_run = next_run + timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        try:
            for days in [7, 3, 1]:
                exams = await db.get_exams_for_reminder(days)
                for exam in exams:
                    sid = str(exam['_id'])
                    day_text = {"1": "⚠️ فردا", "3": "📅 ۳ روز دیگر", "7": "📅 ۷ روز دیگر"}.get(str(days), f"{days} روز دیگر")
                    msg = (f"🔔 <b>یادآوری امتحان</b>\n\n"
                           f"📚 {exam.get('lesson','')}\n⏰ {day_text} — {exam.get('date','')} ساعت {exam.get('time','')}\n"
                           f"📍 {exam.get('location','')}\n👨‍🏫 {exam.get('teacher','')}")
                    users = await db.notif_users('exam')
                    sent = sum(1 for u in users if await _safe_send(app.bot, u['user_id'], msg))
                    if sent: await db.mark_exam_notified(sid, days)
        except Exception as e:
            logger.error(f"reminder error: {e}")
        await asyncio.sleep(3600)


async def _safe_send(bot, uid, msg):
    try:
        await bot.send_message(uid, msg, parse_mode='HTML')
        return True
    except:
        return False


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_handler),
            CallbackQueryHandler(questions_callback, pattern='^questions:cr_topic:'),
            CallbackQueryHandler(content_admin_callback, pattern='^ca:'),
        ],
        states={
            REGISTER:        [CallbackQueryHandler(register_start_callback, pattern="^register:")],
            STEP_NAME:       [MessageHandler(filters.TEXT & ~filters.COMMAND, step_name_handler),
                              CallbackQueryHandler(register_start_callback, pattern="^register:cancel")],
            STEP_GROUP:      [CallbackQueryHandler(register_start_callback, pattern="^register:(group1|group2|cancel)")],
            SEARCH:          [MessageHandler(filters.TEXT & ~filters.COMMAND, search_handler)],
            ANSWERING:       [CallbackQueryHandler(handle_question_answer, pattern='^answer:')],
            BROADCAST:       [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_handler)],
            CREATING_Q: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_create_question_steps),
                CallbackQueryHandler(handle_difficulty_choice, pattern='^qd:'),
                CallbackQueryHandler(questions_callback, pattern='^questions:'),
            ],
            CA_WAITING_FILE: [
                MessageHandler(filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.VOICE, ca_file_handler),
                CallbackQueryHandler(content_admin_callback, pattern='^ca:'),
                CommandHandler('cancel', cancel_handler),
            ],
            CA_WAITING_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ca_text_handler),
                CallbackQueryHandler(content_admin_callback, pattern='^ca:'),
                CommandHandler('cancel', cancel_handler),
            ],
            PROFILE_EDIT_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile_text_handler),
                CallbackQueryHandler(profile_callback, pattern='^profile:'),
                CommandHandler('cancel', cancel_handler),
            ],
            TICKET_WAITING:       [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_message_handler),
                                   CallbackQueryHandler(ticket_callback, pattern='^ticket:'),
                                   CommandHandler('cancel', cancel_handler)],
            TICKET_REPLY_WAITING: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_message_handler),
                                   CallbackQueryHandler(ticket_callback, pattern='^ticket:'),
                                   CommandHandler('cancel', cancel_handler)],
        },
        fallbacks=[
            CommandHandler('start', start_handler),
            CommandHandler('cancel', cancel_handler),
        ],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(conv)

    # ── ترتیب مهم است: specific اول، general بعد ──
    app.add_handler(CallbackQueryHandler(profile_callback, pattern='^profile:'))
    app.add_handler(CallbackQueryHandler(basic_science_callback, pattern='^bs[_:]'))
    app.add_handler(CallbackQueryHandler(references_callback,    pattern='^ref[_:]'))
    app.add_handler(CallbackQueryHandler(route_resources,        pattern='^resources:menu'))
    app.add_handler(CallbackQueryHandler(dashboard_callback,     pattern='^dashboard'))
    app.add_handler(CallbackQueryHandler(questions_callback,     pattern='^(questions|answer:|download_qbank:)'))
    app.add_handler(CallbackQueryHandler(schedule_callback,      pattern='^schedule'))
    app.add_handler(CallbackQueryHandler(stats_callback,         pattern='^stats'))
    app.add_handler(CallbackQueryHandler(notifications_callback, pattern='^notif'))
    app.add_handler(CallbackQueryHandler(admin_callback,         pattern='^admin'))
    app.add_handler(CallbackQueryHandler(backup_callback,        pattern='^backup:(?!confirm_restore)'))
    app.add_handler(CallbackQueryHandler(backup_confirm_restore, pattern='^backup:confirm_restore'))
    app.add_handler(CallbackQueryHandler(faq_callback,           pattern='^faq:'))
    app.add_handler(CallbackQueryHandler(content_admin_callback, pattern='^ca:'))
    app.add_handler(CallbackQueryHandler(ticket_callback,        pattern='^ticket:'))
    # resources:bs و resources:ref باید قبل از resources: عمومی باشن
    app.add_handler(CallbackQueryHandler(basic_science_callback, pattern='^resources:bs'))
    app.add_handler(CallbackQueryHandler(references_callback,    pattern='^resources:ref'))
    app.add_handler(CallbackQueryHandler(route_resources,        pattern='^resources'))

    async def unified_file_handler(update, context):
        uid = update.effective_user.id
        if uid == ADMIN_ID and context.user_data.get('backup_mode') == 'waiting_restore':
            return await backup_file_handler(update, context)
        if context.user_data.get('ca_mode') in ('waiting_file', 'waiting_ref_file') and await db.is_content_admin(uid):
            return await ca_file_handler(update, context)

    async def unified_text_handler(update, context):
        """هندلر متن خارج از conversation — برای ca_mode های آپلود رفرنس"""
        uid     = update.effective_user.id
        ca_mode = context.user_data.get('ca_mode', '')
        if ca_mode in ('waiting_ref_description',) and await db.is_content_admin(uid):
            return await ca_text_handler(update, context)
        # بقیه پیام‌ها به route_message برن
        return await route_message(update, context)

    app.add_handler(MessageHandler(
        filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.VOICE,
        unified_file_handler
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unified_text_handler))

    async def post_init(application):
        asyncio.create_task(send_exam_reminders(application))
    app.post_init = post_init

    logger.info("🩺 ربات پزشکی شروع به کار کرد...")
    app.run_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query"])


async def route_resources(update, context):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🔬 علوم پایه", callback_data='bs:main')],
        [InlineKeyboardButton("📖 رفرنس‌ها",  callback_data='ref:main')],
    ]
    await query.edit_message_text(
        "📚 <b>منابع درسی</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🔬 <b>علوم پایه:</b> محتوای جلسات (ویدیو، جزوه، پاورپوینت و...)\n"
        "📖 <b>رفرنس‌ها:</b> کتاب‌های مرجع (PDF فارسی/لاتین)",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


if __name__ == '__main__':
    main()

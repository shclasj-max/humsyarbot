"""
🩺 ربات پزشکی — نسخه بهینه‌شده
  ✅ سازگار با python-telegram-bot 21.x (آخرین)
  ✅ job_queue برای یادآوری‌ها (به‌جای asyncio.sleep loop)
  ✅ Application.post_init برای ایجاد ایندکس‌ها
  ✅ error_handler مرکزی
  ✅ allowed_updates دقیق
"""
import os
import sys
import logging
import asyncio
from datetime import datetime, time as dtime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler,
    filters, ContextTypes, Application
)

# ── ایمپورت ماژول‌ها ──
from start import (
    start_handler, register_start_callback, step_name_handler,
    REGISTER, STEP_NAME, STEP_GROUP
)
from dashboard import dashboard_callback
from questions import (
    questions_callback, handle_question_answer,
    handle_create_question_steps, handle_difficulty_choice,
    ANSWERING, CREATING_Q
)
from schedule import schedule_callback
from stats import stats_callback
from notifications import notifications_callback
from admin import (
    admin_callback, admin_broadcast_handler, upload_file_handler,
    handle_admin_text, BROADCAST
)
from backup import backup_callback, backup_file_handler, backup_confirm_restore
from utils import cancel_handler, ADMIN_ID
from profile import profile_callback, profile_text_handler, PROFILE_EDIT_WAITING
from message_router import route_message
from basic_science import basic_science_callback
from references import references_callback
from content_admin import (
    content_admin_callback, ca_file_handler, ca_text_handler,
    CA_WAITING_FILE, CA_WAITING_TEXT
)
from faq import faq_callback
from ticket import ticket_callback, ticket_message_handler, TICKET_WAITING, TICKET_REPLY_WAITING
from database import db

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
# کاهش لاگ‌های پرسروصدای خارجی
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error("❌ TELEGRAM_TOKEN تنظیم نشده!")
    sys.exit(1)


# ══════════════════════════════════════════════════
#  Job: یادآوری امتحانات (هر روز ساعت ۸ صبح)
# ══════════════════════════════════════════════════

async def exam_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """Job Queue یادآوری — هر روز ۰۸:۰۰ اجرا می‌شه"""
    logger.info("🔔 اجرای job یادآوری امتحان...")
    day_labels = {1: "⚠️ فردا", 3: "📅 ۳ روز دیگر", 7: "📅 ۷ روز دیگر"}
    try:
        for days, label in day_labels.items():
            exams = await db.get_exams_for_reminder(days)
            for exam in exams:
                sid = str(exam['_id'])
                msg = (
                    f"🔔 <b>یادآوری امتحان</b>\n\n"
                    f"📚 {exam.get('lesson', '')}\n"
                    f"⏰ {label} — {exam.get('date', '')} ساعت {exam.get('time', '')}\n"
                    f"📍 {exam.get('location', '')}\n"
                    f"👨‍🏫 {exam.get('teacher', '')}"
                )
                users = await db.notif_users('exam')
                sent = 0
                for u in users:
                    try:
                        await context.bot.send_message(
                            u['user_id'], msg, parse_mode='HTML'
                        )
                        sent += 1
                        await asyncio.sleep(0.05)  # جلوگیری از flood
                    except Exception:
                        pass
                if sent:
                    await db.mark_exam_notified(sid, days)
                    logger.info(f"امتحان {exam.get('lesson')} — {sent} نفر مطلع شدند")
    except Exception as e:
        logger.error(f"exam_reminder_job error: {e}")


async def daily_question_job(context: ContextTypes.DEFAULT_TYPE):
    """Job: ارسال سوال روزانه — هر روز ۰۹:۰۰"""
    try:
        questions = await db.get_questions(limit=1)
        if not questions:
            return
        q = questions[0]
        opts = q.get('options', [])
        letters = ['🅐', '🅑', '🅒', '🅓']
        opts_text = '\n'.join(
            f"{letters[i]} {opt}" for i, opt in enumerate(opts)
        )
        text = (
            f"🧪 <b>سوال روزانه</b>\n\n"
            f"📚 {q.get('lesson', '')} — {q.get('topic', '')}\n\n"
            f"❓ {q.get('question', '')}\n\n"
            f"{opts_text}\n\n"
            f"<i>برای تمرین بیشتر: بانک سوال</i>"
        )
        users = await db.notif_users('daily_question')
        for u in users:
            try:
                await context.bot.send_message(u['user_id'], text, parse_mode='HTML')
                await asyncio.sleep(0.05)
            except Exception:
                pass
    except Exception as e:
        logger.error(f"daily_question_job error: {e}")


# ══════════════════════════════════════════════════
#  Error Handler مرکزی
# ══════════════════════════════════════════════════

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=context.error)
    # گزارش خطا به ادمین
    if ADMIN_ID:
        try:
            err_text = f"⚠️ <b>خطای ربات</b>\n<code>{str(context.error)[:300]}</code>"
            await context.bot.send_message(ADMIN_ID, err_text, parse_mode='HTML')
        except Exception:
            pass


# ══════════════════════════════════════════════════
#  هندلرهای file/text یکپارچه
# ══════════════════════════════════════════════════

async def unified_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # ۱. بکاپ restore
    if uid == ADMIN_ID and context.user_data.get('backup_mode') == 'waiting_restore':
        return await backup_file_handler(update, context)
    # ۲. آپلود محتوا
    ca_mode = context.user_data.get('ca_mode', '')
    if ca_mode in ('waiting_file', 'waiting_ref_file') and await db.is_content_admin(uid):
        return await ca_file_handler(update, context)
    # ۳. آپلود فایل ادمین
    if uid == ADMIN_ID and context.user_data.get('mode') == 'upload_file':
        return await upload_file_handler(update, context)


async def unified_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ca_mode = context.user_data.get('ca_mode', '')
    # محتوا ادمین — توضیحات رفرنس
    if ca_mode == 'waiting_ref_description' and await db.is_content_admin(uid):
        return await ca_text_handler(update, context)
    return await route_message(update, context)


# ══════════════════════════════════════════════════
#  منوی منابع (inline)
# ══════════════════════════════════════════════════

async def route_resources(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ══════════════════════════════════════════════════
#  ساخت Application و ثبت هندلرها
# ══════════════════════════════════════════════════

def build_application() -> Application:
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .concurrent_updates(True)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(15)
        .pool_timeout(15)
        .build()
    )

    # ── ConversationHandler مرکزی ──
    conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_handler),
            CallbackQueryHandler(questions_callback,   pattern=r'^questions:cr_topic:'),
            CallbackQueryHandler(content_admin_callback, pattern=r'^ca:'),
        ],
        states={
            REGISTER: [
                CallbackQueryHandler(register_start_callback, pattern=r'^register:')
            ],
            STEP_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step_name_handler),
                CallbackQueryHandler(register_start_callback, pattern=r'^register:cancel'),
            ],
            STEP_GROUP: [
                CallbackQueryHandler(register_start_callback, pattern=r'^register:(group1|group2|cancel)')
            ],
            ANSWERING: [
                CallbackQueryHandler(handle_question_answer, pattern=r'^answer:')
            ],
            BROADCAST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_handler)
            ],
            CREATING_Q: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_create_question_steps),
                CallbackQueryHandler(handle_difficulty_choice, pattern=r'^qd:'),
                CallbackQueryHandler(questions_callback, pattern=r'^questions:'),
            ],
            CA_WAITING_FILE: [
                MessageHandler(
                    filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.VOICE,
                    ca_file_handler
                ),
                CallbackQueryHandler(content_admin_callback, pattern=r'^ca:'),
                CommandHandler('cancel', cancel_handler),
            ],
            CA_WAITING_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ca_text_handler),
                CallbackQueryHandler(content_admin_callback, pattern=r'^ca:'),
                CommandHandler('cancel', cancel_handler),
            ],
            PROFILE_EDIT_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile_text_handler),
                CallbackQueryHandler(profile_callback, pattern=r'^profile:'),
                CommandHandler('cancel', cancel_handler),
            ],
            TICKET_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_message_handler),
                CallbackQueryHandler(ticket_callback, pattern=r'^ticket:'),
                CommandHandler('cancel', cancel_handler),
            ],
            TICKET_REPLY_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_message_handler),
                CallbackQueryHandler(ticket_callback, pattern=r'^ticket:'),
                CommandHandler('cancel', cancel_handler),
            ],
        },
        fallbacks=[
            CommandHandler('start', start_handler),
            CommandHandler('cancel', cancel_handler),
        ],
        allow_reentry=True,
        per_message=False,
        # timeout برای conversation — ۳۰ دقیقه بی‌فعالیت
        conversation_timeout=1800,
    )
    app.add_handler(conv)

    # ── Callback handlers — ترتیب مهم است: specific قبل از general ──
    cbs = [
        (profile_callback,          r'^profile:'),
        (basic_science_callback,    r'^bs[_:]'),
        (basic_science_callback,    r'^resources:bs'),
        (references_callback,       r'^ref[_:]'),
        (references_callback,       r'^resources:ref'),
        (route_resources,           r'^resources:menu'),
        (route_resources,           r'^resources'),
        (dashboard_callback,        r'^dashboard'),
        (questions_callback,        r'^(questions|answer:|download_qbank:)'),
        (schedule_callback,         r'^schedule'),
        (stats_callback,            r'^stats'),
        (notifications_callback,    r'^notif'),
        (admin_callback,            r'^admin'),
        (backup_confirm_restore,    r'^backup:confirm_restore'),
        (backup_callback,           r'^backup:'),
        (faq_callback,              r'^faq:'),
        (content_admin_callback,    r'^ca:'),
        (ticket_callback,           r'^ticket:'),
    ]
    for handler, pattern in cbs:
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern))

    # ── File و Text handlers ──
    app.add_handler(MessageHandler(
        filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.VOICE,
        unified_file_handler
    ))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        unified_text_handler
    ))

    # ── Error handler ──
    app.add_error_handler(error_handler)

    return app


# ══════════════════════════════════════════════════
#  post_init: ایجاد ایندکس‌ها + ثبت jobها
# ══════════════════════════════════════════════════

async def post_init(application: Application):
    # ایجاد ایندکس‌های MongoDB
    await db.ensure_indexes()
    logger.info("✅ ایندکس‌های دیتابیس آماده شدند")

    # ثبت jobهای زمان‌بندی — فقط اگر job_queue فعال باشد
    if application.job_queue is not None:
        reminder_time = dtime(hour=4, minute=30, tzinfo=timezone.utc)
        application.job_queue.run_daily(
            exam_reminder_job,
            time=reminder_time,
            name='exam_reminder'
        )
        daily_q_time = dtime(hour=5, minute=30, tzinfo=timezone.utc)
        application.job_queue.run_daily(
            daily_question_job,
            time=daily_q_time,
            name='daily_question'
        )
        logger.info("✅ Job‌های زمان‌بندی ثبت شدند")
    else:
        logger.warning("⚠️ JobQueue فعال نیست — یادآوری‌های زمان‌بندی غیرفعال هستند")
        logger.warning("   برای فعال‌سازی: pip install \"python-telegram-bot[job-queue]\"")


def main():
    app = build_application()
    app.post_init = post_init

    logger.info("🩺 ربات پزشکی شروع به کار کرد...")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
        poll_interval=0.5,
    )


if __name__ == '__main__':
    main()

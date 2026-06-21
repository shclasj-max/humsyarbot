"""
🩺 ربات پزشکی — نسخه نهایی کامل
  ✅ broadcast کاملاً خارج از ConversationHandler
  ✅ unified_file/text_handler با broadcast + qbank
  ✅ job_queue برای یادآوری‌ها
  ✅ error_handler مرکزی با گزارش به ادمین
  ✅ سازگار با python-telegram-bot 21.x
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
    filters, ContextTypes, Application, TypeHandler,
    ApplicationHandlerStop
)

# ── ایمپورت ماژول‌ها ──
from start import (
    start_handler, register_start_callback, step_name_handler,
    register_intake_callback, step_student_id_handler,
    REGISTER, STEP_NAME, STEP_GROUP, STEP_INTAKE, STEP_STUDENT_ID
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
from utils import cancel_handler, ADMIN_ID, is_maintenance_on, maintenance_message, send_audit_log
from profile import profile_callback, profile_text_handler, PROFILE_EDIT_WAITING
from message_router import route_message
from basic_science import basic_science_callback
from resources import resources_callback
from references import references_callback
from content_admin import (
    content_admin_callback, ca_file_handler, ca_text_handler,
    CA_WAITING_FILE, CA_WAITING_TEXT
)
from faq import faq_callback
from ticket import (
    ticket_callback, ticket_message_handler,
    TICKET_WAITING, TICKET_REPLY_WAITING
)
from database import db

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    logger.error("❌ TELEGRAM_TOKEN تنظیم نشده!")
    sys.exit(1)


# ══════════════════════════════════════════════════
#  Job: یادآوری امتحانات — هر روز ۰۸:۰۰ تهران
# ══════════════════════════════════════════════════

async def exam_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("🔔 اجرای job یادآوری امتحان...")
    day_labels = {1: "⚠️ فردا امتحان دارید!", 3: "📅 ۳ روز دیگر", 7: "📅 ۷ روز دیگر"}
    try:
        for days, label in day_labels.items():
            exams = await db.get_exams_for_reminder(days)
            for exam in exams:
                sid = str(exam['_id'])
                msg = (
                    f"🔔 <b>یادآوری امتحان</b>\n\n"
                    f"📚 <b>{exam.get('lesson', '')}</b>\n"
                    f"⏰ {label}\n"
                    f"📅 تاریخ: {exam.get('date', '')}  ساعت {exam.get('time', '')}\n"
                    f"📍 مکان: {exam.get('location', '')}\n"
                    f"👨‍🏫 استاد: {exam.get('teacher', '')}"
                )
                users = await db.notif_users('exam')
                sent  = 0
                for u in users:
                    try:
                        await context.bot.send_message(u['user_id'], msg, parse_mode='HTML')
                        sent += 1
                        await asyncio.sleep(0.05)
                    except Exception:
                        pass
                if sent:
                    await db.mark_exam_notified(sid, days)
                    logger.info(f"امتحان {exam.get('lesson')} — {sent} نفر مطلع شدند")
    except Exception as e:
        logger.error(f"exam_reminder_job error: {e}")


async def daily_question_job(context: ContextTypes.DEFAULT_TYPE):
    """Job: سوال روزانه — هر روز ۰۹:۰۰ تهران"""
    try:
        questions = await db.get_questions(limit=1)
        if not questions:
            return
        q       = questions[0]
        opts    = q.get('options', [])
        letters = ['🅐', '🅑', '🅒', '🅓']
        opts_text = '\n'.join(
            f"{letters[i]} {opt}" for i, opt in enumerate(opts)
        )
        text = (
            f"🧪 <b>سوال روزانه</b>\n\n"
            f"📚 {q.get('lesson', '')} — {q.get('topic', '')}\n\n"
            f"❓ {q.get('question', '')}\n\n"
            f"{opts_text}\n\n"
            f"<i>برای تمرین بیشتر از بانک سوال استفاده کنید 👇</i>"
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


async def weekly_report_job(context: ContextTypes.DEFAULT_TYPE):
    """
    FIX جدید: گزارش هفتگی خودکار — هر یکشنبه برای ادمین ارشد
    (و در صورت ست بودن، گروه لاگ ادمین) ارسال می‌شود.
    """
    logger.info("📊 اجرای job گزارش هفتگی...")
    try:
        s = await db.weekly_report_stats()
        text = (
            "📊 <b>گزارش هفتگی ربات</b>\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"👥 کاربران جدید این هفته: <b>{s['new_users']}</b>\n"
            f"👤 کل کاربران تأییدشده: <b>{s['total_users']}</b>\n"
            f"🟢 کاربران فعال این هفته: <b>{s['active_users_count']}</b>\n"
            f"😴 کاربران غیرفعال (۱۴+ روز): <b>{s['inactive_count']}</b>\n\n"
            f"📚 پرطرفدارترین درس هفته: <b>{s['top_lesson']}</b>\n\n"
            f"🎫 تیکت باز فعلی: <b>{s['open_tickets']}</b>\n"
            f"✅ تیکت بسته‌شده این هفته: <b>{s['closed_week']}</b>\n"
            f"📨 کل تیکت‌های این هفته: <b>{s['total_tickets_week']}</b>\n\n"
            "<i>گزارش بعدی: یکشنبه آینده 🗓</i>"
        )
        # همیشه برای ادمین ارشد
        try:
            await context.bot.send_message(ADMIN_ID, text, parse_mode='HTML')
        except Exception:
            pass
        # اگه گروه لاگ ادمین ست شده، آنجا هم بفرست
        chat_id = await db.get_setting('log_group_admin', None)
        if chat_id:
            try:
                await context.bot.send_message(int(chat_id), text, parse_mode='HTML')
            except Exception:
                pass
    except Exception as e:
        logger.error(f"weekly_report_job error: {e}")


# ══════════════════════════════════════════════════
#  Error Handler مرکزی
# ══════════════════════════════════════════════════

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=context.error)
    if ADMIN_ID:
        try:
            uid_info = ""
            if isinstance(update, Update) and update.effective_user:
                u = update.effective_user
                uid_info = f"\n👤 کاربر: {u.full_name} | آیدی: {u.id}"
            err_text = (
                f"⚠️ <b>خطای ربات</b>{uid_info}\n"
                f"<code>{str(context.error)[:300]}</code>"
            )
            await context.bot.send_message(ADMIN_ID, err_text, parse_mode='HTML')
        except Exception:
            pass


# ══════════════════════════════════════════════════
#  هندلرهای یکپارچه — FIX کامل
# ══════════════════════════════════════════════════

async def unified_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # ۱. بکاپ restore
    if uid == ADMIN_ID and context.user_data.get('backup_mode') == 'waiting_restore':
        return await backup_file_handler(update, context)

    # ۲. FIX: broadcast — عکس/ویدیو/فایل در حالت broadcast
    if uid == ADMIN_ID and context.user_data.get('mode') == 'broadcast':
        return await admin_broadcast_handler(update, context)

    # ۳. FIX: qbank file upload
    if uid == ADMIN_ID and context.user_data.get('mode') in ('qbank_awaiting_file', 'upload_file'):
        return await upload_file_handler(update, context)

    # ۴. محتوا ادمین
    ca_mode = context.user_data.get('ca_mode', '')
    if ca_mode in ('waiting_file', 'waiting_ref_file') and await db.is_content_admin(uid):
        return await ca_file_handler(update, context)


async def maintenance_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FIX جدید: حالت تعمیر و نگهداری — اجرا می‌شود با group=-1 یعنی
    قبل از همه‌ی handlerهای دیگر (پیام و callback). اگر maintenance
    فعال باشد و کاربر ادمین ارشد نباشد، پیام تعمیر نشان داده می‌شود
    و با ApplicationHandlerStop از اجرای ادامه‌ی handlerها جلوگیری
    می‌شود — بدون نیاز به لمس کردن ده‌ها تابع callback موجود.
    """
    uid = update.effective_user.id if update.effective_user else None
    if uid is None or uid == ADMIN_ID:
        return  # ادمین ارشد همیشه دسترسی کامل دارد

    if not await is_maintenance_on():
        return

    msg = await maintenance_message()
    try:
        if update.callback_query:
            await update.callback_query.answer("🔧 ربات در حال بروزرسانی است", show_alert=True)
        elif update.message:
            await update.message.reply_text(msg, parse_mode='HTML')
    except Exception:
        pass
    raise ApplicationHandlerStop


async def update_last_active(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FIX جدید: برای گزارش هفتگی نیاز داریم بدانیم آخرین فعالیت هر
    کاربر کِی بوده. با group=-1 (قبل از همه چیز) فقط یک فیلد آپدیت
    می‌شود — سبک و بدون اثر جانبی روی منطق دیگر.
    """
    uid = update.effective_user.id if update.effective_user else None
    if uid is None:
        return
    try:
        from database import db
        await db.users.update_one(
            {'user_id': uid},
            {'$set': {'last_active': datetime.now().isoformat()}}
        )
    except Exception:
        pass


async def unified_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # ۱. FIX: broadcast — باید اول از همه چک بشه
    if uid == ADMIN_ID and context.user_data.get('mode') == 'broadcast':
        return await admin_broadcast_handler(update, context)

    # ۲. FIX: profile_edit — ویرایش نام/شماره دانشجویی (هر کاربری)
    if context.user_data.get('mode') == 'profile_edit':
        from profile import profile_text_handler
        return await profile_text_handler(update, context)

    # ۳. FIX: search_user ادمین
    if uid == ADMIN_ID and context.user_data.get('mode') == 'search_user':
        return await handle_admin_text(update, context)

    # ۳. FIX: edit_user ادمین
    if uid == ADMIN_ID and context.user_data.get('mode') == 'edit_user':
        return await handle_admin_text(update, context)

    # ۴. FIX: add_intake ادمین
    if uid == ADMIN_ID and context.user_data.get('mode') == 'add_intake':
        return await handle_admin_text(update, context)

    # ۴b. FIX جدید: add_admin_role — افزودن نقش فرعی (فقط مدیر ارشد)
    if uid == ADMIN_ID and context.user_data.get('mode') == 'add_admin_role':
        return await handle_admin_text(update, context)

    # ۴c. FIX جدید: تنظیمات ربات — متن تعمیر و گروه‌های لاگ (فقط مدیر ارشد)
    if uid == ADMIN_ID and context.user_data.get('mode') in (
        'set_maintenance_text', 'set_log_group_admin', 'set_log_group_content'
    ):
        return await handle_admin_text(update, context)

    # ۵. FIX: qbank_awaiting_desc
    if uid == ADMIN_ID and context.user_data.get('mode') == 'qbank_awaiting_desc':
        return await handle_admin_text(update, context)

    # ۵b. FIX: add_schedule — افزودن برنامه کلاسی/امتحان (باگ: قبلاً هیچ‌جا چک نمی‌شد)
    if context.user_data.get('mode') == 'add_schedule':
        from schedule import handle_add_schedule_text
        return await handle_add_schedule_text(update, context)

    # ۶. ca_text_handler
    ca_mode = context.user_data.get('ca_mode', '')
    ca_text_modes = {
        'add_lesson', 'add_session', 'waiting_description',
        'waiting_ref_description', 'add_faq', 'add_ref_subject',
        'add_ref_book', 'edit_lesson', 'edit_session',
        'edit_ref_subject', 'edit_ref_book',
    }
    if ca_mode in ca_text_modes and await db.is_content_admin(uid):
        return await ca_text_handler(update, context)

    # ۷. ticket mode — شامل user_reply و admin_search هم هست
    if context.user_data.get('ticket_mode') in (
        'waiting_message', 'admin_reply', 'user_reply',
        'admin_search', 'awaiting_confirm'
    ):
        return await ticket_message_handler(update, context)

    # ۷b. ticket_search mode برای ادمین
    if uid == ADMIN_ID and context.user_data.get('mode') == 'ticket_search':
        return await ticket_message_handler(update, context)

    # ۸. روتر اصلی
    return await route_message(update, context)


# ══════════════════════════════════════════════════
#  منوی منابع
# ══════════════════════════════════════════════════

async def route_resources(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🔬 علوم پایه", callback_data='bs:main')],
        [InlineKeyboardButton("📖 رفرنس‌ها",  callback_data='ref:main')],
        [InlineKeyboardButton("🔙 بازگشت",    callback_data='dashboard:refresh')],
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
#  ساخت Application
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
    # NOTE: BROADCAST از اینجا حذف شد — در unified_text_handler مدیریت میشه
    conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_handler),
            CallbackQueryHandler(questions_callback,      pattern=r'^questions:cr_topic:'),
            CallbackQueryHandler(content_admin_callback,  pattern=r'^ca:'),
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
                CallbackQueryHandler(
                    register_start_callback,
                    pattern=r'^register:(group1|group2|cancel)'
                )
            ],
            STEP_INTAKE: [
                CallbackQueryHandler(register_intake_callback, pattern=r'^register:intake:')
            ],
            STEP_STUDENT_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, step_student_id_handler),
            ],
            ANSWERING: [
                CallbackQueryHandler(handle_question_answer, pattern=r'^answer:')
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
        conversation_timeout=1800,
    )
    # ── FIX جدید: maintenance gate + last_active — قبل از همه چیز (group=-1) ──
    app.add_handler(TypeHandler(Update, maintenance_gate), group=-1)
    app.add_handler(TypeHandler(Update, update_last_active), group=-1)

    app.add_handler(conv)

    # ── Callback handlers — ترتیب مهم: specific قبل از general ──
    cbs = [
        # پروفایل
        (profile_callback,         r'^profile:'),
        # علوم پایه
        (basic_science_callback,   r'^bs[_:]'),
        (basic_science_callback,   r'^bs_dl:'),
        (basic_science_callback,   r'^resources:bs'),
        # رفرنس‌ها
        (references_callback,      r'^ref[_:]'),
        (references_callback,      r'^resources:ref'),
        # منابع
        (route_resources,          r'^resources:menu'),
        (resources_callback,       r'^download_resource:'),
        (route_resources,          r'^resources:'),
        # داشبورد
        (dashboard_callback,       r'^dashboard'),
        # سوالات
        (questions_callback,       r'^(questions|answer:|download_qbank:)'),
        # بقیه
        (schedule_callback,        r'^schedule'),
        (stats_callback,           r'^stats'),
        (notifications_callback,   r'^notif'),
        (admin_callback,           r'^admin'),
        (backup_confirm_restore,   r'^backup:confirm_restore$'),
        (backup_callback,          r'^backup:'),
        (faq_callback,             r'^faq:'),
        (content_admin_callback,   r'^ca:'),
        (ticket_callback,          r'^ticket:'),
    ]
    for handler, pattern in cbs:
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern))

    # ── File handler — همه انواع فایل ──
    app.add_handler(MessageHandler(
        filters.Document.ALL | filters.VIDEO | filters.AUDIO |
        filters.VOICE | filters.PHOTO,
        unified_file_handler
    ))

    # ── Text handler ──
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        unified_text_handler
    ))

    # ── Error handler ──
    app.add_error_handler(error_handler)

    return app


# ══════════════════════════════════════════════════
#  post_init: ایندکس‌ها + job‌ها
# ══════════════════════════════════════════════════

async def post_init(application: Application):
    await db.ensure_indexes()
    logger.info("✅ ایندکس‌های دیتابیس آماده شدند")

    # FIX: گارد ایمن — اگر JobQueue نصب نباشد، ربات کرش نکند
    if application.job_queue is not None:
        # یادآوری امتحان — ۰۸:۰۰ تهران (04:30 UTC)
        application.job_queue.run_daily(
            exam_reminder_job,
            time=dtime(hour=4, minute=30, tzinfo=timezone.utc),
            name='exam_reminder'
        )

        # سوال روزانه — ۰۹:۰۰ تهران (05:30 UTC)
        application.job_queue.run_daily(
            daily_question_job,
            time=dtime(hour=5, minute=30, tzinfo=timezone.utc),
            name='daily_question'
        )

        # FIX جدید: گزارش هفتگی — یکشنبه‌ها ۰۹:۳۰ تهران (06:00 UTC)
        # نکته: در PTB days=(0,) یعنی یکشنبه (0=sunday...6=saturday)
        application.job_queue.run_daily(
            weekly_report_job,
            time=dtime(hour=6, minute=0, tzinfo=timezone.utc),
            days=(0,),
            name='weekly_report'
        )

        logger.info("✅ Job‌های زمان‌بندی ثبت شدند")
    else:
        logger.warning("⚠️ JobQueue فعال نیست — یادآوری‌ها و گزارش هفتگی غیرفعال هستند")
        logger.warning('   نصب با: pip install "python-telegram-bot[job-queue]"')


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

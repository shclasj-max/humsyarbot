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
from datetime import datetime, time as dtime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
from reports import report_callback, handle_report_note_text   # FIX جدید
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
    """
    FIX جدید: لاگ کامل وضعیت ارسال در notif_runs برای پایش و retry.
    ضد-تکرار از قبل با mark_exam_notified/notified_days درست بود — حفظ شد.
    """
    logger.info("🔔 اجرای job یادآوری امتحان...")
    run_id = await db.notif_run_start('exam_reminder')
    total_sent, total_failed, total_targets = 0, 0, 0
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
                    f"👨‍🏫 استاد: {exam.get('teacher', '')}\n\n"
                    f"<i>⚙️ خاموش‌کردن: 🔔 اعلان‌ها ← یادآوری امتحان</i>"
                )
                users = await db.notif_users('exam')
                sent  = 0
                total_targets += len(users)
                for u in users:
                    try:
                        await context.bot.send_message(u['user_id'], msg, parse_mode='HTML')
                        sent += 1
                        await asyncio.sleep(0.05)
                    except Exception:
                        total_failed += 1
                total_sent += sent
                if sent:
                    await db.mark_exam_notified(sid, days)
                    logger.info(f"امتحان {exam.get('lesson')} — {sent} نفر مطلع شدند")
        await db.notif_run_finish(run_id, total_sent, total_failed, total_targets)
    except Exception as e:
        logger.error(f"exam_reminder_job error: {e}")
        await db.notif_run_finish(run_id, total_sent, total_failed, total_targets,
                                   status='error', error=str(e))


async def daily_question_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Job: سوال روزانه — هر روز ۰۹:۰۰ تهران.
    FIX باگ قبلی: همیشه یک سوال ثابت می‌فرستاد. حالا با چرخش
    (get_daily_rotation_question) واقعاً هر روز سوال عوض می‌شود.
    FIX جدید: وضعیت ارسال در notif_runs ثبت می‌شود تا قابل پایش
    و retry باشد.
    """
    run_id = await db.notif_run_start('daily_question')
    sent, failed = 0, 0
    failed_ids = []
    try:
        q = await db.get_daily_rotation_question()
        if not q:
            await db.notif_run_finish(run_id, 0, 0, 0, status='skipped', error='no questions')
            return
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
            f"<i>برای تمرین بیشتر از بانک سوال استفاده کنید 👇</i>\n"
            f"<i>⚙️ خاموش‌کردن: 🔔 اعلان‌ها ← سوال روزانه</i>"
        )
        users = await db.notif_users('daily_question')
        for u in users:
            try:
                await context.bot.send_message(u['user_id'], text, parse_mode='HTML')
                sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                failed += 1
                failed_ids.append(u['user_id'])
        await db.notif_run_finish(run_id, sent, failed, len(users))
        if failed_ids:
            await db.notif_run_add_failed(run_id, failed_ids)
    except Exception as e:
        logger.error(f"daily_question_job error: {e}")
        await db.notif_run_finish(run_id, sent, failed, sent + failed, status='error', error=str(e))


async def new_resources_notif_job(context: ContextTypes.DEFAULT_TYPE):
    """
    FIX جدید: نوتیف دسته‌ای منابع جدید — این job هر ساعت اجرا می‌شود
    اما فقط وقتی واقعاً کار می‌کند که از آخرین ارسال، فاصله‌ی تعیین‌شده
    در تنظیمات (پیش‌فرض ۲۴ ساعت، قابل تغییر به ۴۸/۷۲ از پنل ادمین)
    گذشته باشد. این از ارسال تکراری/ناقص جلوگیری می‌کند.
    """
    try:
        interval_hours = await db.get_setting('resource_notif_interval_hours', 24)
        last_sent_str  = await db.get_setting('resource_notif_last_sent', None)

        if last_sent_str:
            last_sent = datetime.fromisoformat(last_sent_str)
            elapsed_hours = (datetime.now() - last_sent).total_seconds() / 3600
            if elapsed_hours < interval_hours:
                return  # هنوز وقتش نشده

        new_items = await db.get_unnotified_resources()
        if not new_items:
            # حتی اگه چیزی نبود، last_sent را آپدیت نمی‌کنیم — منتظر محتوای واقعی می‌مانیم
            return

        run_id = await db.notif_run_start('new_resources')

        # FIX طبق سند: گروه‌بندی بر اساس درس + نمایش نوع/مبحث/استاد —
        # قبلاً فقط لیست تخت نام فایل‌ها بود که ارزش کمی داشت.
        type_fa = {
            'pdf': 'PDF', 'video': 'Video', 'voice': 'Voice',
            'pptx': 'PowerPoint', 'test': 'نمونه سوال', 'audio': 'Voice',
        }
        by_lesson: dict = {}
        lesson_order: list = []
        for item in new_items:
            path = await db.bs_get_content_full_path(str(item['_id']))
            lesson_name = path.get('lesson_name', '') or 'سایر'
            if lesson_name not in by_lesson:
                by_lesson[lesson_name] = []
                lesson_order.append(lesson_name)
            ctype = type_fa.get(path.get('content_type', ''), path.get('content_type', '') or 'فایل')
            desc  = path.get('description', '') or path.get('topic', '') or 'بدون عنوان'
            by_lesson[lesson_name].append(f"• {ctype}: {desc}")

        MAX_LESSONS_SHOWN = 4
        MAX_ITEMS_PER_LESSON = 3
        blocks = []
        shown_count = 0
        for lesson_name in lesson_order[:MAX_LESSONS_SHOWN]:
            items = by_lesson[lesson_name]
            block_lines = [f"📘 <b>{lesson_name}</b>"] + items[:MAX_ITEMS_PER_LESSON]
            extra_in_lesson = len(items) - MAX_ITEMS_PER_LESSON
            if extra_in_lesson > 0:
                block_lines.append(f"  ...و {extra_in_lesson} مورد دیگر")
            blocks.append('\n'.join(block_lines))
            shown_count += len(items)

        remaining_lessons = len(lesson_order) - MAX_LESSONS_SHOWN
        remaining_items   = len(new_items) - shown_count
        tail = ""
        if remaining_lessons > 0:
            tail = f"\n\n📦 و {remaining_items} مورد دیگر در {remaining_lessons} درس دیگر"

        text = (
            "📚 <b>منابع جدیدی اضافه شده‌اند</b>\n\n"
            + '\n\n'.join(blocks) + tail +
            "\n\n📚 برای مشاهده کامل: بخش «منابع»\n\n"
            "<i>⚙️ خاموش‌کردن: 🔔 اعلان‌ها ← منابع جدید</i>"
        )

        if len(text) > 3800:
            text = text[:3700] + "\n\n<i>... برای مشاهده کامل وارد بخش «منابع» شوید</i>"

        users = await db.notif_users('new_resources')
        sent, failed, failed_ids = 0, 0, []
        for u in users:
            try:
                await context.bot.send_message(u['user_id'], text, parse_mode='HTML')
                sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                failed += 1
                failed_ids.append(u['user_id'])

        await db.mark_resources_notified([item['_id'] for item in new_items])
        await db.set_setting('resource_notif_last_sent', datetime.now().isoformat())
        await db.notif_run_finish(run_id, sent, failed, len(users))
        if failed_ids:
            await db.notif_run_add_failed(run_id, failed_ids)
        logger.info(f"📚 نوتیف منابع جدید: {len(new_items)} مورد به {sent} نفر ارسال شد")
    except Exception as e:
        logger.error(f"new_resources_notif_job error: {e}")


async def auto_backup_job(context: ContextTypes.DEFAULT_TYPE):
    """
    FIX جدید: بکاپ خودکار روزانه. این job هر ساعت اجرا می‌شود و
    خودش تشخیص می‌دهد آیا الان همان ساعتی است که ادمین تنظیم کرده
    (auto_backup_hour، به‌وقت تهران UTC+3:30) — تا بتوان از پنل
    ادمین ساعت را آزادانه تغییر داد بدون نیاز به ری‌استارت ربات.
    """
    try:
        enabled = await db.get_setting('auto_backup_enabled', False)
        if not enabled:
            return

        target_hour = await db.get_setting('auto_backup_hour', 3)
        now_tehran  = datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)
        if now_tehran.hour != target_hour:
            return

        # جلوگیری از اجرای تکراری در همان ساعت (چون job هر ساعت چک می‌شود)
        last_run = await db.get_setting('auto_backup_last_run', None)
        if last_run:
            last_dt = datetime.fromisoformat(last_run)
            if (datetime.now() - last_dt).total_seconds() < 3600 * 20:
                return  # کمتر از ۲۰ ساعت از آخرین بکاپ گذشته — رد کن

        from backup import build_full_backup_data, send_backup_to_bot_chat
        data = await build_full_backup_data()
        await send_backup_to_bot_chat(context.bot, ADMIN_ID, data, filename='backup_auto')
        await db.set_setting('auto_backup_last_run', datetime.now().isoformat())
        logger.info("💾 بکاپ خودکار با موفقیت ارسال شد")
    except Exception as e:
        logger.error(f"auto_backup_job error: {e}")
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"⚠️ <b>خطا در بکاپ خودکار</b>\n<code>{str(e)[:300]}</code>",
                parse_mode='HTML'
            )
        except Exception:
            pass


async def weekly_report_job(context: ContextTypes.DEFAULT_TYPE):
    """
    FIX باگ مهم: گزارش هفتگی دیگر به پیوی شخصی ادمین ارشد ارسال
    نمی‌شود — طبق درخواست صریح، فقط به گروه لاگ ادمین می‌رود.
    اگر گروه تنظیم نشده باشد، گزارش فقط در لاگ سرور ثبت می‌شود
    (و ارسالی به هیچ‌جا صورت نمی‌گیرد).
    """
    logger.info("📊 اجرای job گزارش هفتگی...")
    try:
        chat_id = await db.get_setting('log_group_admin', None)
        if not chat_id:
            logger.info("گزارش هفتگی: گروه لاگ ادمین تنظیم نشده — ارسالی صورت نگرفت.")
            return
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
        await context.bot.send_message(int(chat_id), text, parse_mode='HTML')
    except Exception as e:
        logger.error(f"weekly_report_job error: {e}")


# ══════════════════════════════════════════════════
#  Error Handler مرکزی
# ══════════════════════════════════════════════════

# FIX باگ: این خطاها کاملاً طبیعی و بی‌خطر هستند — رفتار عادی
# کاربران (کلیک روی دکمه قدیمی، زدن دکمه‌ای که چیزی تغییر نمی‌دهد)
# نه نشانه‌ی یک مشکل واقعی. بدون این فیلتر، هر کدام پیوی شخصی
# ادمین ارشد را شلوغ می‌کرد و خطاهای واقعی در میانشان گم می‌شدند.
SILENT_ERRORS = (
    'Query is too old',
    'query id is invalid',
    'Message is not modified',
    'MESSAGE_ID_INVALID',
    'message to edit not found',
    'message to delete not found',
    "Message can't be deleted",
    'Have no rights to send a message',
)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err_str = str(context.error)

    # خطای بی‌خطر — فقط در لاگ سرور، بدون پیوی به ادمین
    if any(e in err_str for e in SILENT_ERRORS):
        logger.warning(f"⚠️ Silent error (نادیده گرفته شد): {err_str[:150]}")
        if isinstance(update, Update) and update.callback_query:
            try:
                await update.callback_query.answer()
            except Exception:
                pass
        return

    # از اینجا به بعد فقط خطاهای واقعی — همان‌طور که بود
    logger.error(f"Exception: {context.error}", exc_info=context.error)
    if ADMIN_ID:
        try:
            uid_info = ""
            if isinstance(update, Update) and update.effective_user:
                u = update.effective_user
                uid_info = f"\n👤 کاربر: {u.full_name} | آیدی: {u.id}"
            err_text = (
                f"⚠️ <b>خطای ربات</b>{uid_info}\n"
                f"<code>{err_str[:300]}</code>"
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
    # FIX باگ مهم: این گیت فقط باید روی پیوی خصوصی اثر کند —
    # وگرنه پیام «ربات در حال بروزرسانی است» در گروه‌های لاگ
    # (ادمین/محتوا) هم به اعضای آن گروه نمایش داده می‌شد.
    if update.effective_chat is None or update.effective_chat.type != 'private':
        return

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


async def channel_lock_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FIX جدید: قفل اجباری عضویت کانال. اگر ادمین یک یا چند کانال را
    در تنظیمات اضافه کرده باشد، هر کاربر عادی (غیر از ادمین ارشد و
    نقش‌های فرعی ادمین) باید عضو همه آن‌ها باشد تا بتواند از ربات
    استفاده کند. با group=-1 یعنی قبل از maintenance_gate نیست —
    اجرا می‌شود بعد از آن، چون اگر maintenance فعال باشد آن پیام
    اولویت دارد (maintenance_gate با ApplicationHandlerStop متوقف
    می‌کند و این تابع اصلاً اجرا نمی‌شود).
    """
    # FIX باگ مهم: همین مشکل maintenance_gate — فقط پیوی خصوصی
    if update.effective_chat is None or update.effective_chat.type != 'private':
        return

    uid = update.effective_user.id if update.effective_user else None
    if uid is None or uid == ADMIN_ID:
        return

    # دکمه «بررسی مجدد عضویت» با callback خاص — نباید مسدود شود
    if update.callback_query and update.callback_query.data == 'channel_lock:check':
        return

    channels = await db.get_required_channels()
    if not channels:
        return

    # نقش‌های فرعی ادمین هم معاف هستند
    role_doc = await db.get_admin_role(uid)
    if role_doc:
        return

    not_joined = []
    for ch in channels:
        try:
            member = await context.bot.get_chat_member(ch['id'], uid)
            if member.status in ('left', 'kicked'):
                not_joined.append(ch)
        except Exception:
            # اگر ربات نتواند وضعیت را چک کند (مثلاً ادمین کانال نیست)
            # برای امنیت، آن کانال را به‌عنوان عضو‌نشده در نظر می‌گیریم
            not_joined.append(ch)

    if not not_joined:
        return

    keyboard = []
    for ch in not_joined:
        if ch.get('invite_link'):
            keyboard.append([InlineKeyboardButton(f"📢 عضویت در {ch['title']}", url=ch['invite_link'])])
    keyboard.append([InlineKeyboardButton("✅ عضو شدم، بررسی کن", callback_data='channel_lock:check')])

    text = (
        "🔒 <b>عضویت در کانال الزامی است</b>\n\n"
        "برای استفاده از ربات، ابتدا باید در کانال(های) زیر عضو شوید:\n\n"
        + '\n'.join(f"• {ch['title']}" for ch in not_joined)
    )
    try:
        if update.callback_query:
            await update.callback_query.answer("🔒 ابتدا باید عضو کانال شوید", show_alert=True)
        elif update.message:
            await update.message.reply_text(text, parse_mode='HTML',
                                             reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        pass
    raise ApplicationHandlerStop


async def channel_lock_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دکمه «عضو شدم، بررسی کن» — چک مجدد و عبور در صورت موفقیت"""
    query = update.callback_query
    uid   = update.effective_user.id
    channels = await db.get_required_channels()
    still_not_joined = []
    for ch in channels:
        try:
            member = await context.bot.get_chat_member(ch['id'], uid)
            if member.status in ('left', 'kicked'):
                still_not_joined.append(ch)
        except Exception:
            still_not_joined.append(ch)

    if still_not_joined:
        await query.answer("❌ هنوز عضو همه کانال‌ها نشده‌اید!", show_alert=True)
        return

    await query.answer("✅ عضویت تأیید شد!", show_alert=True)
    await query.edit_message_text("✅ عضویت شما تأیید شد. لطفاً /start را بزنید.")


async def update_last_active(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    برای گزارش هفتگی نیاز داریم بدانیم آخرین فعالیت هر کاربر کِی
    بوده. فقط در پیوی خصوصی معنی دارد — فعالیت یک کاربر در گروه
    لاگ ربات (که اصلاً عضو معمولی ربات نیست) را نباید به‌عنوان
    «فعالیت در ربات» ثبت کرد.
    """
    if update.effective_chat is None or update.effective_chat.type != 'private':
        return
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


# FIX باگ: این modeها وقتی کاربر دکمه‌ی اصلی منو را می‌زند (یعنی
# قصد خروج از فلوی نیمه‌کاره را دارد) باید پاک شوند — وگرنه پیام
# بعدی او در هر بخش دیگری از ربات به اشتباه به همین mode می‌رسد.
INTERRUPTIBLE_SIMPLE_MODES = {
    'search_user', 'edit_user', 'add_intake', 'add_admin_role',
    'qbank_awaiting_desc', 'add_schedule', 'flex_time_change',
    'set_auto_backup_hour', 'report_note', 'ticket_search',
    'set_maintenance_text', 'set_log_group_admin', 'set_log_group_content',
    'add_required_channel',
}
MENU_BUTTON_TEXTS = {
    '🩺 داشبورد', '📚 منابع', '🧪 بانک سوال', '❓ سوالات متداول',
    '📅 برنامه', '👤 پروفایل', '🔔 اعلان‌ها', '🎫 پشتیبانی',
    '🎓 پنل محتوا', '👨\u200d⚕️ پنل ادمین',
}


async def unified_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # FIX باگ لغو رول/گزارش/و غیره گیر کردن: اگر کاربر دکمه منو زده
    # و در یکی از modeهای ساده گیر بود، آن mode را پاک کن و رد شو
    # تا روتر اصلی پیام را عادی پردازش کند.
    msg_text = update.message.text.strip() if update.message and update.message.text else ''
    if msg_text in MENU_BUTTON_TEXTS and context.user_data.get('mode') in INTERRUPTIBLE_SIMPLE_MODES:
        for k in ('mode', 'new_role_type', 'new_role_intake', 'flex_change_sid',
                  'report_target_type', 'report_target_id', 'report_reason'):
            context.user_data.pop(k, None)
        # ادامه نده — اجازه بده همین تابع پایین‌تر پیام دکمه را عادی مسیر کند

    # FIX باگ مهم: 'NoneType' object has no attribute 'text' —
    # وقتی mode فعال است (منتظر یک ورودی متنی) ولی کاربر media
    # (عکس/فایل/استیکر/ویس) بدون متن می‌فرستد، update.message.text
    # می‌شود None و توابع پایین‌دستی با .strip() کرش می‌کنند.
    # broadcast و چند mode خاص که خودشان از فایل/عکس پشتیبانی
    # می‌کنند (مثل آپلود فایل بانک سوال) از این گارد معاف هستند.
    active_mode    = context.user_data.get('mode', '')
    active_ca_mode = context.user_data.get('ca_mode', '')
    active_ticket_mode = context.user_data.get('ticket_mode', '')
    MEDIA_ALLOWED_MODES = {
        'broadcast', 'qbank_awaiting_desc', 'waiting_description',
        'waiting_ref_description', 'creating_question',
        'waiting_file', 'waiting_ref_file',  # ca_mode هایی که فایل می‌گیرند
    }
    any_active_mode = active_mode or active_ca_mode or active_ticket_mode
    is_media_allowed = (
        active_mode in MEDIA_ALLOWED_MODES or active_ca_mode in MEDIA_ALLOWED_MODES
    )
    if (any_active_mode and not is_media_allowed
            and update.message is not None and not update.message.text):
        await update.message.reply_text(
            "⚠️ لطفاً پاسخ خود را به‌صورت متن ارسال کنید."
        )
        return

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

    # ۵c. FIX جدید: flex_time_change — اعلام تغییر زمان کلاس منعطف
    if uid == ADMIN_ID and context.user_data.get('mode') == 'flex_time_change':
        from schedule import handle_flex_time_change_text
        return await handle_flex_time_change_text(update, context)

    # ۵d. FIX جدید: ساعت دلخواه بکاپ خودکار
    if uid == ADMIN_ID and context.user_data.get('mode') == 'set_auto_backup_hour':
        from backup import handle_auto_backup_hour_text
        return await handle_auto_backup_hour_text(update, context)

    # ۵e. FIX جدید: توضیح گزارش ایراد (دلیل 'سایر')
    if context.user_data.get('mode') == 'report_note':
        return await handle_report_note_text(update, context)

    # ۵f. FIX جدید: افزودن کانال اجباری
    if uid == ADMIN_ID and context.user_data.get('mode') == 'add_required_channel':
        return await handle_admin_text(update, context)

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
            # FIX باگ مهم: /start و همه‌ی mode‌های گفتگو فقط در پیوی
            # خصوصی فعال باشند — وگرنه ربات روی پیام‌های گروه‌های لاگ
            # (ادمین/محتوا) هم واکنش می‌داد و می‌گفت «/start بزنید».
            CommandHandler('start', start_handler, filters=filters.ChatType.PRIVATE),
            CallbackQueryHandler(questions_callback,      pattern=r'^questions:cr_topic:'),
            CallbackQueryHandler(content_admin_callback,  pattern=r'^ca:'),
        ],
        states={
            REGISTER: [
                CallbackQueryHandler(register_start_callback, pattern=r'^register:')
            ],
            STEP_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, step_name_handler),
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
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, step_student_id_handler),
            ],
            ANSWERING: [
                CallbackQueryHandler(handle_question_answer, pattern=r'^answer:')
            ],
            CREATING_Q: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_create_question_steps),
                CallbackQueryHandler(handle_difficulty_choice, pattern=r'^qd:'),
                CallbackQueryHandler(questions_callback, pattern=r'^questions:'),
            ],
            CA_WAITING_FILE: [
                MessageHandler(
                    (filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.VOICE)
                    & filters.ChatType.PRIVATE,
                    ca_file_handler
                ),
                CallbackQueryHandler(content_admin_callback, pattern=r'^ca:'),
                CommandHandler('cancel', cancel_handler, filters=filters.ChatType.PRIVATE),
            ],
            CA_WAITING_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, ca_text_handler),
                CallbackQueryHandler(content_admin_callback, pattern=r'^ca:'),
                CommandHandler('cancel', cancel_handler, filters=filters.ChatType.PRIVATE),
            ],
            PROFILE_EDIT_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, profile_text_handler),
                CallbackQueryHandler(profile_callback, pattern=r'^profile:'),
                CommandHandler('cancel', cancel_handler, filters=filters.ChatType.PRIVATE),
            ],
            TICKET_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, ticket_message_handler),
                CallbackQueryHandler(ticket_callback, pattern=r'^ticket:'),
                CommandHandler('cancel', cancel_handler, filters=filters.ChatType.PRIVATE),
            ],
            TICKET_REPLY_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, ticket_message_handler),
                CallbackQueryHandler(ticket_callback, pattern=r'^ticket:'),
                CommandHandler('cancel', cancel_handler, filters=filters.ChatType.PRIVATE),
            ],
        },
        fallbacks=[
            CommandHandler('start', start_handler, filters=filters.ChatType.PRIVATE),
            CommandHandler('cancel', cancel_handler, filters=filters.ChatType.PRIVATE),
        ],
        allow_reentry=True,
        per_message=False,
        conversation_timeout=1800,
    )
    # ── FIX جدید: maintenance gate + last_active — قبل از همه چیز (group=-1) ──
    # ترتیب مهم است: ابتدا maintenance (اولویت بالاتر)، سپس قفل کانال
    app.add_handler(TypeHandler(Update, maintenance_gate), group=-1)
    app.add_handler(TypeHandler(Update, channel_lock_gate), group=-1)
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
        (report_callback,          r'^report:'),   # FIX جدید
        (channel_lock_check_callback, r'^channel_lock:check'),   # FIX جدید
    ]
    for handler, pattern in cbs:
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern))

    # ── File handler — همه انواع فایل ──
    # FIX باگ مهم: فقط در پیوی خصوصی فعال باشد — وگرنه فایل‌هایی
    # که در گروه‌های لاگ (ادمین/محتوا) فرستاده شوند هم پردازش می‌شدند.
    app.add_handler(MessageHandler(
        (filters.Document.ALL | filters.VIDEO | filters.AUDIO |
         filters.VOICE | filters.PHOTO) & filters.ChatType.PRIVATE,
        unified_file_handler
    ))

    # ── Text handler ──
    # FIX باگ اصلی گزارش‌شده: این handler عمومی هیچ فیلتر چت نداشت،
    # پس روی هر پیام متنی در گروه‌های لاگ هم اجرا می‌شد و از طریق
    # route_message پاسخ «/start بزنید» می‌فرستاد. حالا فقط پیوی.
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
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

        # FIX جدید: نوتیف منابع جدید — هر ساعت چک می‌شود، خودش تشخیص
        # می‌دهد آیا فاصله‌ی تنظیم‌شده (۲۴/۴۸/۷۲ ساعت) گذشته یا نه
        application.job_queue.run_repeating(
            new_resources_notif_job,
            interval=3600,
            first=120,
            name='new_resources_notif'
        )

        # FIX جدید: بکاپ خودکار — هر ساعت چک می‌شود، فقط در ساعت
        # تنظیم‌شده (از پنل ادمین) واقعاً بکاپ می‌گیرد
        application.job_queue.run_repeating(
            auto_backup_job,
            interval=3600,
            first=180,
            name='auto_backup'
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

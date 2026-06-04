"""
🗺️ Message Router — مسیریابی پیام‌های متنی (دکمه‌های ReplyKeyboard)
"""
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
SEARCH   = 3


# ══════════════════════════════════════════════════
#  مسیریاب اصلی
# ══════════════════════════════════════════════════

async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text.strip()

    # ── حالت‌های خاص ادمین ──
    if uid == ADMIN_ID:
        mode = context.user_data.get('mode', '')
        # FIX: search_user باید قبل از هر چیز چک بشه
        if mode == 'search_user':
            from admin import handle_admin_text
            await handle_admin_text(update, context)
            return
        if mode in ('add_lesson', 'add_topic', 'edit_user'):
            from admin import handle_admin_text
            if await handle_admin_text(update, context):
                return
        if mode == 'broadcast':
            from admin import admin_broadcast_handler
            return await admin_broadcast_handler(update, context)

    # ── حالت ساخت سوال ──
    if context.user_data.get('mode') == 'creating_question':
        from questions import handle_create_question_steps
        return await handle_create_question_steps(update, context)

    # ── حالت ادمین محتوا ──
    ca_text_modes = {
        'add_lesson', 'add_session', 'waiting_description',
        'waiting_ref_description', 'add_faq', 'add_ref_subject',
        'add_ref_book', 'edit_lesson', 'edit_session',
        'edit_ref_subject', 'edit_ref_book',
    }
    if context.user_data.get('ca_mode') in ca_text_modes:
        if await db.is_content_admin(uid):
            from content_admin import ca_text_handler
            return await ca_text_handler(update, context)

    # ── تیکت ──
    if context.user_data.get('ticket_mode') in ('waiting_message', 'admin_reply'):
        from ticket import ticket_message_handler
        return await ticket_message_handler(update, context)

    # ── جستجو ──
    if context.user_data.get('awaiting_search'):
        from search import search_handler
        return await search_handler(update, context)

    # ── بررسی کاربر ──
    user = await db.get_user(uid)
    if not user:
        await update.message.reply_text(
            "لطفاً ابتدا /start را بزنید تا ثبت‌نام کنید."
        )
        return
    if not user.get('approved') and uid != ADMIN_ID:
        await update.message.reply_text("⏳ دسترسی شما هنوز تأیید نشده است.")
        return

    # ── مسیریابی دکمه‌های منو ──
    await _route_menu_button(update, context, text, uid, user)


async def _route_menu_button(update, context, text: str, uid: int, user: dict):
    """مسیریابی دکمه‌های کیبورد اصلی"""

    if text == "🩺 داشبورد":
        from dashboard import build_dashboard_text
        t, kb = await build_dashboard_text(uid)
        await update.message.reply_text(t, parse_mode='HTML', reply_markup=kb)

    elif text == "📚 منابع":
        keyboard = [
            [InlineKeyboardButton("🔬 علوم پایه", callback_data='bs:main')],
            [InlineKeyboardButton("📖 رفرنس‌ها",  callback_data='ref:main')],
        ]
        await update.message.reply_text(
            "📚 <b>منابع درسی</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔬 <b>علوم پایه:</b> محتوای جلسات (ویدیو، جزوه، پاورپوینت و...)\n"
            "📖 <b>رفرنس‌ها:</b> کتاب‌های مرجع درسی (PDF فارسی/لاتین)",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif text == "🧪 بانک سوال":
        from questions import _main_menu_msg
        await _main_menu_msg(update.message)

    elif text == "❓ سوالات متداول":
        from faq import show_faq_main
        await show_faq_main(update.message)

    elif text == "📅 برنامه":
        from schedule import show_schedule_main
        await show_schedule_main(update.message, uid, user)

    elif text == "👤 پروفایل":
        from profile import show_profile_msg
        await show_profile_msg(update)

    elif text == "🔔 اعلان‌ها":
        from notifications import show_notif_settings
        await show_notif_settings(update.message, uid)

    elif text == "🎫 پشتیبانی":
        from ticket import show_ticket_main
        await show_ticket_main(update.message, uid)

    elif text == "🎓 پنل محتوا":
        if await db.is_content_admin(uid):
            from content_admin import show_ca_main
            await show_ca_main(update.message, uid)
        else:
            await update.message.reply_text("❌ دسترسی ندارید.")

    elif text == "👨‍⚕️ پنل ادمین":
        if uid == ADMIN_ID:
            from admin import show_admin_main
            await show_admin_main(update.message)
        else:
            await update.message.reply_text("❌ دسترسی ندارید.")

    elif text == "🔍 جستجو":
        context.user_data['awaiting_search'] = True
        context.user_data['search_mode']     = 'resources'
        await update.message.reply_text(
            "🔍 <b>جستجو</b>\n\nکلمه‌ای که دنبالش هستید را بنویسید:",
            parse_mode='HTML'
        )

    else:
        # پیام نامشناخته — راهنمای سریع
        await update.message.reply_text(
            "از دکمه‌های منو استفاده کنید یا /start بزنید.",
        )

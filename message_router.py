import os, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from utils import NOTIF_LABELS

logger = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
SEARCH = 3


async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text

    # ── حالت‌های ادمین اصلی ──
    if uid == ADMIN_ID:
        mode = context.user_data.get('mode', '')
        if mode in ('add_lesson', 'add_topic', 'edit_user'):
            from admin import handle_admin_text
            if await handle_admin_text(update, context): return
        if mode == 'broadcast':
            from admin import admin_broadcast_handler
            return await admin_broadcast_handler(update, context)

    # ── حالت ساخت سوال ──
    if context.user_data.get('mode') == 'creating_question':
        from questions import handle_create_question_steps
        return await handle_create_question_steps(update, context)

    # ── حالت ادمین محتوا ──
    if context.user_data.get('ca_mode') in ('add_lesson','add_session','waiting_description',
                                              'waiting_ref_description',
                                              'add_faq','add_ref_subject','add_ref_book',
                                              'edit_lesson','edit_session',
                                              'edit_ref_subject','edit_ref_book'):
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
        await update.message.reply_text("لطفاً /start را بزنید.")
        return
    if not user.get('approved') and uid != ADMIN_ID:
        await update.message.reply_text("⏳ دسترسی شما هنوز تأیید نشده است.")
        return

    # ════ مسیریابی دکمه‌ها ════

    if text == "🩺 داشبورد":
        from dashboard import build_dashboard_text
        t, kb = await build_dashboard_text(uid)
        await update.message.reply_text(t, parse_mode='HTML', reply_markup=kb)

    elif text == "📚 منابع":
        keyboard = [
            [InlineKeyboardButton("🔬 علوم پایه",  callback_data='bs:main')],
            [InlineKeyboardButton("📖 رفرنس‌ها",   callback_data='ref:main')],
        ]
        await update.message.reply_text(
            "📚 <b>منابع درسی</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "🔬 <b>علوم پایه:</b> محتوای جلسات (ویدیو، جزوه، پاورپوینت و...)\n"
            "📖 <b>رفرنس‌ها:</b> کتاب‌های مرجع درسی (PDF فارسی/لاتین)",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif text == "🧪 بانک سوال":
        keyboard = [
            [InlineKeyboardButton("📁 بانک سوال ادمین",   callback_data='questions:file_bank')],
            [InlineKeyboardButton("🧪 تمرین تستی",         callback_data='questions:practice')],
            [InlineKeyboardButton("✏️ طراحی سوال",         callback_data='questions:create')],
            [InlineKeyboardButton("📊 آمار تمرین من",      callback_data='questions:stats')],
        ]
        await update.message.reply_text(
            "🧪 <b>بانک سوال</b>\n\n"
            "📁 فایل PDF بانک سوال اساتید\n"
            "🧪 تمرین سوالات چهارگزینه‌ای\n"
            "✏️ طراحی و ارسال سوال",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif text == "❓ سوالات متداول":
        keyboard = [
            [InlineKeyboardButton("🔬 علوم پایه",        callback_data='faq:cat:0')],
            [InlineKeyboardButton("📚 رفرنس‌ها",          callback_data='faq:cat:1')],
            [InlineKeyboardButton("🧪 بانک سوال",         callback_data='faq:cat:2')],
            [InlineKeyboardButton("📅 برنامه و امتحانات", callback_data='faq:cat:3')],
            [InlineKeyboardButton("👤 حساب کاربری",       callback_data='faq:cat:4')],
            [InlineKeyboardButton("⚙️ مشکلات فنی",        callback_data='faq:cat:5')],
        ]
        await update.message.reply_text(
            "❓ <b>سوالات متداول</b>\n\n━━━━━━━━━━━━━━━━\nدر کدام بخش سوال دارید؟",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif text == "👤 پروفایل":
        from profile import _show_profile_msg
        await _show_profile_msg(update)

    elif text == "📅 برنامه":
        keyboard = [
            [InlineKeyboardButton("📖 کلاس‌ها",       callback_data='schedule:type:class'),
             InlineKeyboardButton("📝 امتحانات",       callback_data='schedule:type:exam')],
            [InlineKeyboardButton("🔄 جبرانی",         callback_data='schedule:type:makeup'),
             InlineKeyboardButton("⏳ امتحانات نزدیک", callback_data='schedule:upcoming')],
        ]
        await update.message.reply_text("📅 <b>برنامه و امتحانات</b>", parse_mode='HTML',
                                         reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == "📊 آمار من":
        keyboard = [
            [InlineKeyboardButton("📊 آمار کلی",      callback_data='stats:main')],
            [InlineKeyboardButton("📅 فعالیت هفتگی",  callback_data='stats:weekly'),
             InlineKeyboardButton("⚡ نقاط ضعف",       callback_data='stats:weak')],
        ]
        await update.message.reply_text("📊 <b>آمار من</b>", parse_mode='HTML',
                                         reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == "🔔 اعلان‌ها":
        user_data = await db.get_user(uid)
        s = user_data.get('notification_settings', {}) if user_data else {}
        from notifications import NOTIF_ITEMS
        keyboard = []
        for key, label, _ in NOTIF_ITEMS:
            default = False if key == 'daily_question' else True
            icon = "🔔" if s.get(key, default) else "🔕"
            keyboard.append([InlineKeyboardButton(f"{icon} {label}", callback_data=f'notif:toggle:{key}')])
        keyboard.append([
            InlineKeyboardButton("✅ همه روشن",   callback_data='notif:all_on'),
            InlineKeyboardButton("🔕 همه خاموش", callback_data='notif:all_off')
        ])
        await update.message.reply_text("🔔 <b>تنظیمات اعلان‌ها</b>", parse_mode='HTML',
                                         reply_markup=InlineKeyboardMarkup(keyboard))

    elif text == "🎫 پشتیبانی":
        keyboard = [
            [InlineKeyboardButton("🎫 تیکت جدید",          callback_data='ticket:new')],
            [InlineKeyboardButton("📋 تیکت‌های من",         callback_data='ticket:list')],
        ]
        if uid == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("📬 تیکت‌های باز (ادمین)", callback_data='ticket:admin_list')])
        await update.message.reply_text(
            "🎫 <b>پشتیبانی</b>\n\nبرای ارسال مشکل یا سوال، تیکت جدید بزنید:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif text == "👨‍⚕️ پنل ادمین" and uid == ADMIN_ID:
        await _admin_panel_msg(update)

    elif text == "🎓 پنل محتوا":
        if await db.is_content_admin(uid):
            keyboard = [
                [InlineKeyboardButton("📘 مدیریت علوم پایه", callback_data='ca:terms')],
                [InlineKeyboardButton("📚 مدیریت رفرنس‌ها",  callback_data='ca:refs')],
                [InlineKeyboardButton("❓ مدیریت FAQ",         callback_data='ca:faq')],
            ]
            await update.message.reply_text("🎓 <b>پنل ادمین محتوا</b>", parse_mode='HTML',
                                             reply_markup=InlineKeyboardMarkup(keyboard))


async def _admin_panel_msg(update):
    """منوی پنل ادمین — دقیقاً همان ساختار _admin_menu در admin.py"""
    from database import db as _db
    s = await _db.global_stats()
    keyboard = [
        [InlineKeyboardButton(
            f"📊 آمار سیستم  ({s['users']} کاربر | {s.get('open_tickets',0)} تیکت باز)",
            callback_data='admin:stats'
        )],
        [InlineKeyboardButton("👥 مدیریت کاربران",   callback_data='admin:users'),
         InlineKeyboardButton("⏳ تأیید کاربران",    callback_data='admin:pending')],
        [InlineKeyboardButton("🔍 جستجوی کاربر",     callback_data='admin:search_user')],
        [InlineKeyboardButton("🎓 ادمین‌های محتوا",  callback_data='admin:content_admins')],
        [InlineKeyboardButton("📘 علوم پایه",        callback_data='ca:terms_admin'),
         InlineKeyboardButton("📚 رفرنس‌ها",         callback_data='ca:refs_admin')],
        [InlineKeyboardButton("❓ مدیریت FAQ",        callback_data='ca:faq')],
        [InlineKeyboardButton("🧪 بانک سوال",        callback_data='admin:qbank_manage'),
         InlineKeyboardButton("✅ تأیید سوالات",     callback_data='admin:pending_q')],
        [InlineKeyboardButton("📅 برنامه جدید",      callback_data='admin:add_schedule'),
         InlineKeyboardButton("🗑 حذف برنامه",       callback_data='admin:del_schedule_list')],
        [InlineKeyboardButton("🎫 تیکت‌های باز",     callback_data='ticket:admin_list')],
        [InlineKeyboardButton("📢 ارسال همگانی",      callback_data='admin:broadcast')],
    ]
    await update.message.reply_text(
        "👨‍⚕️ <b>پنل مدیریت</b>\n━━━━━━━━━━━━━━━━",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from utils import main_keyboard, admin_keyboard, content_admin_keyboard

logger = logging.getLogger(__name__)

REGISTER  = 0
STEP_NAME = 10
STEP_GROUP = 12   # student_id step حذف شد

ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid        = update.effective_user.id
    first_name = update.effective_user.first_name or ''
    user       = await db.get_user(uid)

    if not user:
        context.user_data.clear()
        await update.message.reply_text(
            f"🩺 <b>به ربات آموزشی پزشکی خوش آمدید!</b>\n\n"
            f"سلام <b>{first_name}</b> عزیز 👋\n\n"
            "این ربات به شما کمک می‌کند:\n"
            "📚 منابع و جزوات درسی\n"
            "🎥 آرشیو کلاس‌ها\n"
            "🧪 بانک سوال و تمرین\n"
            "📅 برنامه کلاس‌ها و امتحانات\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "برای شروع، ابتدا باید ثبت‌نام کنید.\n"
            "این فرآیند فقط <b>۲ مرحله</b> دارد! 🚀",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ شروع ثبت‌نام", callback_data='register:start')
            ]])
        )
        return REGISTER

    if not user.get('approved') and uid != ADMIN_ID:
        await update.message.reply_text(
            "⏳ <b>در انتظار تأیید</b>\n\n"
            f"سلام {user.get('name','')} عزیز،\n"
            "ثبت‌نام شما انجام شده و در انتظار تأیید ادمین است.\n\n"
            "به زودی دسترسی شما فعال می‌شود. 🙏",
            parse_mode='HTML'
        )
        return ConversationHandler.END

    kb = admin_keyboard() if uid == ADMIN_ID else (
         content_admin_keyboard() if user.get('role') == 'content_admin' else main_keyboard())
    await update.message.reply_text(
        f"🩺 <b>خوش برگشتید {user.get('name','')} عزیز!</b>",
        parse_mode='HTML', reply_markup=kb)
    await show_dashboard_msg(update, context)
    return ConversationHandler.END


async def register_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'register:start':
        context.user_data['reg_step'] = 'name'
        await query.edit_message_text(
            "📝 <b>مرحله ۱ از ۲ — نام و نام خانوادگی</b>\n\n"
            "👤 لطفاً نام و نام خانوادگی کامل خود را بنویسید:\n\n"
            "<i>مثال: علی احمدی</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ انصراف", callback_data='register:cancel')
            ]])
        )
        return STEP_NAME

    elif query.data == 'register:cancel':
        await query.edit_message_text("❌ ثبت‌نام لغو شد.\n\nبرای شروع مجدد /start بزنید.")
        return ConversationHandler.END

    elif query.data == 'register:group1':
        return await _save_group(update, context, '1')
    elif query.data == 'register:group2':
        return await _save_group(update, context, '2')


async def step_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()

    if len(name) < 3:
        await update.message.reply_text("⚠️ نام باید حداقل ۳ حرف باشد.\n\n👤 لطفاً نام کامل خود را بنویسید:")
        return STEP_NAME
    if len(name) > 50:
        await update.message.reply_text("⚠️ نام نباید بیشتر از ۵۰ حرف باشد:")
        return STEP_NAME

    context.user_data['reg_name'] = name
    context.user_data['reg_step'] = 'group'

    await update.message.reply_text(
        f"✅ <b>نام ثبت شد:</b> {name}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📝 <b>مرحله ۲ از ۲ — انتخاب گروه</b>\n\n"
        "👥 گروه درسی خود را انتخاب کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("1️⃣ گروه ۱", callback_data='register:group1'),
             InlineKeyboardButton("2️⃣ گروه ۲", callback_data='register:group2')],
            [InlineKeyboardButton("❌ انصراف",  callback_data='register:cancel')]
        ])
    )
    return STEP_GROUP


async def _save_group(update, context, group):
    query    = update.callback_query
    uid      = update.effective_user.id
    username = update.effective_user.username
    name     = context.user_data.get('reg_name', '')

    if not name:
        await query.edit_message_text("❌ خطایی رخ داد. لطفاً /start بزنید و مجدد ثبت‌نام کنید.")
        return ConversationHandler.END

    # student_id خالی — دیگه نیازی نیست
    await db.create_user(uid, name, '', group, username)

    if uid == ADMIN_ID:
        await db.update_user(uid, {'approved': True})
        await query.edit_message_text(
            f"🎉 <b>ثبت‌نام کامل شد!</b>\n\n"
            f"👤 نام: <b>{name}</b>\n"
            f"👥 گروه: <b>{group}</b>\n"
            f"🔑 نقش: <b>ادمین</b>\n\n"
            f"✅ دسترسی شما فعال است.",
            parse_mode='HTML'
        )
        await context.bot.send_message(uid, "به پنل ادمین خوش آمدید! 👨‍⚕️", reply_markup=admin_keyboard())
        await _send_dashboard(context, uid)
    else:
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"🔔 <b>درخواست ثبت‌نام جدید</b>\n\n"
                f"👤 نام: <b>{name}</b>\n"
                f"👥 گروه: <b>{group}</b>\n"
                f"📱 یوزرنیم: @{username or 'ندارد'}\n"
                f"🆔 آیدی: <code>{uid}</code>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ تأیید", callback_data=f'admin:approve:{uid}'),
                    InlineKeyboardButton("❌ رد",    callback_data=f'admin:reject:{uid}')
                ]])
            )
        except Exception as e:
            logger.error(f"Cannot notify admin: {e}")

        await query.edit_message_text(
            f"🎉 <b>ثبت‌نام با موفقیت انجام شد!</b>\n\n"
            f"👤 نام: <b>{name}</b>\n"
            f"👥 گروه: <b>{group}</b>\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"⏳ <b>در انتظار تأیید ادمین...</b>\n\n"
            f"به زودی دسترسی شما فعال می‌شود و پیام تأیید دریافت خواهید کرد. 🙏",
            parse_mode='HTML'
        )

    for k in ['reg_name', 'reg_step']:
        context.user_data.pop(k, None)
    return ConversationHandler.END


async def register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return REGISTER


async def _send_dashboard(context, uid):
    from dashboard import build_dashboard_text
    try:
        user = await db.get_user(uid)
        if user and user.get('approved'):
            text, kb = await build_dashboard_text(uid)
            await context.bot.send_message(uid, text, parse_mode='HTML', reply_markup=kb)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")


async def show_dashboard_msg(update, context):
    from dashboard import build_dashboard_text
    uid = update.effective_user.id
    try:
        text, kb = await build_dashboard_text(uid)
        await update.effective_message.reply_text(text, parse_mode='HTML', reply_markup=kb)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")

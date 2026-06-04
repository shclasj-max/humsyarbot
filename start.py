"""
🚀 Start — ثبت‌نام و ورود کاربر
"""
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from utils import main_keyboard, admin_keyboard, content_admin_keyboard, get_keyboard_for_user

logger = logging.getLogger(__name__)

ADMIN_ID  = int(os.getenv('ADMIN_ID', '0'))
REGISTER  = 0
STEP_NAME = 10
STEP_GROUP = 12


# ══════════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════════

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid        = update.effective_user.id
    first_name = update.effective_user.first_name or ''
    user       = await db.get_user(uid)

    # ── کاربر جدید ──
    if not user:
        context.user_data.clear()
        await update.message.reply_text(
            f"🩺 <b>به ربات آموزشی پزشکی خوش آمدید!</b>\n\n"
            f"سلام <b>{first_name}</b> عزیز 👋\n\n"
            "این ربات به شما کمک می‌کند:\n"
            "📚 منابع و جزوات درسی\n"
            "🧪 بانک سوال و تمرین هوشمند\n"
            "📅 برنامه کلاس‌ها و امتحانات\n"
            "🎫 پشتیبانی و پاسخ سریع\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "برای شروع، ابتدا ثبت‌نام کنید.\n"
            "فقط <b>۲ مرحله</b> ساده! 🚀",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ شروع ثبت‌نام", callback_data='register:start')
            ]])
        )
        return REGISTER

    # ── در انتظار تأیید ──
    if not user.get('approved') and uid != ADMIN_ID:
        await update.message.reply_text(
            "⏳ <b>در انتظار تأیید</b>\n\n"
            f"سلام <b>{user.get('name', '')}</b> عزیز،\n"
            "ثبت‌نام شما انجام شده و منتظر تأیید ادمین است.\n\n"
            "به زودی دسترسی شما فعال می‌شود. 🙏",
            parse_mode='HTML'
        )
        return ConversationHandler.END

    # ── کاربر تأییدشده ──
    kb = get_keyboard_for_user(user, uid)
    await update.message.reply_text(
        f"🩺 <b>خوش برگشتید {user.get('name', '')} عزیز!</b>",
        parse_mode='HTML',
        reply_markup=kb
    )
    await _show_dashboard(update, context)
    return ConversationHandler.END


# ══════════════════════════════════════════════════
#  ثبت‌نام — Callbacks
# ══════════════════════════════════════════════════

async def register_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    if data == 'register:start':
        context.user_data['reg_step'] = 'name'
        await query.edit_message_text(
            "📝 <b>مرحله ۱ از ۲ — نام و نام خانوادگی</b>\n\n"
            "👤 لطفاً نام کامل خود را بنویسید:\n\n"
            "<i>مثال: علی احمدی</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ انصراف", callback_data='register:cancel')
            ]])
        )
        return STEP_NAME

    elif data == 'register:cancel':
        await query.edit_message_text(
            "❌ ثبت‌نام لغو شد.\n\nبرای شروع مجدد /start بزنید."
        )
        return ConversationHandler.END

    elif data == 'register:group1':
        return await _save_group(update, context, '1')

    elif data == 'register:group2':
        return await _save_group(update, context, '2')

    return REGISTER


async def step_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text("⚠️ نام باید حداقل ۳ حرف باشد. مجدد وارد کنید:")
        return STEP_NAME
    if len(name) > 50:
        await update.message.reply_text("⚠️ نام نباید بیشتر از ۵۰ حرف باشد:")
        return STEP_NAME

    context.user_data['reg_name'] = name

    await update.message.reply_text(
        f"✅ <b>نام ثبت شد:</b> {name}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📝 <b>مرحله ۲ از ۲ — انتخاب گروه درسی</b>\n\n"
        "👥 گروه خود را انتخاب کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("1️⃣ گروه ۱", callback_data='register:group1'),
                InlineKeyboardButton("2️⃣ گروه ۲", callback_data='register:group2'),
            ],
            [InlineKeyboardButton("❌ انصراف", callback_data='register:cancel')],
        ])
    )
    return STEP_GROUP


async def _save_group(update, context, group: str):
    query    = update.callback_query
    uid      = update.effective_user.id
    username = update.effective_user.username
    name     = context.user_data.get('reg_name', '')

    if not name:
        await query.edit_message_text("❌ خطا. لطفاً /start بزنید.")
        return ConversationHandler.END

    await db.create_user(uid, name, '', group, username)

    if uid == ADMIN_ID:
        await db.update_user(uid, {'approved': True})
        await query.edit_message_text(
            f"🎉 <b>ثبت‌نام کامل شد!</b>\n\n"
            f"👤 نام: <b>{name}</b>  |  👥 گروه: <b>{group}</b>\n"
            f"🔑 نقش: <b>ادمین</b>  |  ✅ دسترسی فعال",
            parse_mode='HTML'
        )
        await context.bot.send_message(
            uid, "به پنل ادمین خوش آمدید! 👨‍⚕️",
            reply_markup=admin_keyboard()
        )
        await _send_dashboard_by_id(context, uid)
    else:
        # اطلاع‌رسانی به ادمین
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
                    InlineKeyboardButton("❌ رد",    callback_data=f'admin:reject:{uid}'),
                ]])
            )
        except Exception as e:
            logger.warning(f"Cannot notify admin: {e}")

        await query.edit_message_text(
            f"🎉 <b>ثبت‌نام با موفقیت انجام شد!</b>\n\n"
            f"👤 نام: <b>{name}</b>  |  👥 گروه: <b>{group}</b>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "⏳ <b>در انتظار تأیید ادمین...</b>\n\n"
            "پس از تأیید، پیام دریافت خواهید کرد. 🙏",
            parse_mode='HTML'
        )

    # پاک‌سازی user_data
    context.user_data.pop('reg_name', None)
    context.user_data.pop('reg_step', None)
    return ConversationHandler.END


# ══════════════════════════════════════════════════
#  توابع کمکی داشبورد
# ══════════════════════════════════════════════════

async def _show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from dashboard import build_dashboard_text
    uid = update.effective_user.id
    try:
        text, kb = await build_dashboard_text(uid)
        await update.effective_message.reply_text(text, parse_mode='HTML', reply_markup=kb)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")


async def _send_dashboard_by_id(context: ContextTypes.DEFAULT_TYPE, uid: int):
    from dashboard import build_dashboard_text
    try:
        text, kb = await build_dashboard_text(uid)
        await context.bot.send_message(uid, text, parse_mode='HTML', reply_markup=kb)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")

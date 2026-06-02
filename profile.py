"""پروفایل کاربر — مشاهده و ویرایش اطلاعات شخصی"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db

logger = logging.getLogger(__name__)

PROFILE_EDIT_WAITING = 70



async def _show_profile_msg(update):
    """ارسال پروفایل از طریق پیام متنی (دکمه کیبورد)"""
    uid  = update.effective_user.id
    user = await db.get_user(uid)
    if not user:
        await update.message.reply_text("❌ کاربر پیدا نشد.")
        return

    stats   = await db.user_stats(uid)
    tickets = await db.ticket_get_user(uid)
    open_t  = sum(1 for t in tickets if t['status'] == 'open')

    role_map = {
        'student':       '🧑‍🎓 دانشجو',
        'content_admin': '🎓 ادمین محتوا',
        'admin':         '👑 ادمین'
    }
    role_icon = role_map.get(user.get('role', 'student'), '🧑‍🎓 دانشجو')

    total_correct = stats.get('correct_answers', 0)
    if   total_correct >= 200: rank = "🏆 نخبه"
    elif total_correct >= 100: rank = "🥇 حرفه‌ای"
    elif total_correct >= 50:  rank = "🥈 پیشرفته"
    elif total_correct >= 20:  rank = "🥉 در حال رشد"
    else:                      rank = "🌱 تازه‌کار"

    pct    = stats.get('percentage', 0)
    filled = int(pct / 10)
    bar    = '█' * filled + '░' * (10 - filled)

    reg_date = user.get('registered_at', '')[:10] if user.get('registered_at') else 'نامشخص'
    uname    = f"@{user['username']}" if user.get('username') else '—'

    text = (
        f"╔══════════════════╗\n"
        f"   👤 <b>پروفایل من</b>\n"
        f"╚══════════════════╝\n\n"
        f"📛 <b>نام:</b>  {user.get('name','')}\n"
        f"👥 <b>گروه:</b>  گروه {user.get('group','')}\n"
        f"📱 <b>یوزرنیم:</b>  {uname}\n"
        f"🎭 <b>نقش:</b>  {role_icon}\n"
        f"📅 <b>ثبت‌نام:</b>  {reg_date}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 <b>آمار تحصیلی</b>\n\n"
        f"🧪 سوال پاسخ داده: <b>{stats.get('total_answers',0)}</b>\n"
        f"✅ پاسخ صحیح: <b>{total_correct}</b>\n"
        f"📈 درصد موفقیت: <b>{pct}%</b>\n"
        f"<code>[{bar}]</code>\n\n"
        f"📥 دانلودها: <b>{stats.get('downloads',0)}</b>\n"
        f"🔥 فعالیت هفتگی: <b>{stats.get('week_activity',0)}</b>\n"
        f"🎫 تیکت باز: <b>{open_t}</b>\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🏅 <b>رتبه:</b>  {rank}\n"
    )

    keyboard = [
        [InlineKeyboardButton("✏️ ویرایش نام",  callback_data='profile:edit_name'),
         InlineKeyboardButton("👥 تغییر گروه",   callback_data='profile:edit_group')],
        [InlineKeyboardButton("🔄 بروزرسانی",    callback_data='profile:refresh')],
    ]
    await update.message.reply_text(
        text, parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard))

async def profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    uid    = update.effective_user.id
    data   = query.data
    parts  = data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    if action == 'main':
        await _show_profile(query, uid)

    elif action == 'edit_name':
        context.user_data['profile_edit'] = 'name'
        await query.edit_message_text(
            "✏️ <b>ویرایش نام</b>\n\n"
            "نام و نام خانوادگی جدید خود را بنویسید:\n\n"
            "<i>مثال: علی احمدی</i>\n\n"
            "⌨️ /cancel برای لغو",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='profile:main')
            ]]))
        return PROFILE_EDIT_WAITING

    elif action == 'edit_group':
        await query.edit_message_text(
            "👥 <b>تغییر گروه درسی</b>\n\n"
            "گروه جدید خود را انتخاب کنید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("1️⃣ گروه ۱", callback_data='profile:set_group:1'),
                 InlineKeyboardButton("2️⃣ گروه ۲", callback_data='profile:set_group:2')],
                [InlineKeyboardButton("🔙 بازگشت", callback_data='profile:main')]
            ]))

    elif action == 'set_group':
        new_group = parts[2]
        await db.update_user(uid, {'group': new_group})
        await query.answer(f"✅ گروه به {new_group} تغییر یافت!", show_alert=True)
        await _show_profile(query, uid)

    elif action == 'refresh':
        await _show_profile(query, uid)


async def _show_profile(query, uid):
    user  = await db.get_user(uid)
    if not user:
        await query.edit_message_text("❌ کاربر پیدا نشد.")
        return

    stats = await db.user_stats(uid)
    tickets = await db.ticket_get_user(uid)
    open_t  = sum(1 for t in tickets if t['status'] == 'open')

    role_map = {
        'student':       '🧑‍🎓 دانشجو',
        'content_admin': '🎓 ادمین محتوا',
        'admin':         '👑 ادمین'
    }
    role_icon = role_map.get(user.get('role','student'), '🧑‍🎓 دانشجو')

    # محاسبه رتبه بر اساس فعالیت
    activity = stats.get('week_activity', 0)
    total_correct = stats.get('correct_answers', 0)
    if total_correct >= 200:   rank = "🏆 نخبه"
    elif total_correct >= 100: rank = "🥇 حرفه‌ای"
    elif total_correct >= 50:  rank = "🥈 پیشرفته"
    elif total_correct >= 20:  rank = "🥉 در حال رشد"
    else:                      rank = "🌱 تازه‌کار"

    # نوار پیشرفت
    pct = stats.get('percentage', 0)
    filled = int(pct / 10)
    bar = '█' * filled + '░' * (10 - filled)

    reg_date = user.get('registered_at', '')[:10] if user.get('registered_at') else 'نامشخص'
    uname    = f"@{user['username']}" if user.get('username') else '—'

    text = (
        f"╔══════════════════╗\n"
        f"   👤 <b>پروفایل من</b>\n"
        f"╚══════════════════╝\n\n"
        f"📛 <b>نام:</b>  {user.get('name','')}\n"
        f"👥 <b>گروه:</b>  گروه {user.get('group','')}\n"
        f"📱 <b>یوزرنیم:</b>  {uname}\n"
        f"🎭 <b>نقش:</b>  {role_icon}\n"
        f"📅 <b>ثبت‌نام:</b>  {reg_date}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 <b>آمار تحصیلی</b>\n\n"
        f"🧪 سوال پاسخ داده: <b>{stats.get('total_answers',0)}</b>\n"
        f"✅ پاسخ صحیح: <b>{stats.get('correct_answers',0)}</b>\n"
        f"📈 درصد موفقیت: <b>{pct}%</b>\n"
        f"<code>[{bar}]</code>\n\n"
        f"📥 دانلودها: <b>{stats.get('downloads',0)}</b>\n"
        f"🔥 فعالیت هفتگی: <b>{activity}</b>\n"
        f"🎫 تیکت باز: <b>{open_t}</b>\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🏅 <b>رتبه:</b>  {rank}\n"
    )

    keyboard = [
        [InlineKeyboardButton("✏️ ویرایش نام",    callback_data='profile:edit_name'),
         InlineKeyboardButton("👥 تغییر گروه",     callback_data='profile:edit_group')],
        [InlineKeyboardButton("🔄 بروزرسانی",      callback_data='profile:refresh')],
    ]

    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def profile_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    mode = context.user_data.get('profile_edit','')
    text = update.message.text.strip()

    if text.lower() in ('/cancel', 'لغو'):
        context.user_data.pop('profile_edit', None)
        await update.message.reply_text("✅ لغو شد.")
        return ConversationHandler.END

    if mode == 'name':
        if len(text) < 3:
            await update.message.reply_text("⚠️ نام باید حداقل ۳ حرف باشد:")
            return PROFILE_EDIT_WAITING
        if len(text) > 50:
            await update.message.reply_text("⚠️ نام نباید بیشتر از ۵۰ حرف باشد:")
            return PROFILE_EDIT_WAITING
        await db.update_user(uid, {'name': text})
        context.user_data.pop('profile_edit', None)
        await update.message.reply_text(
            f"✅ نام به <b>{text}</b> تغییر یافت!",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("👤 مشاهده پروفایل", callback_data='profile:main')
            ]]))
        return ConversationHandler.END

    return PROFILE_EDIT_WAITING

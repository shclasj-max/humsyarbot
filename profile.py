"""
👤 پروفایل کاربر — مشاهده و ویرایش اطلاعات شخصی
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from utils import progress_bar, get_rank

logger = logging.getLogger(__name__)
PROFILE_EDIT_WAITING = 70


def _profile_text(user: dict, stats: dict, open_tickets: int) -> str:
    role_map = {
        'student':       '🧑‍🎓 دانشجو',
        'content_admin': '🎓 ادمین محتوا',
        'admin':         '👑 ادمین',
    }
    role_icon = role_map.get(user.get('role', 'student'), '🧑‍🎓 دانشجو')
    rank      = get_rank(stats.get('correct_answers', 0))
    pct       = stats.get('percentage', 0)
    bar       = progress_bar(pct)
    reg_date  = user.get('registered_at', '')[:10] or 'نامشخص'
    uname     = f"@{user['username']}" if user.get('username') else '—'

    return (
        "╔══════════════════╗\n"
        "   👤 <b>پروفایل من</b>\n"
        "╚══════════════════╝\n\n"
        f"📛 <b>نام:</b>  {user.get('name', '')}\n"
        f"👥 <b>گروه:</b>  گروه {user.get('group', '')}\n"
        f"📱 <b>یوزرنیم:</b>  {uname}\n"
        f"🎭 <b>نقش:</b>  {role_icon}\n"
        f"📅 <b>ثبت‌نام:</b>  {reg_date}\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📊 <b>آمار تحصیلی</b>\n\n"
        f"🧪 سوال پاسخ داده: <b>{stats.get('total_answers', 0)}</b>\n"
        f"✅ پاسخ صحیح: <b>{stats.get('correct_answers', 0)}</b>\n"
        f"📈 درصد موفقیت: <b>{pct}%</b>\n"
        f"<code>[{bar}]</code>\n\n"
        f"📥 دانلودها: <b>{stats.get('downloads', 0)}</b>\n"
        f"🔥 فعالیت هفتگی: <b>{stats.get('week_activity', 0)}</b>\n"
        f"🎫 تیکت باز: <b>{open_tickets}</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        f"🏅 <b>رتبه:</b>  {rank}\n"
    )


def _profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ ویرایش نام",  callback_data='profile:edit_name'),
            InlineKeyboardButton("👥 تغییر گروه",   callback_data='profile:edit_group'),
        ],
        [InlineKeyboardButton("🔄 بروزرسانی",       callback_data='profile:refresh')],
        [InlineKeyboardButton("🔙 داشبورد",          callback_data='dashboard:refresh')],
    ])


async def _get_profile_data(uid: int) -> tuple:
    user    = await db.get_user(uid)
    stats   = await db.user_stats(uid)
    tickets = await db.ticket_get_user(uid)
    open_t  = sum(1 for t in tickets if t.get('status') == 'open')
    return user, stats, open_t


# ══════════════════════════════════════════════════
#  Callback
# ══════════════════════════════════════════════════

async def profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    uid    = update.effective_user.id
    parts  = query.data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    if action in ('main', 'refresh'):
        user, stats, open_t = await _get_profile_data(uid)
        if not user:
            await query.edit_message_text("❌ کاربر پیدا نشد.")
            return
        await query.edit_message_text(
            _profile_text(user, stats, open_t),
            parse_mode='HTML',
            reply_markup=_profile_keyboard()
        )

    elif action == 'edit_name':
        context.user_data['profile_edit'] = 'name'
        await query.edit_message_text(
            "✏️ <b>ویرایش نام</b>\n\n"
            "نام و نام خانوادگی جدید خود را بنویسید:\n"
            "<i>مثال: علی احمدی</i>\n\n/cancel برای لغو",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='profile:main')
            ]])
        )
        return PROFILE_EDIT_WAITING

    elif action == 'edit_group':
        await query.edit_message_text(
            "👥 <b>تغییر گروه درسی</b>\n\nگروه جدید خود را انتخاب کنید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("1️⃣ گروه ۱", callback_data='profile:set_group:1'),
                    InlineKeyboardButton("2️⃣ گروه ۲", callback_data='profile:set_group:2'),
                ],
                [InlineKeyboardButton("🔙 بازگشت", callback_data='profile:main')],
            ])
        )

    elif action == 'set_group' and len(parts) > 2:
        new_group = parts[2]
        await db.update_user(uid, {'group': new_group})
        await query.answer(f"✅ گروه به {new_group} تغییر یافت!", show_alert=True)
        user, stats, open_t = await _get_profile_data(uid)
        await query.edit_message_text(
            _profile_text(user, stats, open_t),
            parse_mode='HTML',
            reply_markup=_profile_keyboard()
        )


async def profile_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    mode = context.user_data.get('profile_edit', '')
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
            ]])
        )
        return ConversationHandler.END

    return PROFILE_EDIT_WAITING


# ══════════════════════════════════════════════════
#  فراخوانی از message_router
# ══════════════════════════════════════════════════

async def show_profile_msg(update: Update):
    uid             = update.effective_user.id
    user, stats, open_t = await _get_profile_data(uid)
    if not user:
        await update.message.reply_text("❌ کاربر پیدا نشد.")
        return
    await update.message.reply_text(
        _profile_text(user, stats, open_t),
        parse_mode='HTML',
        reply_markup=_profile_keyboard()
    )

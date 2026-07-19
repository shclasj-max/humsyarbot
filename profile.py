"""
👤 پروفایل کاربر
  ✅ FIX: ویرایش نام بدون ConversationHandler — با mode در unified_text_handler
  ✅ ویرایش شماره دانشجویی
  ✅ ویرایش گروه و ورودی
"""
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from utils import progress_bar, get_rank, fmt_jalali_dt

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
PROFILE_EDIT_WAITING = 70  # نگه داشته برای سازگاری با bot.py


def _profile_text(user: dict, stats: dict, open_tickets: int, sub_line: str = '') -> str:
    role_map = {
        'student':       '🧑‍🎓 دانشجو',
        'content_admin': '🎓 ادمین محتوا',
        'admin':         '👑 ادمین',
    }
    role_icon = role_map.get(user.get('role', 'student'), '🧑‍🎓 دانشجو')
    rank      = get_rank(stats.get('correct_answers', 0))
    pct       = stats.get('percentage', 0)
    bar       = progress_bar(pct)
    reg_date  = fmt_jalali_dt(user.get('registered_at', ''), with_time=False) or 'نامشخص'
    uname     = f"@{user['username']}" if user.get('username') else '—'
    sid       = user.get('student_id', '') or '—'
    intake    = user.get('intake', '') or 'ثبت نشده'

    return (
        "👤 <b>پروفایل من</b>\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"📛 <b>نام:</b>  {user.get('name', '')}\n"
        f"🎓 <b>شماره دانشجویی:</b>  {sid}\n"
        f"📅 <b>ورودی:</b>  {intake}\n"
        f"👥 <b>گروه:</b>  گروه {user.get('group', '')}\n"
        f"📱 <b>یوزرنیم:</b>  {uname}\n"
        f"🎭 <b>نقش:</b>  {role_icon}\n"
        f"📅 <b>ثبت‌نام:</b>  {reg_date}\n"
        + (f"{sub_line}" if sub_line else "") +
        "\n"
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
            InlineKeyboardButton("✏️ ویرایش نام",          callback_data='profile:edit_name'),
            InlineKeyboardButton("🎓 ویرایش شماره دانشجویی", callback_data='profile:edit_sid'),
        ],
        [
            InlineKeyboardButton("👥 تغییر گروه",  callback_data='profile:edit_group'),
            InlineKeyboardButton("📅 تغییر ورودی", callback_data='profile:edit_intake'),
        ],
        # FIX جدید: دسترسی به جزئیات کامل اشتراک از پروفایل
        [InlineKeyboardButton("🧾 جزئیات اشتراک", callback_data='sub:my_status')],
        [InlineKeyboardButton("🔄 بروزرسانی",     callback_data='profile:refresh')],
        [InlineKeyboardButton("🔙 داشبورد",        callback_data='dashboard:refresh')],
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
        from subscription import sub_status_line
        sub_line = await sub_status_line(uid)
        await query.edit_message_text(
            _profile_text(user, stats, open_t, sub_line),
            parse_mode='HTML',
            reply_markup=_profile_keyboard()
        )

    # ── FIX: ویرایش نام با mode — نه ConversationHandler ──
    elif action == 'edit_name':
        context.user_data['profile_edit'] = 'name'
        context.user_data['mode']         = 'profile_edit'
        await query.edit_message_text(
            "✏️ <b>ویرایش نام</b>\n\n"
            "نام و نام خانوادگی جدید خود را بنویسید:\n"
            "<i>مثال: علی احمدی</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='profile:cancel_edit')
            ]])
        )

    elif action == 'edit_sid':
        context.user_data['profile_edit'] = 'student_id'
        context.user_data['mode']         = 'profile_edit'
        await query.edit_message_text(
            "🎓 <b>ویرایش شماره دانشجویی</b>\n\n"
            "شماره دانشجویی خود را وارد کنید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='profile:cancel_edit')
            ]])
        )

    elif action == 'cancel_edit':
        context.user_data.pop('profile_edit', None)
        context.user_data.pop('mode', None)
        user, stats, open_t = await _get_profile_data(uid)
        await query.edit_message_text(
            _profile_text(user, stats, open_t),
            parse_mode='HTML',
            reply_markup=_profile_keyboard()
        )

    elif action == 'edit_group':
        user = await db.get_user(uid)
        current_group = user.get('group', '') if user else ''
        keyboard = [
            [
                InlineKeyboardButton(
                    f"{'✅ ' if current_group == '1' else ''}1️⃣ گروه ۱",
                    callback_data='profile:set_group:1'
                ),
                InlineKeyboardButton(
                    f"{'✅ ' if current_group == '2' else ''}2️⃣ گروه ۲",
                    callback_data='profile:set_group:2'
                ),
            ],
            [InlineKeyboardButton("🔙 بازگشت", callback_data='profile:main')],
        ]
        await query.edit_message_text(
            f"👥 <b>تغییر گروه درسی</b>\n\n"
            f"گروه فعلی: <b>گروه {current_group or 'تعیین نشده'}</b>\n\n"
            "گروه جدید خود را انتخاب کنید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
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

    elif action == 'edit_intake':
        intakes = await db.get_active_intakes()
        user    = await db.get_user(uid)
        current = user.get('intake', '') if user else ''
        if not intakes:
            await query.answer("❌ هیچ ورودی‌ای تعریف نشده!", show_alert=True)
            return
        keyboard = []
        for i in intakes:
            active = current == i['code']
            keyboard.append([InlineKeyboardButton(
                f"{'✅ ' if active else ''}{i['label']}",
                callback_data=f'profile:set_intake:{i["code"]}'
            )])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='profile:main')])
        await query.edit_message_text(
            f"📅 <b>تغییر ورودی تحصیلی</b>\n\n"
            f"ورودی فعلی: <b>{current or 'ثبت نشده'}</b>\n\n"
            "ورودی جدید خود را انتخاب کنید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'set_intake' and len(parts) > 2:
        new_intake = parts[2]
        intakes    = await db.get_all_intakes()
        label      = next((i['label'] for i in intakes if i['code'] == new_intake), new_intake)
        await db.update_user(uid, {'intake': new_intake})
        await query.answer(f"✅ ورودی به {label} تغییر یافت!", show_alert=True)
        user, stats, open_t = await _get_profile_data(uid)
        await query.edit_message_text(
            _profile_text(user, stats, open_t),
            parse_mode='HTML',
            reply_markup=_profile_keyboard()
        )


# ══════════════════════════════════════════════════
#  FIX: هندلر متن پروفایل — بدون ConversationHandler
#  فراخوانی از unified_text_handler در bot.py
# ══════════════════════════════════════════════════

async def profile_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FIX: این تابع از unified_text_handler فراخوانی میشه
    وقتی mode == 'profile_edit' باشه
    """
    uid   = update.effective_user.id
    field = context.user_data.get('profile_edit', '')
    text  = update.message.text.strip()

    if not field:
        return

    if field == 'name':
        if len(text) < 3:
            await update.message.reply_text("⚠️ نام باید حداقل ۳ حرف باشد. مجدد وارد کنید:")
            return
        if len(text) > 50:
            await update.message.reply_text("⚠️ نام نباید بیشتر از ۵۰ حرف باشد:")
            return
        await db.update_user(uid, {'name': text})
        context.user_data.pop('profile_edit', None)
        context.user_data.pop('mode', None)
        await update.message.reply_text(
            f"✅ نام به <b>{text}</b> تغییر یافت!",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("👤 مشاهده پروفایل", callback_data='profile:main')
            ]])
        )

    elif field == 'student_id':
        if len(text) < 5:
            await update.message.reply_text("⚠️ شماره دانشجویی نامعتبر است. مجدد وارد کنید:")
            return
        await db.update_user(uid, {'student_id': text})
        context.user_data.pop('profile_edit', None)
        context.user_data.pop('mode', None)
        await update.message.reply_text(
            f"✅ شماره دانشجویی <code>{text}</code> ثبت شد!",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("👤 مشاهده پروفایل", callback_data='profile:main')
            ]])
        )
    else:
        context.user_data.pop('profile_edit', None)
        context.user_data.pop('mode', None)


async def show_profile_msg(update: Update):
    uid             = update.effective_user.id
    user, stats, open_t = await _get_profile_data(uid)
    if not user:
        await update.message.reply_text("❌ کاربر پیدا نشد.")
        return
    from subscription import sub_status_line
    sub_line = await sub_status_line(uid)
    await update.message.reply_text(
        _profile_text(user, stats, open_t, sub_line),
        parse_mode='HTML',
        reply_markup=_profile_keyboard()
    )

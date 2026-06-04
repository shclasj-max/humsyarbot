"""
🔔 اعلان‌ها — تنظیمات کاربری
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes
from database import db

logger = logging.getLogger(__name__)

NOTIF_ITEMS = [
    ('new_resources',  '📚 منابع جدید',       'وقتی محتوای جدید آپلود شود'),
    ('schedule',       '📅 تغییر برنامه',       'وقتی کلاس یا امتحانی تغییر کند'),
    ('exam',           '📝 یادآوری امتحان',     '۷، ۳ و ۱ روز قبل از امتحان'),
    ('daily_question', '🧪 سوال روزانه',        'هر روز صبح یک سوال تستی'),
]
_DEFAULTS = {'new_resources': True, 'schedule': True, 'exam': True, 'daily_question': False}


async def notifications_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    uid    = update.effective_user.id
    parts  = query.data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    if action in ('main', 'settings'):
        await _show_settings(query, uid)

    elif action == 'toggle' and len(parts) > 2:
        ntype   = parts[2]
        user    = await db.get_user(uid)
        s       = user.get('notification_settings', {}) if user else {}
        current = s.get(ntype, _DEFAULTS.get(ntype, True))
        await db.update_user(uid, {f'notification_settings.{ntype}': not current})
        status  = "✅ فعال" if not current else "❌ غیرفعال"
        await query.answer(f"{status} شد")
        await _show_settings(query, uid)

    elif action == 'all_on':
        settings = {f'notification_settings.{k}': True for k, _, _ in NOTIF_ITEMS}
        await db.update_user(uid, settings)
        await query.answer("✅ همه اعلان‌ها فعال شد")
        await _show_settings(query, uid)

    elif action == 'all_off':
        settings = {f'notification_settings.{k}': False for k, _, _ in NOTIF_ITEMS}
        await db.update_user(uid, settings)
        await query.answer("❌ همه اعلان‌ها غیرفعال شد")
        await _show_settings(query, uid)


async def _show_settings(query_or_msg, uid: int, edit: bool = True):
    user = await db.get_user(uid)
    s    = user.get('notification_settings', {}) if user else {}
    active = sum(1 for k, _, _ in NOTIF_ITEMS if s.get(k, _DEFAULTS.get(k, True)))

    keyboard = []
    lines    = [f"🔔 <b>تنظیمات اعلان‌ها</b>", f"فعال: {active} از {len(NOTIF_ITEMS)}", "━━━━━━━━━━━━━━━━\n"]

    for key, label, desc in NOTIF_ITEMS:
        is_on  = s.get(key, _DEFAULTS.get(key, True))
        icon   = "🔔" if is_on else "🔕"
        status = "روشن" if is_on else "خاموش"
        keyboard.append([InlineKeyboardButton(
            f"{icon} {label} — {status}",
            callback_data=f'notif:toggle:{key}'
        )])
        lines.append(f"{icon} <b>{label}</b>\n   <i>{desc}</i>")

    keyboard.append([
        InlineKeyboardButton("✅ همه روشن",   callback_data='notif:all_on'),
        InlineKeyboardButton("🔕 همه خاموش", callback_data='notif:all_off'),
    ])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='dashboard:refresh')])

    text = '\n'.join(lines)
    markup = InlineKeyboardMarkup(keyboard)

    try:
        if edit and hasattr(query_or_msg, 'edit_message_text'):
            await query_or_msg.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
        else:
            msg = query_or_msg if isinstance(query_or_msg, Message) else query_or_msg.message
            await msg.reply_text(text, parse_mode='HTML', reply_markup=markup)
    except Exception as e:
        logger.debug(f"_show_settings error: {e}")


async def show_notif_settings(message: Message, uid: int):
    """فراخوانی از message_router"""
    await _show_settings(message, uid, edit=False)

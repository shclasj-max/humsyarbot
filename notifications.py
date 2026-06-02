import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db

logger = logging.getLogger(__name__)

NOTIF_ITEMS = [
    ('new_resources',  '📚 منابع جدید',          'وقتی محتوای جدید آپلود شود'),
    ('schedule',       '📅 تغییر برنامه',          'وقتی کلاس یا امتحانی تغییر کند'),
    ('exam',           '📝 یادآوری امتحان',        '۷، ۳ و ۱ روز قبل از امتحان'),
    ('daily_question', '🧪 سوال روزانه',           'هر روز صبح یک سوال تستی'),
]


async def notifications_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    parts = query.data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    if action in ('main', 'settings'):
        await _show_settings(query, uid)

    elif action == 'toggle':
        ntype = parts[2]
        user = await db.get_user(uid)
        s = user.get('notification_settings', {}) if user else {}
        default = False if ntype == 'daily_question' else True
        current = s.get(ntype, default)
        await db.update_user(uid, {f'notification_settings.{ntype}': not current})
        await query.answer(f"{'✅ فعال' if not current else '❌ غیرفعال'} شد")
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


async def _show_settings(query, uid):
    user = await db.get_user(uid)
    s = user.get('notification_settings', {}) if user else {}
    active = sum(1 for k, _, _ in NOTIF_ITEMS if s.get(k, k != 'daily_question'))

    keyboard = []
    for key, label, desc in NOTIF_ITEMS:
        default = False if key == 'daily_question' else True
        is_on = s.get(key, default)
        icon = "🔔" if is_on else "🔕"
        status = "روشن" if is_on else "خاموش"
        keyboard.append([InlineKeyboardButton(
            f"{icon} {label} — {status}",
            callback_data=f'notif:toggle:{key}'
        )])

    keyboard.append([
        InlineKeyboardButton("✅ همه روشن", callback_data='notif:all_on'),
        InlineKeyboardButton("🔕 همه خاموش", callback_data='notif:all_off')
    ])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='dashboard:refresh')])

    lines = [f"🔔 <b>تنظیمات اعلان‌ها</b>", f"فعال: {active} از {len(NOTIF_ITEMS)}", "━━━━━━━━━━━━━━━━", ""]
    for key, label, desc in NOTIF_ITEMS:
        default = False if key == 'daily_question' else True
        is_on = s.get(key, default)
        icon = "🔔" if is_on else "🔕"
        lines.append(f"{icon} <b>{label}</b>\n   <i>{desc}</i>")

    await query.edit_message_text(
        '\n'.join(lines),
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

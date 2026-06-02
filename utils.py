from telegram import ReplyKeyboardMarkup, KeyboardButton

TERMS = ['ترم ۱', 'ترم ۲', 'ترم ۳', 'ترم ۴', 'ترم ۵']

CONTENT_TYPES = [
    ('video', '🎥 ویدیو کلاس'),
    ('ppt',   '📊 پاورپوینت'),
    ('pdf',   '📄 جزوه PDF'),
    ('note',  '📝 نکات'),
    ('test',  '🧪 تست'),
    ('voice', '🎙 ویس استاد'),
]

NOTIF_LABELS = {
    'new_resources':  '📚 منابع جدید',
    'schedule':       '📅 تغییر برنامه',
    'exam':           '📝 یادآوری امتحان',
    'daily_question': '🧪 سوال روزانه',
}


def main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🩺 داشبورد"),       KeyboardButton("📚 منابع")],
        [KeyboardButton("🧪 بانک سوال"),     KeyboardButton("❓ سوالات متداول")],
        [KeyboardButton("📅 برنامه"),         KeyboardButton("👤 پروفایل")],
        [KeyboardButton("🔔 اعلان‌ها"),       KeyboardButton("🎫 پشتیبانی")],
    ], resize_keyboard=True)


def content_admin_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🩺 داشبورد"),       KeyboardButton("📚 منابع")],
        [KeyboardButton("🧪 بانک سوال"),     KeyboardButton("❓ سوالات متداول")],
        [KeyboardButton("📅 برنامه"),         KeyboardButton("👤 پروفایل")],
        [KeyboardButton("🔔 اعلان‌ها"),       KeyboardButton("🎫 پشتیبانی")],
        [KeyboardButton("🎓 پنل محتوا")],
    ], resize_keyboard=True)


def admin_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🩺 داشبورد"),       KeyboardButton("📚 منابع")],
        [KeyboardButton("🧪 بانک سوال"),     KeyboardButton("❓ سوالات متداول")],
        [KeyboardButton("📅 برنامه"),         KeyboardButton("👤 پروفایل")],
        [KeyboardButton("🔔 اعلان‌ها"),       KeyboardButton("🎫 پشتیبانی")],
        [KeyboardButton("👨‍⚕️ پنل ادمین"),   KeyboardButton("🎓 پنل محتوا")],
    ], resize_keyboard=True)

async def cancel_handler(update, context):
    """لغو هر عملیات در حال انجام با /cancel"""
    from telegram.ext import ConversationHandler
    # پاک‌سازی تمام حالت‌های فعال
    for key in ['ca_mode', 'ca_pending_file', 'ca_content_type',
                'ca_edit_target', 'ca_edit_field',
                'ticket_mode', 'mode', 'creating_question']:
        context.user_data.pop(key, None)
    await update.message.reply_text(
        "✅ عملیات لغو شد.\n\nبرای ادامه از دکمه‌های ربات استفاده کنید.")
    return ConversationHandler.END

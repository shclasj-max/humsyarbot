"""
🛠️ Utilities — ثابت‌ها، کیبوردها، و توابع کمکی مشترک
"""
import os
import logging
from datetime import datetime
from typing import Optional, List
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ConversationHandler

logger = logging.getLogger(__name__)

ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# ══════════════════════════════════════════════════
#  ثابت‌های مشترک
# ══════════════════════════════════════════════════
TERMS = ['ترم ۱', 'ترم ۲', 'ترم ۳', 'ترم ۴', 'ترم ۵']

CONTENT_TYPES = [
    ('video', '🎥 ویدیو کلاس'),
    ('ppt',   '📊 پاورپوینت'),
    ('pdf',   '📄 جزوه PDF'),
    ('note',  '📝 نکات'),
    ('test',  '🧪 تست'),
    ('voice', '🎙 ویس استاد'),
]

CONTENT_ICONS = {k: v for k, v in CONTENT_TYPES}

NOTIF_LABELS = {
    'new_resources':  '📚 منابع جدید',
    'schedule':       '📅 تغییر برنامه',
    'exam':           '📝 یادآوری امتحان',
    'daily_question': '🧪 سوال روزانه',
}

DIFF_LABELS = {
    'easy':   'آسان 🟢',
    'medium': 'متوسط 🟡',
    'hard':   'سخت 🔴',
}

JALALI_MONTHS = [
    'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
    'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'
]
JALALI_DAYS = ['دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه', 'شنبه', 'یکشنبه']

# ══════════════════════════════════════════════════
#  کیبوردهای ReplyKeyboard
# ══════════════════════════════════════════════════

def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        [KeyboardButton("🩺 داشبورد"),     KeyboardButton("📚 منابع")],
        [KeyboardButton("🧪 بانک سوال"),   KeyboardButton("❓ سوالات متداول")],
        [KeyboardButton("📅 برنامه"),       KeyboardButton("👤 پروفایل")],
        [KeyboardButton("🔔 اعلان‌ها"),     KeyboardButton("🎫 پشتیبانی")],
    ], resize_keyboard=True)


def content_admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        [KeyboardButton("🩺 داشبورد"),     KeyboardButton("📚 منابع")],
        [KeyboardButton("🧪 بانک سوال"),   KeyboardButton("❓ سوالات متداول")],
        [KeyboardButton("📅 برنامه"),       KeyboardButton("👤 پروفایل")],
        [KeyboardButton("🔔 اعلان‌ها"),     KeyboardButton("🎫 پشتیبانی")],
        [KeyboardButton("🎓 پنل محتوا")],
    ], resize_keyboard=True)


def admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        [KeyboardButton("🩺 داشبورد"),     KeyboardButton("📚 منابع")],
        [KeyboardButton("🧪 بانک سوال"),   KeyboardButton("❓ سوالات متداول")],
        [KeyboardButton("📅 برنامه"),       KeyboardButton("👤 پروفایل")],
        [KeyboardButton("🔔 اعلان‌ها"),     KeyboardButton("🎫 پشتیبانی")],
        [KeyboardButton("👨‍⚕️ پنل ادمین"), KeyboardButton("🎓 پنل محتوا")],
    ], resize_keyboard=True)


def sub_admin_keyboard() -> ReplyKeyboardMarkup:
    """
    FIX جدید: کیبورد برای کاربرانی که نقش فرعی ادمین دارند
    (support/broadcaster) — دکمه‌های دانشجویی عادی + پنل ادمین محدود.
    """
    return ReplyKeyboardMarkup([
        [KeyboardButton("🩺 داشبورد"),     KeyboardButton("📚 منابع")],
        [KeyboardButton("🧪 بانک سوال"),   KeyboardButton("❓ سوالات متداول")],
        [KeyboardButton("📅 برنامه"),       KeyboardButton("👤 پروفایل")],
        [KeyboardButton("🔔 اعلان‌ها"),     KeyboardButton("🎫 پشتیبانی")],
        [KeyboardButton("👨‍⚕️ پنل ادمین")],
    ], resize_keyboard=True)


async def get_keyboard_for_user(user: dict, uid: int) -> ReplyKeyboardMarkup:
    """
    کیبورد مناسب بر اساس نقش کاربر — FIX جدید: حالا async است تا
    بتواند نقش‌های فرعی ادمین (admin_roles) را هم چک کند.
    """
    if uid == ADMIN_ID:
        return admin_keyboard()
    role = user.get('role', 'student') if user else 'student'
    if role == 'content_admin':
        return content_admin_keyboard()
    # FIX جدید: چک نقش فرعی (support/broadcaster/content_scoped)
    from database import db
    role_doc = await db.get_admin_role(uid)
    if role_doc:
        sub_role = role_doc.get('role', '')
        if sub_role == 'content_scoped':
            return content_admin_keyboard()
        return sub_admin_keyboard()
    return main_keyboard()


# ══════════════════════════════════════════════════
#  دکمه‌های InlineKeyboard کمکی
# ══════════════════════════════════════════════════

def back_btn(label: str = "🔙 بازگشت", cb: str = 'dashboard:refresh') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=cb)]])


def confirm_keyboard(yes_cb: str, no_cb: str,
                     yes_label: str = "✅ بله",
                     no_label: str = "❌ خیر") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(yes_label, callback_data=yes_cb),
        InlineKeyboardButton(no_label, callback_data=no_cb),
    ]])


def paginate(items: list, page: int, per_page: int = 8,
             cb_prefix: str = 'page') -> tuple:
    """برگرداندن صفحه جاری و دکمه‌های ناوبری"""
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = items[start:start + per_page]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f'{cb_prefix}:{page - 1}'))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f'{cb_prefix}:{page + 1}'))

    return chunk, nav, page, total_pages


# ══════════════════════════════════════════════════
#  توابع فرمت‌بندی
# ══════════════════════════════════════════════════

def progress_bar(pct: float, length: int = 10,
                 fill: str = '█', empty: str = '░') -> str:
    filled = int(min(pct, 100) / 100 * length)
    return fill * filled + empty * (length - filled)


def get_rank(correct_answers: int) -> str:
    if correct_answers >= 200: return "🏆 نخبه"
    if correct_answers >= 100: return "🥇 حرفه‌ای"
    if correct_answers >= 50:  return "🥈 پیشرفته"
    if correct_answers >= 20:  return "🥉 در حال رشد"
    return "🌱 تازه‌کار"


def get_level(pct: float) -> str:
    if pct >= 90: return "🏆 خبره"
    if pct >= 75: return "⭐ پیشرفته"
    if pct >= 60: return "📈 متوسط"
    if pct >= 40: return "📚 مبتدی"
    return "🌱 تازه‌کار"


def exam_countdown(days: int) -> str:
    if days < 0:  return f"({abs(days)} روز پیش)"
    if days == 0: return "🔴 امروز!"
    if days == 1: return "🔴 فردا!"
    if days <= 3: return f"🟠 {days} روز دیگر"
    if days <= 7: return f"🟡 {days} روز دیگر"
    return f"🟢 {days} روز دیگر"


# ══════════════════════════════════════════════════
#  تبدیل تاریخ میلادی به شمسی
# ══════════════════════════════════════════════════

def _to_jalali(gy: int, gm: int, gd: int) -> tuple:
    g_l = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2, gm2, gd2 = gy - 1600, gm - 1, gd - 1
    g_day_no = (365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100
                + (gy2 + 399) // 400 + g_l[gm2]
                + (1 if gm2 > 1 and ((gy2 % 4 == 0 and gy2 % 100 != 0) or gy2 % 400 == 0) else 0)
                + gd2)
    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    j_mi = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]
    jm = 11
    for i in range(11):
        if j_day_no < j_mi[i]:
            jm = i
            break
        j_day_no -= j_mi[i]
    return jy, jm + 1, j_day_no + 1


def jalali_weekday_index(date_str: str) -> int:
    """
    FIX جدید: index روز هفته با شنبه=۰ تا جمعه=۶ — برای ساخت
    جدول هفتگی برنامه کلاسی (شنبه تا جمعه) لازم است.
    پایتون weekday() دوشنبه=۰ می‌دهد؛ نگاشت به شنبه=۰:
    دوشنبه=۰→۲, سه‌شنبه=۱→۳, چهارشنبه=۲→۴, پنج‌شنبه=۳→۵,
    جمعه=۴→۶, شنبه=۵→۰, یکشنبه=۶→۱
    """
    try:
        from datetime import datetime
        y, m, d = map(int, date_str.split('-'))
        py_weekday = datetime(y, m, d).weekday()  # 0=دوشنبه ... 6=یکشنبه
        mapping = {5: 0, 6: 1, 0: 2, 1: 3, 2: 4, 3: 5, 4: 6}
        return mapping[py_weekday]
    except Exception:
        return 0


JALALI_WEEK_SAT_FIRST = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه']


def fmt_jalali(date_str: str) -> str:
    """تبدیل YYYY-MM-DD به مثلاً: ۱۵ فروردین ۱۴۰۴ (شنبه)"""
    try:
        from datetime import datetime
        y, m, d = map(int, date_str.split('-'))
        jy, jm, jd = _to_jalali(y, m, d)
        day_of_week = JALALI_DAYS[datetime(y, m, d).weekday()]
        return f"{jd} {JALALI_MONTHS[jm - 1]} {jy} ({day_of_week})"
    except Exception:
        return date_str


def days_until(date_str: str) -> int:
    try:
        from datetime import datetime
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return (d.replace(hour=0, minute=0, second=0, microsecond=0) -
                datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).days
    except Exception:
        return 0


# ══════════════════════════════════════════════════
#  هندلر لغو
# ══════════════════════════════════════════════════

async def cancel_handler(update, context):
    """لغو هر عملیات در جریان با /cancel"""
    keys_to_clear = [
        'ca_mode', 'ca_pending_file', 'ca_content_type',
        'ca_edit_target', 'ca_edit_field', 'ca_ref_lang', 'ca_ref_volume',
        'ticket_mode', 'mode', 'creating_question',
        'profile_edit', 'awaiting_search', 'search_mode',
        'edit_user', 'backup_mode',
        # FIX جدید: سیستم اشتراک
        'sub_mode', 'sub_plan_id', 'sub_final_price', 'sub_discount_code',
        'sub_reject_pid', 'suba_target_uid', 'suba_grant_role',
        'suba_plan_edit_id', 'suba_grant_list',
    ]
    for key in keys_to_clear:
        context.user_data.pop(key, None)

    await update.message.reply_text(
        "✅ عملیات لغو شد.\n\nاز دکمه‌های منو استفاده کنید.",
        reply_markup=main_keyboard()
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════
#  ارسال امن پیام (بدون کرش روی Forbidden)
# ══════════════════════════════════════════════════

async def safe_send(bot, uid: int, text: str, **kwargs) -> bool:
    """
    ارسال پیام با مدیریت خطا — برای broadcast.

    🐛 باگ واقعی که اینجا بود: این تابع هیچ فرقی بین «کاربر ربات را
    بلاک کرده» (خطای دائمی) و «تلگرام موقتاً محدودمان کرده / خطای
    شبکه‌ی گذرا» (RetryAfter / TimedOut — قابل‌حل با کمی صبر) قائل
    نمی‌شد؛ هر دو را یکسان «ناموفق» می‌شمرد و برای همیشه از دستش
    می‌داد. چون این تابع پایه‌ی broadcast_message است و آن هم پایه‌ی
    اطلاع‌رسانی برنامه/امتحان/منابع جدید در کل ربات، همین یک باگ روی
    همه‌ی کانال‌های اعلان اثر می‌گذاشت. حالا RetryAfter و خطاهای موقت
    شبکه باعث یک صبر کوتاه و تلاش مجدد می‌شوند، نه از دست رفتن پیام.
    """
    import asyncio
    from telegram.error import RetryAfter, TimedOut, NetworkError
    for attempt in range(3):
        try:
            await bot.send_message(uid, text, **kwargs)
            return True
        except RetryAfter as e:
            await asyncio.sleep(min(e.retry_after, 30) + 0.5)
            continue
        except (TimedOut, NetworkError):
            await asyncio.sleep(1.5)
            continue
        except Exception as e:
            logger.debug(f"safe_send failed for {uid}: {e}")
            return False
    return False


async def broadcast_message(bot, users: List[dict], text: str,
                            parse_mode: str = 'HTML') -> tuple:
    """ارسال همگانی — برمی‌گردونه (sent, failed)"""
    import asyncio
    sent, failed = 0, 0
    # ارسال دسته‌ای با تاخیر کم برای جلوگیری از flood
    for i, u in enumerate(users):
        ok = await safe_send(bot, u['user_id'], text, parse_mode=parse_mode)
        if ok:
            sent += 1
        else:
            failed += 1
        if i % 30 == 29:
            await asyncio.sleep(1)  # تنفس بین دسته‌ها
    return sent, failed


# ══════════════════════════════════════════════════
#  لاگ فعالیت حساس — ارسال به گروه‌های مشخص‌شده
# ══════════════════════════════════════════════════

# FIX بازطراحی کامل طبق استاندارد جدید Audit Log:
# هر پیام باید در کمتر از ۵ ثانیه نشان دهد چه کسی/چه نقشی/چه کاری/
# روی چه چیزی/چه تغییری/چه سطح اهمیتی — بدون نیاز به مراجعه به دیتابیس.

SEVERITY_META = {
    'INFO':     {'icon': '🟢', 'label': 'INFO'},
    'WARNING':  {'icon': '🟡', 'label': 'WARNING'},
    'HIGH':     {'icon': '🟠', 'label': 'HIGH'},
    'CRITICAL': {'icon': '🔴', 'label': 'CRITICAL'},
}


def new_correlation_id() -> str:
    """
    FIX طبق سند: شناسه رهگیری برای عملیات چندمرحله‌ای (مثل broadcast
    که شروع/ارسال/پایان دارد) — همه با یک correlation_id مشترک ثبت
    می‌شوند تا با get_logs_by_correlation کل فرآیند قابل پیگیری باشد.
    """
    import uuid
    return uuid.uuid4().hex[:10]


def _fa_module(module: str) -> str:
    """ترجمه نام ماژول انگلیسی (پایدار در کد) به فارسی (فقط برای نمایش)"""
    from database import db
    return db.MODULE_LABELS_FA.get(module, module)


async def send_audit_log(bot, category: str, actor_name: str, actor_id: int,
                          action: str, module: str = '', details: str = '',
                          severity: str = 'INFO', actor_role: str = '',
                          target_id: str = '', target_type: str = '',
                          target_label: str = '', before: dict = None,
                          after: dict = None, tags: list = None,
                          correlation_id: str = None) -> str:
    """
    FIX بازطراحی کامل — ساختار ثابت طبق سند:
    🛡 گزارش فعالیت → 🕒 زمان → 👤 انجام‌دهنده(نام+نقش+شناسه) →
    ⚡ عملیات → 🎯 هدف(برچسب قابل‌فهم، نه فقط ObjectId خام) →
    📂 بخش(فارسی) → 📝 جزئیات → 🔄 تغییرات → 🏷 سطح اهمیت → #تگ‌ها

    target_label: نام/متن قابل‌فهم هدف — مثلاً نام کاربر یا عنوان سوال.
    اگر خالی باشد، فقط target_id (در صورت وجود) نشان داده می‌شود.
    correlation_id: برای پیوند دادن چند رویداد یک عملیات (مثل شروع/
    پایان broadcast) — اختیاری.
    اگر گروه لاگ تنظیم نشده باشد، فقط در دیتابیس ثبت می‌شود — هرگز
    به پیوی شخصی ادمین ارشد نمی‌رود.
    """
    from database import db

    log_id = await db.log_action(
        actor_id, actor_name, actor_role, action, module, category,
        severity, target_id, target_type, target_label,
        before, after, details, tags, correlation_id
    )

    group_key = 'log_group_admin' if category == 'admin' else 'log_group_content'
    chat_id   = await db.get_setting(group_key, None)
    if not chat_id:
        return log_id

    sev_meta  = SEVERITY_META.get(severity, SEVERITY_META['INFO'])
    cat_icon  = '🛡' if category == 'admin' else '🎓'
    cat_title = 'گزارش فعالیت مدیریتی' if category == 'admin' else 'گزارش فعالیت محتوا'
    now_str   = datetime.now().strftime('%Y-%m-%d | %H:%M:%S')
    module_fa = _fa_module(module) if module else ''

    lines = [
        f"{cat_icon} <b>{cat_title}</b>",
        "",
        f"🕒 <b>زمان</b>",
        f"{now_str}",
        "",
        f"👤 <b>انجام‌دهنده</b>",
        f"• نام: {actor_name}",
        f"• نقش: {actor_role or 'نامشخص'}",
        f"• شناسه: <code>{actor_id}</code>",
        "",
        f"⚡ <b>عملیات</b>",
        f"{action}",
    ]

    if target_label or target_id:
        lines += ["", f"🎯 <b>هدف</b>"]
        if target_label:
            lines.append(f"• عنوان: {target_label}")
        if target_id:
            lines.append(f"• شناسه: <code>{target_id}</code>")

    if module_fa:
        lines += ["", f"📂 <b>بخش</b>", module_fa]

    if details:
        lines += ["", f"📝 <b>جزئیات</b>", f"{details}"]

    if before and after:
        change_lines = []
        for key in after:
            old_val = before.get(key, '—')
            new_val = after.get(key, '—')
            change_lines.append(f"• {key}: {old_val} ← {new_val}")
        if change_lines:
            lines += ["", f"🔄 <b>تغییرات</b>"] + change_lines

    lines += ["", f"🏷 <b>سطح اهمیت</b>", f"{sev_meta['icon']} {sev_meta['label']}"]

    # تگ‌های جستجو — همیشه ماژول فارسی + عملیات کوتاه، به‌علاوه تگ‌های اضافی
    auto_tags = []
    if module_fa:
        auto_tags.append(module_fa.replace(' ', '_'))
    if actor_role:
        # FIX: حذف پرانتز و کاراکترهای نامناسب برای تگ تلگرام
        clean_role = actor_role.split('(')[0].strip().replace(' ', '_')
        auto_tags.append(clean_role)
    all_tags = auto_tags + (tags or [])
    if all_tags:
        lines += ["", ' '.join(f"#{t}" for t in all_tags)]

    text = '\n'.join(lines)

    try:
        await bot.send_message(int(chat_id), text, parse_mode='HTML')
    except Exception as e:
        logger.warning(f"send_audit_log failed for chat {chat_id}: {e}")

    return log_id


# ══════════════════════════════════════════════════
#  بررسی حالت تعمیر و نگهداری (Maintenance mode)
# ══════════════════════════════════════════════════

async def is_maintenance_on() -> bool:
    """آیا ربات در حالت تعمیر و نگهداری است؟"""
    from database import db
    return bool(await db.get_setting('maintenance_mode', False))


async def maintenance_message() -> str:
    from database import db
    custom = await db.get_setting('maintenance_text', '')
    if custom:
        return custom
    return (
        "🔧 <b>ربات موقتاً در حال بروزرسانی است</b>\n\n"
        "لطفاً چند دقیقه دیگر دوباره تلاش کنید.\n"
        "از صبر شما سپاسگزاریم 🙏"
    )

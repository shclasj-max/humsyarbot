"""
📅 برنامه کلاس‌ها و امتحانات
  ✅ نمایش با تاریخ شمسی
  ✅ فیلتر گروه
  ✅ اضافه/حذف توسط ادمین
  ✅ سازگار با utils.py مرکزی
"""
import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes
from database import db
from utils import fmt_jalali, days_until, exam_countdown, ADMIN_ID

logger = logging.getLogger(__name__)

TYPE_NAMES  = {'class': '📖 کلاس', 'exam': '📝 امتحان', 'makeup': '🔄 جبرانی'}
GROUP_ICONS = {'1': '1️⃣', '2': '2️⃣', 'هر دو': '👥', '': '👥'}


def _days_label(days: int) -> str:
    if days < 0:  return f"({abs(days)} روز پیش)"
    if days == 0: return "⚠️ امروز!"
    if days == 1: return "⏰ فردا!"
    if days <= 3: return f"🔴 {days} روز دیگر"
    if days <= 7: return f"🟠 {days} روز دیگر"
    return f"🟢 {days} روز دیگر"


# ══════════════════════════════════════════════════
#  Callback اصلی
# ══════════════════════════════════════════════════

async def schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    uid    = update.effective_user.id
    parts  = query.data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    user       = await db.get_user(uid)
    user_group = user.get('group', '') if user else ''

    if action == 'main':
        await _schedule_main(query, user_group)

    elif action == 'type':
        stype        = parts[2] if len(parts) > 2 else 'class'
        group_filter = parts[3] if len(parts) > 3 else user_group
        items        = await db.get_schedules(stype=stype, group=group_filter or None)
        title        = f"{TYPE_NAMES.get(stype, stype)}"
        if group_filter:
            title += f" — گروه {group_filter}"
        await _show_schedule_list(query, items, title)

    elif action == 'upcoming':
        items    = await db.upcoming_exams(14)
        filtered = [
            i for i in items
            if i.get('group', 'هر دو') in ('هر دو', user_group, '')
        ]
        await _show_schedule_list(query, filtered, "⏳ امتحانات ۱۴ روز آینده")

    elif action == 'group_sel':
        stype = parts[2] if len(parts) > 2 else 'class'
        keyboard = [
            [InlineKeyboardButton("1️⃣ گروه ۱",     callback_data=f'schedule:type:{stype}:1')],
            [InlineKeyboardButton("2️⃣ گروه ۲",     callback_data=f'schedule:type:{stype}:2')],
            [InlineKeyboardButton("👥 هر دو گروه", callback_data=f'schedule:type:{stype}:')],
            [InlineKeyboardButton("🔙 بازگشت",     callback_data='schedule:main')],
        ]
        await query.edit_message_text(
            "👥 کدام گروه را نمایش دهم?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ── بخش ادمین ──
    elif action == 'add_type' and uid == ADMIN_ID:
        context.user_data['mode'] = 'add_schedule'
        keyboard = [
            [InlineKeyboardButton("📖 کلاس",   callback_data='schedule:add_start:class')],
            [InlineKeyboardButton("📝 امتحان", callback_data='schedule:add_start:exam')],
            [InlineKeyboardButton("🔄 جبرانی", callback_data='schedule:add_start:makeup')],
            [InlineKeyboardButton("🔙 بازگشت", callback_data='admin:main')],
        ]
        await query.edit_message_text(
            "📅 <b>افزودن برنامه</b>\n\nنوع را انتخاب کنید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'add_start' and uid == ADMIN_ID:
        stype = parts[2] if len(parts) > 2 else 'class'
        context.user_data['schedule_type'] = stype
        context.user_data['mode']          = 'add_schedule'
        context.user_data['awaiting_search'] = True
        context.user_data['search_mode']     = 'add_schedule'
        type_fa = TYPE_NAMES.get(stype, stype)
        await query.edit_message_text(
            f"📅 <b>افزودن {type_fa}</b>\n\n"
            "فرمت: <code>درس, استاد, تاریخ(شمسی YYYY/MM/DD), ساعت, مکان, گروه(اختیاری), توضیح(اختیاری)</code>\n\n"
            "مثال:\n<code>آناتومی, دکتر محمدی, 1404/01/15, 09:00, کلاس A2, هر دو</code>\n"
            "<i>گروه: ۱ یا ۲ یا هر دو (پیش‌فرض: هر دو)</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='admin:main')
            ]])
        )

    elif action == 'del_list' and uid == ADMIN_ID:
        await _show_delete_list(query)

    elif action == 'del' and uid == ADMIN_ID:
        sid = parts[2]
        await db.delete_schedule(sid)
        await query.answer("🗑 برنامه حذف شد!", show_alert=True)
        await _show_delete_list(query)


# ══════════════════════════════════════════════════
#  نمایش‌دهنده‌های UI
# ══════════════════════════════════════════════════

async def _schedule_main(query, user_group: str):
    g = user_group or ''
    g_label = f" گروه {g}" if g else ""
    keyboard = [
        [
            InlineKeyboardButton(f"📖 کلاس‌ها{g_label}", callback_data=f'schedule:type:class:{g}'),
            InlineKeyboardButton("📝 امتحانات",            callback_data=f'schedule:type:exam:{g}'),
        ],
        [
            InlineKeyboardButton("🔄 جبرانی",              callback_data=f'schedule:type:makeup:{g}'),
            InlineKeyboardButton("⏳ امتحانات نزدیک",       callback_data='schedule:upcoming'),
        ],
        [InlineKeyboardButton("👥 تغییر گروه نمایش",      callback_data='schedule:group_sel:class')],
        [InlineKeyboardButton("🔙 بازگشت",                 callback_data='dashboard:refresh')],
    ]
    await query.edit_message_text(
        f"📅 <b>برنامه و امتحانات</b>\n"
        f"{'👤 گروه شما: ' + g if g else ''}",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_schedule_list(query, items: list, title: str):
    kb_back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='schedule:main')]])

    if not items:
        await query.edit_message_text(
            f"{title}\n\n❌ موردی ثبت نشده است.",
            reply_markup=kb_back
        )
        return

    lines = [f"<b>{title}</b>\n━━━━━━━━━━━━━━━━\n"]
    for s in items:
        icon      = TYPE_NAMES.get(s.get('type', ''), '📌').split()[0]
        g_icon    = GROUP_ICONS.get(str(s.get('group', '')), '👥')
        date_str  = s.get('date', '')
        days      = days_until(date_str)
        jalali    = fmt_jalali(date_str)
        d_label   = _days_label(days)
        weekly    = " 🔁" if s.get('is_weekly') else ''
        lines.append(
            f"{icon} <b>{s.get('lesson', '')}</b>  {g_icon}{weekly}\n"
            f"   📅 {jalali}  |  {d_label}\n"
            f"   ⏰ {s.get('time', '')}  |  👨‍🏫 {s.get('teacher', '')}\n"
            f"   📍 {s.get('location', '')}\n"
            + (f"   📝 {s['notes']}\n" if s.get('notes') else '')
        )

    text = '\n'.join(lines)
    if len(text) > 4000:
        text = text[:3900] + "\n\n<i>... موارد بیشتر موجود است</i>"

    await query.edit_message_text(text, parse_mode='HTML', reply_markup=kb_back)


async def _show_delete_list(query):
    items    = await db.get_schedules(upcoming=False)
    keyboard = []
    for s in items[:20]:
        sid   = str(s['_id'])
        label = f"🗑 {s.get('type','')[:1].upper()} | {s.get('lesson','')} | {s.get('date','')}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f'schedule:del:{sid}')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:main')])
    await query.edit_message_text(
        "🗑 <b>حذف برنامه</b>\n\nانتخاب کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ══════════════════════════════════════════════════
#  فراخوانی از message_router (دکمه کیبورد)
# ══════════════════════════════════════════════════

async def show_schedule_main(message: Message, uid: int, user: dict):
    user_group = user.get('group', '') if user else ''
    g = user_group or ''
    g_label = f" گروه {g}" if g else ""
    keyboard = [
        [
            InlineKeyboardButton(f"📖 کلاس‌ها{g_label}", callback_data=f'schedule:type:class:{g}'),
            InlineKeyboardButton("📝 امتحانات",            callback_data=f'schedule:type:exam:{g}'),
        ],
        [
            InlineKeyboardButton("🔄 جبرانی",              callback_data=f'schedule:type:makeup:{g}'),
            InlineKeyboardButton("⏳ امتحانات نزدیک",       callback_data='schedule:upcoming'),
        ],
        [InlineKeyboardButton("👥 تغییر گروه نمایش",      callback_data='schedule:group_sel:class')],
    ]
    await message.reply_text(
        f"📅 <b>برنامه و امتحانات</b>\n"
        f"{'👤 گروه شما: ' + g if g else ''}",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ══════════════════════════════════════════════════
#  پارسر افزودن برنامه (از message_router)
# ══════════════════════════════════════════════════

def _jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple:
    """تبدیل شمسی به میلادی برای ذخیره در دیتابیس"""
    jy -= 979
    jm -= 1
    jd -= 1
    j_day_no = 365 * jy + (jy // 33) * 8 + (jy % 33 + 3) // 4
    for i in range(jm):
        j_day_no += [31,31,31,31,31,31,30,30,30,30,30,29][i]
    j_day_no += jd
    g_day_no = j_day_no + 79
    gy = 1600 + 400 * (g_day_no // 146097)
    g_day_no %= 146097
    leap = True
    if g_day_no >= 36525:
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)
        g_day_no %= 36524
        leap = g_day_no >= 365
        if leap: g_day_no += 1
    gy += 4 * (g_day_no // 1461)
    g_day_no %= 1461
    if g_day_no >= 366:
        leap = False
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365
    g_l = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    for i, days in enumerate(g_l):
        if g_day_no < days:
            gm = i + 1
            break
        g_day_no -= days
    return gy, gm, g_day_no + 1


def _parse_jalali_date(date_str: str) -> str:
    """تبدیل 1404/01/15 یا 1404-01-15 به YYYY-MM-DD میلادی"""
    date_str = date_str.strip().replace('/', '-')
    parts = date_str.split('-')
    if len(parts) == 3:
        jy, jm, jd = int(parts[0]), int(parts[1]), int(parts[2])
        if jy > 1400:  # تاریخ شمسی
            gy, gm, gd = _jalali_to_gregorian(jy, jm, jd)
            return f"{gy:04d}-{gm:02d}-{gd:02d}"
    return date_str  # اگه میلادی بود برگردون


async def handle_add_schedule_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پارس متن افزودن برنامه توسط ادمین — با تاریخ شمسی"""
    from utils import broadcast_message
    stype = context.user_data.pop('schedule_type', 'class')
    text  = update.message.text.strip()

    try:
        parts = [p.strip() for p in text.split(',')]
        if len(parts) < 5:
            raise ValueError("حداقل ۵ فیلد لازم است")
        lesson, teacher, raw_date, time_str, location = parts[:5]
        group = parts[5].strip() if len(parts) > 5 else 'هر دو'
        notes = parts[6].strip() if len(parts) > 6 else ''

        # تبدیل تاریخ شمسی به میلادی
        date = _parse_jalali_date(raw_date)
        from datetime import datetime as dt
        dt.strptime(date, '%Y-%m-%d')  # اعتبارسنجی

        # نرمال‌سازی گروه
        if group not in ('1', '2', 'هر دو', ''):
            group = 'هر دو'

        await db.add_schedule(stype, lesson, teacher, date, time_str, location, notes, group)

        ntype   = 'exam' if stype == 'exam' else 'schedule'
        users   = await db.notif_users(ntype)
        type_fa = TYPE_NAMES.get(stype, stype)
        g_label = f" | گروه {group}" if group not in ('هر دو', '') else ''
        msg = (
            f"📅 <b>{type_fa} جدید:</b> {lesson}\n"
            f"👨‍🏫 {teacher}  |  {fmt_jalali(date)} ساعت {time_str}\n"
            f"📍 {location}{g_label}"
        )
        sent, _ = await broadcast_message(context.bot, users, msg)

        for k in ('awaiting_search', 'search_mode', 'mode'):
            context.user_data.pop(k, None)

        await update.message.reply_text(
            f"✅ <b>{type_fa} اضافه شد!</b>\n"
            f"📌 {lesson}  |  {fmt_jalali(date)} {time_str}{g_label}\n"
            f"🔔 {sent} نفر مطلع شدند.",
            parse_mode='HTML'
        )
    except ValueError as e:
        await update.message.reply_text(
            f"❌ خطا: {e}\n\n"
            "فرمت صحیح:\n"
            "<code>درس, استاد, 1404/01/15, HH:MM, مکان, گروه, توضیح</code>\n"
            "<i>گروه: ۱ یا ۲ یا هر دو</i>",
            parse_mode='HTML'
        )

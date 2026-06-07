"""
📅 برنامه کلاس‌ها و امتحانات
  ✅ تاریخ شمسی ورودی و نمایش
  ✅ فیکس باگ کاما فارسی (٫ → ,)
  ✅ فیلتر گروه
  ✅ اضافه/حذف توسط ادمین
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


def _normalize_text(text: str) -> str:
    """
    FIX: نرمال‌سازی متن ورودی
    - کاما فارسی ٫ → کاما انگلیسی ,
    - ویرگول فارسی ، → کاما انگلیسی ,
    - فاصله‌های اضافه حذف
    """
    text = text.replace('٫', ',').replace('،', ',')
    # حذف فاصله‌های اضافه اطراف کاما
    import re
    text = re.sub(r'\s*,\s*', ', ', text)
    return text.strip()


def _jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple:
    """تبدیل شمسی به میلادی"""
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
    for i, days_in_m in enumerate(g_l):
        if g_day_no < days_in_m:
            gm = i + 1
            break
        g_day_no -= days_in_m
    return gy, gm, g_day_no + 1


def _parse_jalali_date(date_str: str) -> str:
    """
    تبدیل تاریخ شمسی به میلادی برای ذخیره در دیتابیس
    پشتیبانی از: 1404/01/15 یا 1404-01-15
    """
    date_str = date_str.strip().replace('/', '-').replace('\\', '-')
    # حذف کاراکترهای نامرئی
    date_str = ''.join(c for c in date_str if c.isprintable()).strip()
    parts_d = date_str.split('-')
    if len(parts_d) == 3:
        try:
            jy, jm, jd = int(parts_d[0]), int(parts_d[1]), int(parts_d[2])
            if jy > 1400:  # قطعاً شمسی
                gy, gm, gd = _jalali_to_gregorian(jy, jm, jd)
                return f"{gy:04d}-{gm:02d}-{gd:02d}"
            elif jy > 2000:  # قطعاً میلادی
                return date_str
        except ValueError:
            pass
    return date_str


def _is_valid_time(time_str: str) -> bool:
    """بررسی فرمت ساعت HH:MM"""
    try:
        parts_t = time_str.strip().split(':')
        if len(parts_t) != 2:
            return False
        h, m = int(parts_t[0]), int(parts_t[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except Exception:
        return False


def _is_date_string(s: str) -> bool:
    """تشخیص اینکه آیا رشته تاریخ است یا نه"""
    s = s.strip().replace('/', '-')
    parts_d = s.split('-')
    if len(parts_d) != 3:
        return False
    try:
        y = int(parts_d[0])
        return y > 1000  # شمسی یا میلادی
    except Exception:
        return False


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
        title        = TYPE_NAMES.get(stype, stype)
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

    elif action == 'add_type' and uid == ADMIN_ID:
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
        type_fa = TYPE_NAMES.get(stype, stype)
        await query.edit_message_text(
            f"📅 <b>افزودن {type_fa}</b>\n\n"
            "فرمت ورودی:\n"
            "<code>درس, استاد, تاریخ شمسی, ساعت, مکان, گروه, توضیح</code>\n\n"
            "📌 مثال:\n"
            "<code>آناتومی, دکتر محمدی, 1404/01/15, 09:00, کلاس A2, هر دو</code>\n\n"
            "⚠️ نکات:\n"
            "• تاریخ باید شمسی باشد: <code>1404/01/15</code>\n"
            "• ساعت: <code>09:00</code> یا <code>14:30</code>\n"
            "• گروه: <code>۱</code> یا <code>۲</code> یا <code>هر دو</code> (اختیاری)\n"
            "• از کاما انگلیسی <code>,</code> استفاده کنید",
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
#  UI
# ══════════════════════════════════════════════════

async def _schedule_main(query, user_group: str):
    g = user_group or ''
    g_label = f" گروه {g}" if g else ""
    keyboard = [
        [
            InlineKeyboardButton(f"📖 کلاس‌ها{g_label}", callback_data=f'schedule:type:class:{g}'),
            InlineKeyboardButton("📝 امتحانات",           callback_data=f'schedule:type:exam:{g}'),
        ],
        [
            InlineKeyboardButton("🔄 جبرانی",             callback_data=f'schedule:type:makeup:{g}'),
            InlineKeyboardButton("⏳ امتحانات نزدیک",      callback_data='schedule:upcoming'),
        ],
        [InlineKeyboardButton("👥 تغییر گروه نمایش",     callback_data='schedule:group_sel:class')],
        [InlineKeyboardButton("🔙 بازگشت",                callback_data='dashboard:refresh')],
    ]
    await query.edit_message_text(
        f"📅 <b>برنامه و امتحانات</b>\n"
        f"{'👤 گروه شما: ' + g if g else ''}",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_schedule_list(query, items: list, title: str):
    kb_back = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 بازگشت", callback_data='schedule:main')
    ]])

    if not items:
        await query.edit_message_text(
            f"{title}\n\n❌ موردی ثبت نشده است.",
            reply_markup=kb_back
        )
        return

    lines = [f"<b>{title}</b>\n━━━━━━━━━━━━━━━━\n"]
    for s in items:
        icon     = TYPE_NAMES.get(s.get('type', ''), '📌').split()[0]
        g_icon   = GROUP_ICONS.get(str(s.get('group', '')), '👥')
        date_str = s.get('date', '')
        days     = days_until(date_str)
        jalali   = fmt_jalali(date_str)
        d_label  = _days_label(days)
        weekly   = " 🔁" if s.get('is_weekly') else ''
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
        sid  = str(s['_id'])
        jd   = fmt_jalali(s.get('date', ''))
        tp   = TYPE_NAMES.get(s.get('type', ''), '').split()[0]
        label = f"🗑 {tp} | {s.get('lesson','')} | {jd}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f'schedule:del:{sid}')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:main')])
    await query.edit_message_text(
        "🗑 <b>حذف برنامه</b>\n\nانتخاب کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_schedule_main(message: Message, uid: int, user: dict):
    user_group = user.get('group', '') if user else ''
    g = user_group or ''
    g_label = f" گروه {g}" if g else ""
    keyboard = [
        [
            InlineKeyboardButton(f"📖 کلاس‌ها{g_label}", callback_data=f'schedule:type:class:{g}'),
            InlineKeyboardButton("📝 امتحانات",           callback_data=f'schedule:type:exam:{g}'),
        ],
        [
            InlineKeyboardButton("🔄 جبرانی",             callback_data=f'schedule:type:makeup:{g}'),
            InlineKeyboardButton("⏳ امتحانات نزدیک",      callback_data='schedule:upcoming'),
        ],
        [InlineKeyboardButton("👥 تغییر گروه نمایش",     callback_data='schedule:group_sel:class')],
    ]
    await message.reply_text(
        f"📅 <b>برنامه و امتحانات</b>\n"
        f"{'👤 گروه شما: ' + g if g else ''}",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ══════════════════════════════════════════════════
#  پارسر افزودن برنامه — FIX کامل
# ══════════════════════════════════════════════════

async def handle_add_schedule_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    پارس متن افزودن برنامه توسط ادمین
    FIX: نرمال‌سازی کاما فارسی + تشخیص هوشمند فیلدها
    """
    from utils import broadcast_message
    stype = context.user_data.pop('schedule_type', 'class')
    raw   = update.message.text.strip()

    # FIX: نرمال‌سازی کاما فارسی و ویرگول
    raw = _normalize_text(raw)

    try:
        parts = [p.strip() for p in raw.split(',')]

        if len(parts) < 5:
            raise ValueError(
                f"تعداد فیلدها کافی نیست ({len(parts)} فیلد دریافت شد، حداقل ۵ نیاز است)"
            )

        # FIX: تشخیص هوشمند — اگه فیلد سوم تاریخ نبود، بگرد دنبال تاریخ
        lesson  = parts[0]
        teacher = parts[1]

        # پیدا کردن تاریخ در بین فیلدها
        date_idx = None
        for i in range(2, min(4, len(parts))):
            if _is_date_string(parts[i]):
                date_idx = i
                break

        if date_idx is None:
            raise ValueError(
                "تاریخ شمسی پیدا نشد!\n"
                "مثال: <code>1404/03/18</code>\n"
                "توجه: از کاما انگلیسی <code>,</code> استفاده کنید، نه فارسی <code>٫</code>"
            )

        raw_date = parts[date_idx]
        date     = _parse_jalali_date(raw_date)

        # اعتبارسنجی تاریخ میلادی تولیدشده
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f"تاریخ نامعتبر: {raw_date}")

        # بقیه فیلدها
        remaining = parts[date_idx + 1:]
        if len(remaining) < 2:
            raise ValueError("ساعت و مکان الزامی هستند")

        # FIX: پیدا کردن ساعت
        time_str = None
        time_idx = None
        for i, r in enumerate(remaining):
            if _is_valid_time(r):
                time_str = r.strip()
                time_idx = i
                break

        if not time_str:
            # شاید ساعت قبل از تاریخ بود — اگه هنوز نداریم خطا
            raise ValueError(
                f"ساعت معتبر پیدا نشد! فرمت صحیح: <code>09:00</code>"
            )

        after_time = remaining[time_idx + 1:]
        location   = after_time[0].strip() if after_time else 'اعلام نشده'
        group      = after_time[1].strip() if len(after_time) > 1 else 'هر دو'
        notes      = after_time[2].strip() if len(after_time) > 2 else ''

        # نرمال‌سازی گروه
        group_map = {
            '1': '1', '۱': '1', 'گروه ۱': '1', 'گروه 1': '1',
            '2': '2', '۲': '2', 'گروه ۲': '2', 'گروه 2': '2',
            'هر دو': 'هر دو', 'هردو': 'هر دو', 'all': 'هر دو', '': 'هر دو',
        }
        group = group_map.get(group, 'هر دو')

        await db.add_schedule(
            stype, lesson, teacher, date, time_str, location, notes, group
        )

        # اطلاع‌رسانی
        ntype   = 'exam' if stype == 'exam' else 'schedule'
        users   = await db.notif_users(ntype)
        type_fa = TYPE_NAMES.get(stype, stype)
        g_label = f" | گروه {group}" if group not in ('هر دو', '') else ''
        jalali_display = fmt_jalali(date)
        notif_msg = (
            f"📅 <b>{type_fa} جدید</b>\n\n"
            f"📚 {lesson}\n"
            f"👨‍🏫 {teacher}\n"
            f"📅 {jalali_display}  ⏰ {time_str}\n"
            f"📍 {location}{g_label}"
        )
        sent, _ = await broadcast_message(context.bot, users, notif_msg)

        for k in ('awaiting_search', 'search_mode', 'mode', 'schedule_type'):
            context.user_data.pop(k, None)

        await update.message.reply_text(
            f"✅ <b>{type_fa} با موفقیت اضافه شد!</b>\n\n"
            f"📚 {lesson}\n"
            f"👨‍🏫 {teacher}\n"
            f"📅 {jalali_display}  ⏰ {time_str}\n"
            f"📍 {location}{g_label}\n\n"
            f"🔔 <b>{sent} نفر</b> مطلع شدند.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📅 مشاهده برنامه", callback_data=f'schedule:type:{stype}:'),
                InlineKeyboardButton("🔙 پنل ادمین",      callback_data='admin:main'),
            ]])
        )

    except ValueError as e:
        for k in ('awaiting_search', 'search_mode', 'mode', 'schedule_type'):
            context.user_data.pop(k, None)
        await update.message.reply_text(
            f"❌ <b>خطا:</b> {e}\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📋 <b>فرمت صحیح:</b>\n"
            "<code>درس, استاد, 1404/MM/DD, HH:MM, مکان, گروه, توضیح</code>\n\n"
            "📌 <b>مثال:</b>\n"
            "<code>آناتومی, دکتر محمدی, 1404/01/15, 09:00, کلاس A2, هر دو</code>\n\n"
            "⚠️ <b>مهم:</b> از کاما انگلیسی <code>,</code> استفاده کنید",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 تلاش مجدد", callback_data=f'schedule:add_start:{stype}'),
                InlineKeyboardButton("❌ لغو",         callback_data='admin:main'),
            ]])
        )

"""برنامه کلاس‌ها و امتحانات — با تاریخ شمسی و گروه‌بندی"""
import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db

logger = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# ─── تبدیل تاریخ میلادی به شمسی ───
def _to_jalali(gy, gm, gd):
    g_l = [0,31,59,90,120,151,181,212,243,273,304,334]
    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1
    g_day_no = (365*gy2 + (gy2+3)//4 - (gy2+99)//100 + (gy2+399)//400
                + g_l[gm2] + (1 if gm2 > 1 and ((gy2%4==0 and gy2%100!=0) or gy2%400==0) else 0)
                + gd2)
    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33*j_np + 4*(j_day_no//1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no-1)//365
        j_day_no = (j_day_no-1)%365
    j_mi = [31,31,31,31,31,31,30,30,30,30,30,29]
    jm = 11
    for i in range(11):
        if j_day_no < j_mi[i]:
            jm = i
            break
        j_day_no -= j_mi[i]
    return jy, jm+1, j_day_no+1

JALALI_MONTHS = ['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور',
                 'مهر','آبان','آذر','دی','بهمن','اسفند']
JALALI_DAYS   = ['دوشنبه','سه‌شنبه','چهارشنبه','پنج‌شنبه','جمعه','شنبه','یکشنبه']

def fmt_jalali(date_str):
    """تبدیل YYYY-MM-DD به مثلاً: ۱۵ فروردین ۱۴۰۴"""
    try:
        parts = date_str.split('-')
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        jy, jm, jd = _to_jalali(y, m, d)
        dt = datetime(y, m, d)
        day_of_week = JALALI_DAYS[dt.weekday()]
        return f"{jd} {JALALI_MONTHS[jm-1]} {jy} ({day_of_week})"
    except:
        return date_str

def days_until(date_str):
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return (d.replace(hour=0,minute=0,second=0,microsecond=0) -
                datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)).days
    except:
        return 0

def days_label(days):
    if days < 0:  return f"({abs(days)} روز پیش)"
    if days == 0: return "⚠️ امروز!"
    if days == 1: return "⏰ فردا!"
    if days <= 3: return f"🔴 {days} روز دیگر"
    if days <= 7: return f"🟠 {days} روز دیگر"
    return f"🟢 {days} روز دیگر"


async def schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    uid    = update.effective_user.id
    data   = query.data
    parts  = data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    # گروه کاربر
    user = await db.get_user(uid)
    user_group = user.get('group', '') if user else ''

    if action == 'main':
        await _schedule_main(query, user_group)

    elif action == 'type':
        stype = parts[2]
        group_filter = parts[3] if len(parts) > 3 else user_group
        names = {'class': '📖 کلاس‌ها', 'exam': '📝 امتحانات', 'makeup': '🔄 جبرانی'}
        items = await db.get_schedules(stype=stype, group=group_filter)
        title = f"{names.get(stype, stype)} — گروه {group_filter}" if group_filter else names.get(stype, stype)
        await _show_schedule_list(query, items, title)

    elif action == 'upcoming':
        items = await db.upcoming_exams(14)
        # فیلتر گروه
        filtered = [i for i in items if i.get('group','هر دو') in ('هر دو', user_group, '')]
        await _show_schedule_list(query, filtered, "⏳ امتحانات ۱۴ روز آینده")

    elif action == 'group_sel':
        stype = parts[2]
        keyboard = [
            [InlineKeyboardButton(f"1️⃣ گروه ۱", callback_data=f'schedule:type:{stype}:1')],
            [InlineKeyboardButton(f"2️⃣ گروه ۲", callback_data=f'schedule:type:{stype}:2')],
            [InlineKeyboardButton(f"👥 هر دو گروه", callback_data=f'schedule:type:{stype}:')],
            [InlineKeyboardButton("🔙 بازگشت", callback_data='schedule:main')],
        ]
        await query.edit_message_text("👥 کدام گروه را نمایش دهم?",
                                       reply_markup=InlineKeyboardMarkup(keyboard))


async def _schedule_main(query, user_group):
    group_icon = f"(گروه {user_group})" if user_group else ""
    keyboard = [
        [InlineKeyboardButton(f"📖 کلاس‌ها {group_icon}", callback_data=f'schedule:type:class:{user_group}'),
         InlineKeyboardButton(f"📝 امتحانات",              callback_data=f'schedule:type:exam:{user_group}')],
        [InlineKeyboardButton("🔄 جبرانی",                 callback_data=f'schedule:type:makeup:{user_group}'),
         InlineKeyboardButton("⏳ امتحانات نزدیک",          callback_data='schedule:upcoming')],
        [InlineKeyboardButton("👥 تغییر گروه نمایش",       callback_data='schedule:group_sel:class')],
    ]
    await query.edit_message_text(
        f"📅 <b>برنامه و امتحانات</b>\n"
        f"{'👤 گروه شما: ' + user_group if user_group else ''}",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_schedule_list(query, items, title):
    if not items:
        await query.edit_message_text(
            f"{title}\n\n❌ موردی ثبت نشده است.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='schedule:main')]])
        )
        return

    type_icons = {'class': '📖', 'exam': '📝', 'makeup': '🔄'}
    group_icons = {'1': '1️⃣', '2': '2️⃣', 'هر دو': '👥', '': '👥'}
    text = f"{title}\n━━━━━━━━━━━━━━━━\n\n"

    for s in items:
        icon       = type_icons.get(s.get('type', ''), '📌')
        g_icon     = group_icons.get(str(s.get('group', '')), '👥')
        date_str   = s.get('date', '')
        days       = days_until(date_str)
        jalali_str = fmt_jalali(date_str)
        d_label    = days_label(days)
        weekly_tag = " 🔁 هفتگی" if s.get('is_weekly') else ''
        text += (
            f"{icon} <b>{s.get('lesson','')}</b>  {g_icon}{weekly_tag}\n"
            f"   📅 {jalali_str}  |  {d_label}\n"
            f"   ⏰ {s.get('time','')}  |  👨‍🏫 {s.get('teacher','')}\n"
            f"   📍 {s.get('location','')}\n"
        )
        if s.get('notes'):
            text += f"   📝 {s['notes']}\n"
        text += "\n"

    if len(text) > 4000:
        text = text[:3900] + "\n\n... (ادامه در پیام بعدی)"

    await query.edit_message_text(
        text, parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='schedule:main')]])
    )

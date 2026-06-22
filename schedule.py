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
from bson import ObjectId
from utils import (fmt_jalali, days_until, exam_countdown, ADMIN_ID,
                    jalali_weekday_index, JALALI_WEEK_SAT_FIRST, send_audit_log)

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

    elif action == 'weekly_chart':
        await _show_weekly_chart(query, user_group)

    # ══════════════════════════════════════════════
    # FIX جدید: فلوی پیش‌نمایش قبل از ثبت برنامه
    # ══════════════════════════════════════════════
    elif action == 'flex' and uid == ADMIN_ID:
        flex_type = parts[2] if len(parts) > 2 else 'fixed'
        p = context.user_data.get('pending_schedule', {})
        if not p:
            await query.edit_message_text("❌ اطلاعاتی برای پیش‌نمایش پیدا نشد.")
            return
        p['flex_type'] = flex_type
        context.user_data['pending_schedule'] = p
        await _show_schedule_preview(query, context, edit=True)

    elif action == 'confirm_add' and uid == ADMIN_ID:
        await _finalize_schedule_add(query, context)

    elif action == 'edit_pending' and uid == ADMIN_ID:
        p = context.user_data.get('pending_schedule', {})
        stype = p.get('stype', 'class')
        context.user_data.pop('pending_schedule', None)
        context.user_data['schedule_type'] = stype
        context.user_data['mode'] = 'add_schedule'
        type_fa = TYPE_NAMES.get(stype, stype)
        await query.edit_message_text(
            f"✏️ <b>ویرایش {type_fa}</b>\n\n"
            "اطلاعات را دوباره با فرمت زیر بفرستید:\n"
            "<code>درس, استاد, 1404/MM/DD, HH:MM, مکان, گروه, توضیح</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='admin:main')
            ]])
        )

    elif action == 'cancel_pending' and uid == ADMIN_ID:
        context.user_data.pop('pending_schedule', None)
        context.user_data.pop('mode', None)
        await query.edit_message_text(
            "❌ لغو شد. هیچ موردی ثبت نشد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 پنل ادمین", callback_data='admin:main')
            ]])
        )

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
        # FIX جدید: گرفتن اطلاعات قبل از حذف برای ثبت در لاگ
        deleted_item = await db.schedules.find_one({'_id': ObjectId(sid)})
        await db.delete_schedule(sid)
        await query.answer("🗑 برنامه حذف شد!", show_alert=True)
        if deleted_item:
            admin_user = await db.get_user(uid)
            actor_name = admin_user.get('name', 'ادمین') if admin_user else 'ادمین'
            type_fa = TYPE_NAMES.get(deleted_item.get('type',''), '')
            await send_audit_log(
                context.bot, 'admin', actor_name, uid,
                f"حذف {type_fa}", module='Schedules', severity='WARNING',
                target_id=sid,
                details=f"{deleted_item.get('lesson','')} — {fmt_jalali(deleted_item.get('date',''))}"
            )
        await _show_delete_list(query)

    # ══════════════════════════════════════════════
    # FIX جدید: اعلام تغییر زمان برای کلاس منعطف
    # ══════════════════════════════════════════════
    elif action == 'flex_list' and uid == ADMIN_ID:
        await _show_flex_list(query)

    elif action == 'flex_change' and uid == ADMIN_ID:
        sid = parts[2]
        context.user_data['flex_change_sid'] = sid
        context.user_data['mode'] = 'flex_time_change'
        await query.edit_message_text(
            "🔄 <b>اعلام تغییر زمان کلاس</b>\n\n"
            "زمان جدید را با فرمت زیر بفرستید:\n"
            "<code>1404/MM/DD, HH:MM, توضیح کوتاه (اختیاری)</code>\n\n"
            "📌 مثال:\n"
            "<code>1404/02/10, 14:00, به دلیل تعطیلی استاد</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='schedule:flex_list')
            ]])
        )


# ══════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════

async def _schedule_main(query, user_group: str):
    g = user_group or ''
    g_label = f" گروه {g}" if g else ""
    keyboard = [
        [InlineKeyboardButton("📊 جدول هفتگی کلاس‌ها", callback_data='schedule:weekly_chart')],
        [
            InlineKeyboardButton(f"📖 لیست کلاس‌ها{g_label}", callback_data=f'schedule:type:class:{g}'),
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


async def _show_weekly_chart(query, user_group: str):
    """
    FIX جدید: نمایش برنامه کلاسی هفته جاری به‌صورت جدول شنبه تا جمعه.
    کلاس‌های منعطف (flex_type='flexible') با برچسب «زمان متغیر» و
    آخرین زمان اعلام‌شده نشان داده می‌شوند.
    """
    from datetime import datetime, timedelta
    today = datetime.now()
    # شروع هفته جاری از شنبه (نزدیک‌ترین شنبه قبل یا امروز)
    py_wd = today.weekday()  # 0=دوشنبه...6=یکشنبه
    days_since_sat = {5: 0, 6: 1, 0: 2, 1: 3, 2: 4, 3: 5, 4: 6}[py_wd]
    week_start = today - timedelta(days=days_since_sat)
    week_end   = week_start + timedelta(days=6)

    start_str = week_start.strftime('%Y-%m-%d')
    end_str   = week_end.strftime('%Y-%m-%d')

    all_classes = await db.get_schedules(stype='class', upcoming=False, group=user_group or None)
    week_classes = [c for c in all_classes if start_str <= c.get('date', '') <= end_str]

    # گروه‌بندی بر اساس روز هفته (۰=شنبه ... ۶=جمعه)
    by_day = {i: [] for i in range(7)}
    for c in week_classes:
        idx = jalali_weekday_index(c.get('date', ''))
        by_day[idx].append(c)

    lines = [
        "📊 <b>جدول هفتگی کلاس‌ها</b>",
        f"🗓 {fmt_jalali(start_str).split('(')[0].strip()} تا {fmt_jalali(end_str).split('(')[0].strip()}",
        "━━━━━━━━━━━━━━━━",
    ]
    has_any = False
    for i, day_name in enumerate(JALALI_WEEK_SAT_FIRST):
        items = sorted(by_day[i], key=lambda x: x.get('time', ''))
        lines.append(f"\n📅 <b>{day_name}</b>")
        if not items:
            lines.append("   <i>کلاسی ندارید</i>")
            continue
        has_any = True
        for c in items:
            flex = c.get('flex_type', 'fixed')
            if flex == 'flexible':
                time_part = f"🔄 زمان متغیر — آخرین اعلام: {c.get('time', '')}"
                if c.get('flex_note'):
                    time_part += f" ({c['flex_note']})"
            else:
                time_part = f"⏰ {c.get('time', '')}"
            lines.append(
                f"   • <b>{c.get('lesson','')}</b>\n"
                f"     {time_part}\n"
                f"     👨‍🏫 {c.get('teacher','')}  |  📍 {c.get('location','')}"
            )
    if not has_any:
        lines.append("\n<i>هیچ کلاسی برای این هفته ثبت نشده است.</i>")

    text = '\n'.join(lines)
    if len(text) > 4000:
        text = text[:3900] + "\n\n<i>... برای دیدن کامل، از لیست کلاس‌ها استفاده کنید</i>"

    await query.edit_message_text(
        text, parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 بازگشت", callback_data='schedule:main')
        ]])
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


async def _show_flex_list(query):
    """
    FIX جدید: لیست کلاس‌های منعطف برای اعلام تغییر زمان.
    """
    all_items = await db.get_schedules(upcoming=True)
    flex_items = [s for s in all_items if s.get('flex_type') == 'flexible']
    if not flex_items:
        await query.edit_message_text(
            "🔄 <b>کلاس‌های منعطف</b>\n\n"
            "❌ هیچ کلاس منعطفی ثبت نشده.\n"
            "<i>برای ثبت کلاس منعطف، هنگام افزودن برنامه، نوع زمان‌بندی را «منعطف» انتخاب کنید.</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='admin:main')
            ]])
        )
        return
    keyboard = []
    for s in flex_items[:20]:
        sid = str(s['_id'])
        jd  = fmt_jalali(s.get('date', ''))
        label = f"🔄 {s.get('lesson','')} | {jd} {s.get('time','')}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f'schedule:flex_change:{sid}')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:main')])
    await query.edit_message_text(
        "🔄 <b>اعلام تغییر زمان — انتخاب کلاس</b>\n\n"
        "کلاسی که زمانش تغییر کرده را انتخاب کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_flex_time_change_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    FIX جدید: پردازش متن زمان جدید برای کلاس منعطف + نوتیف فوری
    به همه‌ی دانشجویانی که نوتیف 'schedule' را روشن دارند.
    """
    from utils import broadcast_message
    sid = context.user_data.pop('flex_change_sid', None)
    context.user_data.pop('mode', None)
    raw = _normalize_text(update.message.text.strip())

    if not sid:
        await update.message.reply_text("❌ خطا — دوباره تلاش کنید.")
        return

    parts = [p.strip() for p in raw.split(',')]
    if len(parts) < 2:
        await update.message.reply_text(
            "❌ فرمت اشتباه!\nمثال: <code>1404/02/10, 14:00, توضیح</code>",
            parse_mode='HTML'
        )
        return

    new_date_raw = parts[0]
    new_time     = parts[1]
    note         = parts[2] if len(parts) > 2 else ''

    if not _is_valid_time(new_time):
        await update.message.reply_text("❌ فرمت ساعت اشتباه است. مثال: 14:00")
        return

    new_date = _parse_jalali_date(new_date_raw)
    try:
        datetime.strptime(new_date, '%Y-%m-%d')
    except ValueError:
        await update.message.reply_text("❌ تاریخ نامعتبر است.")
        return

    schedule_doc = await db.schedules.find_one({'_id': ObjectId(sid)})
    if not schedule_doc:
        await update.message.reply_text("❌ این کلاس پیدا نشد.")
        return

    ok = await db.update_schedule_time(sid, new_date, new_time, note)
    if not ok:
        await update.message.reply_text("❌ خطا در ذخیره تغییر.")
        return

    jalali_display = fmt_jalali(new_date)
    lesson  = schedule_doc.get('lesson', '')
    teacher = schedule_doc.get('teacher', '')
    location = schedule_doc.get('location', '')
    group    = schedule_doc.get('group', 'هر دو')

    notif_msg = (
        f"🔄 <b>تغییر زمان کلاس</b>\n\n"
        f"📚 {lesson}\n"
        f"👨‍🏫 {teacher}\n\n"
        f"📅 <b>زمان جدید:</b> {jalali_display}  ⏰ {new_time}\n"
        f"📍 {location}"
        + (f"\n\n📝 {note}" if note else '')
    )
    users = await db.notif_users('schedule')
    sent, _ = await broadcast_message(context.bot, users, notif_msg)

    admin_uid  = update.effective_user.id
    admin_user = await db.get_user(admin_uid)
    actor_name = admin_user.get('name', 'ادمین') if admin_user else 'ادمین'
    old_jalali = fmt_jalali(schedule_doc.get('date', ''))
    await send_audit_log(
        context.bot, 'admin', actor_name, admin_uid,
        "تغییر زمان کلاس", module='Schedules', severity='INFO', target_id=sid,
        before={'زمان': f"{old_jalali} {schedule_doc.get('time','')}"},
        after={'زمان': f"{jalali_display} {new_time}"},
        details=f"درس: {lesson}"
    )

    await update.message.reply_text(
        f"✅ <b>تغییر زمان ثبت و اعلام شد!</b>\n\n"
        f"📚 {lesson}\n📅 {jalali_display}  ⏰ {new_time}\n\n"
        f"🔔 <b>{sent} نفر</b> مطلع شدند.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 پنل ادمین", callback_data='admin:main')
        ]])
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

async def _ask_flex_type(message, context):
    """
    FIX جدید — مرحله ۱ پیش‌نمایش: انتخاب نوع زمان‌بندی (ثابت/منعطف)
    قبل از نمایش پیش‌نمایش نهایی.
    """
    keyboard = [
        [InlineKeyboardButton("📌 ثابت (زمان قطعی و همیشگی)", callback_data='schedule:flex:fixed')],
        [InlineKeyboardButton("🔄 منعطف (ممکن است زمان تغییر کند)", callback_data='schedule:flex:flexible')],
        [InlineKeyboardButton("❌ لغو", callback_data='admin:main')],
    ]
    await message.reply_text(
        "📌 <b>نوع زمان‌بندی این مورد چیست؟</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📌 <b>ثابت:</b> همیشه طبق همین زمان برگزار می‌شود\n"
        "🔄 <b>منعطف:</b> ممکن است زمان جا‌به‌جا شود — در جدول هفتگی "
        "با برچسب «زمان متغیر» نشان داده می‌شود",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_schedule_preview(message_or_query, context, edit: bool = False):
    """
    FIX جدید — مرحله ۲ پیش‌نمایش: نمایش کامل اطلاعات قبل از ثبت نهایی،
    با دکمه‌های ✅ تأیید و انتشار / ✏️ بازگشت و ویرایش / ❌ لغو.
    """
    p = context.user_data.get('pending_schedule', {})
    if not p:
        return
    type_fa = TYPE_NAMES.get(p['stype'], p['stype'])
    jalali_display = fmt_jalali(p['date'])
    flex = p.get('flex_type', 'fixed')
    flex_label = "🔄 منعطف (ممکن است تغییر کند)" if flex == 'flexible' else "📌 ثابت"
    g_label = p['group'] if p['group'] not in ('', None) else 'هر دو'

    text = (
        "👁 <b>پیش‌نمایش — لطفاً بررسی کنید</b>\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"🏷 <b>نوع:</b> {type_fa}\n"
        f"📚 <b>درس:</b> {p['lesson']}\n"
        f"👨‍🏫 <b>استاد:</b> {p['teacher']}\n"
        f"📅 <b>تاریخ:</b> {jalali_display}\n"
        f"⏰ <b>ساعت:</b> {p['time']}\n"
        f"📍 <b>مکان:</b> {p['location']}\n"
        f"👥 <b>گروه هدف:</b> {g_label}\n"
        f"🔁 <b>نوع زمان‌بندی:</b> {flex_label}\n"
        + (f"📝 <b>توضیحات:</b> {p['notes']}\n" if p.get('notes') else '')
        + "\n━━━━━━━━━━━━━━━━\n"
        "📤 <b>وضعیت انتشار:</b> در انتظار تأیید نهایی شما"
    )
    keyboard = [
        [InlineKeyboardButton("✅ تأیید و انتشار", callback_data='schedule:confirm_add')],
        [InlineKeyboardButton("✏️ بازگشت و ویرایش", callback_data='schedule:edit_pending')],
        [InlineKeyboardButton("❌ لغو", callback_data='schedule:cancel_pending')],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if edit and hasattr(message_or_query, 'edit_message_text'):
        await message_or_query.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
    else:
        msg = message_or_query if hasattr(message_or_query, 'reply_text') else message_or_query.message
        await msg.reply_text(text, parse_mode='HTML', reply_markup=markup)


async def _finalize_schedule_add(update_or_query, context):
    """
    FIX جدید: تأیید نهایی — همان منطق ذخیره و اطلاع‌رسانی قبلی،
    اما حالا بعد از تأیید کاربر در پیش‌نمایش اجرا می‌شود.
    """
    from utils import broadcast_message
    p = context.user_data.pop('pending_schedule', {})
    if not p:
        return

    sid = await db.add_schedule(
        p['stype'], p['lesson'], p['teacher'], p['date'], p['time'],
        p['location'], p.get('notes', ''), p['group'],
        flex_type=p.get('flex_type', 'fixed'),
        flex_note=p.get('time', '') if p.get('flex_type') == 'flexible' else '',
    )

    # FIX جدید: نوتیف جبرانی جدا از برنامه کلاسی عادی است
    ntype = {'exam': 'exam', 'makeup': 'makeup'}.get(p['stype'], 'schedule')
    users   = await db.notif_users(ntype)
    type_fa = TYPE_NAMES.get(p['stype'], p['stype'])
    g_label = f" | گروه {p['group']}" if p['group'] not in ('هر دو', '') else ''
    jalali_display = fmt_jalali(p['date'])
    flex_tag = " 🔄 (منعطف)" if p.get('flex_type') == 'flexible' else ''
    notif_msg = (
        f"📅 <b>{type_fa} جدید</b>{flex_tag}\n\n"
        f"📚 {p['lesson']}\n"
        f"👨‍🏫 {p['teacher']}\n"
        f"📅 {jalali_display}  ⏰ {p['time']}\n"
        f"📍 {p['location']}{g_label}"
    )
    sent, _ = await broadcast_message(context.bot, users, notif_msg)

    bot_obj = context.bot
    admin_uid = update_or_query.from_user.id if hasattr(update_or_query, 'from_user') else update_or_query.effective_user.id
    admin_user = await db.get_user(admin_uid)
    actor_name = admin_user.get('name', 'ادمین') if admin_user else 'ادمین'
    await send_audit_log(
        bot_obj, 'admin', actor_name, admin_uid,
        f"ایجاد {type_fa} جدید", module='Schedules', severity='INFO',
        details=f"{p['lesson']} — {jalali_display} {p['time']}"
    )

    for k in ('awaiting_search', 'search_mode', 'mode', 'schedule_type'):
        context.user_data.pop(k, None)

    text = (
        f"✅ <b>{type_fa} با موفقیت اضافه شد!</b>\n\n"
        f"📚 {p['lesson']}\n"
        f"👨‍🏫 {p['teacher']}\n"
        f"📅 {jalali_display}  ⏰ {p['time']}\n"
        f"📍 {p['location']}{g_label}\n\n"
        f"🔔 <b>{sent} نفر</b> مطلع شدند."
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📅 مشاهده برنامه", callback_data=f'schedule:type:{p["stype"]}:'),
        InlineKeyboardButton("🔙 پنل ادمین",      callback_data='admin:main'),
    ]])
    if hasattr(update_or_query, 'edit_message_text'):
        await update_or_query.edit_message_text(text, parse_mode='HTML', reply_markup=keyboard)
    else:
        await update_or_query.message.reply_text(text, parse_mode='HTML', reply_markup=keyboard)


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

        # FIX جدید: به‌جای ذخیره مستقیم، اطلاعات پارس‌شده را نگه می‌داریم
        # و یک پیش‌نمایش + انتخاب نوع زمان‌بندی نشان می‌دهیم.
        context.user_data['pending_schedule'] = {
            'stype': stype, 'lesson': lesson, 'teacher': teacher,
            'date': date, 'time': time_str, 'location': location,
            'group': group, 'notes': notes,
        }
        context.user_data.pop('mode', None)
        await _ask_flex_type(update.message, context)

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

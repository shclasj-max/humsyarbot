import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db

ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

RANK_LEVELS = [
    (0,   "🌱 تازه‌کار"),
    (10,  "📖 دانشجو"),
    (30,  "🎓 فعال"),
    (60,  "⭐ پیشرفته"),
    (100, "🏆 نخبه"),
]

def get_rank(pct):
    for threshold, label in reversed(RANK_LEVELS):
        if pct >= threshold:
            return label
    return "🌱 تازه‌کار"

def progress_bar(pct, length=10):
    filled = int(pct / 100 * length)
    return '█' * filled + '░' * (length - filled)

def exam_countdown(days):
    if days == 0: return "🔴 امروز!"
    if days == 1: return "🔴 فردا!"
    if days <= 3: return f"🟠 {days} روز دیگر"
    if days <= 7: return f"🟡 {days} روز دیگر"
    return f"🟢 {days} روز دیگر"


async def build_dashboard_text(uid):
    user = await db.get_user(uid)
    if not user:
        return "❌ کاربر پیدا نشد.", None

    stats = await db.user_stats(uid)
    new_res = await db.new_resources_count(7)
    exams = await db.upcoming_exams(7)
    open_tickets = 0
    try:
        tickets = await db.ticket_get_user(uid)
        open_tickets = sum(1 for t in tickets if t.get('status') == 'open')
    except: pass

    # امتحان نزدیک
    exam_lines = []
    for e in exams[:2]:
        try:
            d = datetime.strptime(e['date'], '%Y-%m-%d')
            days = max(0, (d - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).days)
            exam_lines.append(f"  📝 {e['lesson']} — {exam_countdown(days)}")
        except:
            exam_lines.append(f"  📝 {e.get('lesson','')}")
    exam_text = '\n'.join(exam_lines) if exam_lines else "  ✅ امتحانی نزدیک نیست"

    # نقاط ضعف
    weak = stats['weak_topics'][:3]
    weak_text = '، '.join(weak) if weak else 'ندارید 🎉'

    bar = progress_bar(stats['percentage'])
    rank = get_rank(stats['percentage'])
    pct = stats['percentage']

    # ستاره‌های فعالیت هفتگی
    act = stats['week_activity']
    act_stars = '🔥' * min(act // 3, 5) if act > 0 else '💤'

    # وضعیت اعلان
    notif_s = user.get('notification_settings', {})
    active_notifs = sum(1 for v in notif_s.values() if v)

    group_icon = "1️⃣" if str(user.get('group', '')) == '1' else "2️⃣"
    role = user.get('role', 'student')
    role_badge = " | 🎓 ادمین محتوا" if role == 'content_admin' else (" | 👑 ادمین" if uid == ADMIN_ID else "")

    text = (
        f"🩺 <b>داشبورد — {user['name']}</b>{role_badge}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 گروه {group_icon}  |  🎓 {user.get('student_id','')}\n\n"
        f"📊 <b>آمادگی تستی</b>\n"
        f"  {bar} <b>{pct}%</b>  {rank}\n\n"
        f"📈 <b>آمار من</b>\n"
        f"  🧪 سوال: <b>{stats['total_answers']}</b>  "
        f"✅ صحیح: <b>{stats['correct_answers']}</b>  "
        f"📥 دانلود: <b>{stats['downloads']}</b>\n"
        f"  {act_stars} فعالیت این هفته: <b>{act}</b> بار\n\n"
        f"⏳ <b>امتحانات پیش رو</b>\n{exam_text}\n\n"
        f"⚡ <b>نقاط ضعف:</b> {weak_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📚 منابع جدید این هفته: <b>{new_res}</b>  "
        f"🔔 اعلان‌های فعال: <b>{active_notifs}/4</b>"
    )
    if open_tickets:
        text += f"\n🎫 تیکت‌های باز: <b>{open_tickets}</b>"

    keyboard = [
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data='dashboard:refresh'),
         InlineKeyboardButton("📊 آمار کامل", callback_data='stats:main')],
        [InlineKeyboardButton("🧪 تمرین هوشمند", callback_data='questions:weak'),
         InlineKeyboardButton("🔔 اعلان‌ها", callback_data='notif:main')],
        [InlineKeyboardButton("🎫 تیکت پشتیبانی", callback_data='ticket:main')]
    ]
    if uid == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("👨‍⚕️ پنل ادمین", callback_data='admin:main')])

    return text, InlineKeyboardMarkup(keyboard)


async def dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    text, kb = await build_dashboard_text(uid)
    try:
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=kb)
    except:
        await update.effective_message.reply_text(text, parse_mode='HTML', reply_markup=kb)

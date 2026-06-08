"""
🩺 داشبورد — با فراخوانی موازی دیتابیس برای سرعت
  ✅ نمایش ورودی + گروه
  ✅ جدول برترین‌ها
"""
import os
import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from utils import progress_bar, get_rank, exam_countdown, fmt_jalali

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))


async def build_dashboard_text(uid: int) -> tuple:
    user, stats, exams, new_res = await asyncio.gather(
        db.get_user(uid),
        db.user_stats(uid),
        db.upcoming_exams(7),
        db.new_resources_count(7),
    )

    if not user:
        return "❌ کاربر پیدا نشد.", None

    open_tickets = 0
    try:
        tickets = await db.ticket_get_user(uid)
        open_tickets = sum(1 for t in tickets if t.get('status') == 'open')
    except Exception:
        pass

    exam_lines = []
    for e in exams[:2]:
        try:
            d = datetime.strptime(e['date'], '%Y-%m-%d')
            days = max(0, (
                d.replace(hour=0, minute=0, second=0, microsecond=0)
                - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            ).days)
            exam_lines.append(f"  📝 {e['lesson']} — {exam_countdown(days)}")
        except Exception:
            exam_lines.append(f"  📝 {e.get('lesson', '')}")
    exam_text = '\n'.join(exam_lines) if exam_lines else "  ✅ امتحانی نزدیک نیست"

    weak     = stats['weak_topics'][:3]
    weak_str = '، '.join(weak) if weak else 'ندارید 🎉'
    pct      = stats['percentage']
    bar      = progress_bar(pct)
    rank     = get_rank(stats['correct_answers'])
    act      = stats['week_activity']
    act_stars = '🔥' * min(act // 3, 5) if act > 0 else '💤'

    notif_s       = user.get('notification_settings', {})
    active_notifs = sum(1 for v in notif_s.values() if v)
    group_icon    = "1️⃣" if str(user.get('group', '')) == '1' else "2️⃣"
    role          = user.get('role', 'student')
    role_badge    = (
        " | 👑 ادمین" if uid == ADMIN_ID
        else " | 🎓 ادمین محتوا" if role == 'content_admin'
        else ""
    )

    intake      = user.get('intake', '') or '—'
    sid_line    = f"🎓 {user.get('student_id', '')}\n" if user.get('student_id') else ""

    text = (
        f"🩺 <b>داشبورد — {user['name']}</b>{role_badge}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 ورودی: <b>{intake}</b>  |  👥 گروه {group_icon}\n"
        f"{sid_line}\n"
        f"📊 <b>آمادگی تستی</b>\n"
        f"  {bar} <b>{pct}%</b>  {rank}\n\n"
        f"📈 <b>آمار من</b>\n"
        f"  🧪 سوال: <b>{stats['total_answers']}</b>  "
        f"✅ صحیح: <b>{stats['correct_answers']}</b>  "
        f"📥 دانلود: <b>{stats['downloads']}</b>\n"
        f"  {act_stars} فعالیت این هفته: <b>{act}</b> بار\n\n"
        f"⏳ <b>امتحانات پیش رو</b>\n{exam_text}\n\n"
        f"⚡ <b>نقاط ضعف:</b> {weak_str}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📚 منابع جدید این هفته: <b>{new_res}</b>  "
        f"🔔 اعلان‌های فعال: <b>{active_notifs}/4</b>"
    )
    if open_tickets:
        text += f"\n🎫 تیکت‌های باز: <b>{open_tickets}</b>"

    keyboard = [
        [
            InlineKeyboardButton("🔄 بروزرسانی",    callback_data='dashboard:refresh'),
            InlineKeyboardButton("📊 آمار کامل",     callback_data='stats:main'),
        ],
        [
            InlineKeyboardButton("🧪 تمرین هوشمند", callback_data='questions:weak'),
            InlineKeyboardButton("🏆 جدول برترین",  callback_data='dashboard:leaderboard'),
        ],
        [
            InlineKeyboardButton("🔔 اعلان‌ها",     callback_data='notif:main'),
            InlineKeyboardButton("🎫 پشتیبانی",     callback_data='ticket:main'),
        ],
    ]
    if uid == ADMIN_ID:
        keyboard.append([
            InlineKeyboardButton("👨‍⚕️ پنل ادمین",  callback_data='admin:main'),
            InlineKeyboardButton("📡 وضعیت ربات",   callback_data='admin:bot_status'),
        ])

    return text, InlineKeyboardMarkup(keyboard)


async def _build_leaderboard_text(uid: int) -> tuple:
    leaders = await db.get_leaderboard(10)
    lines   = ["🏆 <b>جدول برترین‌ها</b>\n━━━━━━━━━━━━━━━━\n"]
    medals  = ['🥇', '🥈', '🥉'] + ['🎖'] * 7
    for i, u in enumerate(leaders):
        name    = u.get('name', 'کاربر')
        correct = u.get('correct_answers', 0)
        total   = u.get('total_answers', 0)
        pct     = round(correct / total * 100, 1) if total > 0 else 0
        marker  = " ← شما" if u.get('user_id') == uid else ""
        intake  = f" | {u.get('intake','')}" if u.get('intake') else ""
        lines.append(
            f"{medals[i]} <b>{name}</b> — گروه {u.get('group', '')}{intake}\n"
            f"   ✅ {correct} صحیح از {total}  |  📈 {pct}%{marker}"
        )
    text = '\n'.join(lines)
    kb   = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 بازگشت", callback_data='dashboard:refresh')
    ]])
    return text, kb


async def dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    uid    = update.effective_user.id
    action = query.data.split(':')[1] if ':' in query.data else 'refresh'

    if action == 'leaderboard':
        text, kb = await _build_leaderboard_text(uid)
    else:
        text, kb = await build_dashboard_text(uid)

    try:
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=kb)
    except Exception:
        await update.effective_message.reply_text(text, parse_mode='HTML', reply_markup=kb)

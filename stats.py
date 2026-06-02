from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db


def bar(val, mx=100, length=12, fill='█', empty='░'):
    f = int(val / mx * length) if mx > 0 else 0
    return fill * f + empty * (length - f)


async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data.split(':')[1] if ':' in query.data else 'main'

    if action == 'main':
        await _main_stats(query, update.effective_user.id)
    elif action == 'weekly':
        await _weekly(query, update.effective_user.id)
    elif action == 'weak':
        await _weak(query, update.effective_user.id)


async def _main_stats(query, uid):
    stats = await db.user_stats(uid)
    user = await db.get_user(uid)
    total = stats['total_answers']
    correct = stats['correct_answers']
    pct = stats['percentage']

    if pct >= 90: level = "🏆 خبره"
    elif pct >= 75: level = "⭐ پیشرفته"
    elif pct >= 60: level = "📈 متوسط"
    elif pct >= 40: level = "📚 مبتدی"
    else: level = "🌱 تازه‌کار"

    b = bar(pct)
    text = (
        f"📊 <b>آمار من</b>\n"
        f"👤 {user.get('name','')} | گروه {user.get('group','')}\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"🏅 سطح: <b>{level}</b>\n\n"
        f"📊 آمادگی: {b} <b>{pct}%</b>\n"
        f"✅ صحیح: <b>{correct}</b>  ❌ اشتباه: <b>{total-correct}</b>\n"
        f"📥 دانلود: <b>{stats['downloads']}</b>\n"
        f"🔥 فعالیت هفتگی: <b>{stats['week_activity']}</b>\n"
        f"⚡ نقاط ضعف: <b>{len(stats['weak_topics'])}</b> مبحث"
    )
    keyboard = [
        [InlineKeyboardButton("📅 فعالیت هفتگی", callback_data='stats:weekly'),
         InlineKeyboardButton("⚡ نقاط ضعف", callback_data='stats:weak')],
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data='stats:main')]
    ]
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _weekly(query, uid):
    data = await db.weekly_activity(uid)
    max_val = max(d[1] for d in data) or 1
    text = "📅 <b>فعالیت ۷ روز گذشته</b>\n\n"
    for date, count in data:
        b = bar(count, max_val, 10)
        text += f"{date}: {b} {count}\n"
    total = sum(d[1] for d in data)
    text += f"\n📊 مجموع: <b>{total}</b> عمل"
    await query.edit_message_text(
        text, parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='stats:main')]])
    )


async def _weak(query, uid):
    user = await db.get_user(uid)
    weak = user.get('weak_topics', []) if user else []
    if not weak:
        text = "🎉 <b>هیچ نقطه ضعفی ندارید!</b>\nبیشتر تمرین کنید."
    else:
        text = "⚡ <b>نقاط ضعف شما:</b>\n\n"
        for i, t in enumerate(weak, 1):
            text += f"{i}. ❌ {t}\n"
        text += "\n💡 تمرین هدفمند این مباحث را پیشنهاد می‌کنم."
    keyboard = [
        [InlineKeyboardButton("⚡ تمرین نقاط ضعف", callback_data='questions:weak')],
        [InlineKeyboardButton("🔙 بازگشت", callback_data='stats:main')]
    ]
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

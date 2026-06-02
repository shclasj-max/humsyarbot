import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db

logger = logging.getLogger(__name__)


async def archive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split(':')

    if data.startswith('download_video:'):
        vid = await db.get_video(parts[1])
        if not vid:
            await query.answer("❌ ویدیو پیدا نشد!", show_alert=True)
            return
        await db.videos.update_one({'_id': vid['_id']}, {'$inc': {'views': 1}})
        caption = (
            f"🎥 <b>{vid.get('lesson','')} — {vid.get('topic','')}</b>\n"
            f"👨‍🏫 {vid.get('teacher','')} | 📅 {vid.get('date','')}\n"
            f"👁 {vid.get('views',0)} بار مشاهده"
        )
        try:
            await context.bot.send_video(update.effective_chat.id, vid['file_id'],
                                          caption=caption, parse_mode='HTML')
        except:
            try:
                await context.bot.send_document(update.effective_chat.id, vid['file_id'],
                                                 caption=caption, parse_mode='HTML')
            except:
                await query.answer("❌ خطا در ارسال!", show_alert=True)
        return

    action = parts[1] if len(parts) > 1 else 'main'

    if action == 'main':
        lessons = await db.get_lessons()
        keyboard = []
        for i in range(0, len(lessons), 2):
            row = [InlineKeyboardButton(lessons[i], callback_data=f'archive:lesson:{lessons[i]}'[:64])]
            if i + 1 < len(lessons):
                row.append(InlineKeyboardButton(lessons[i+1], callback_data=f'archive:lesson:{lessons[i+1]}'[:64]))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("📅 آخرین کلاس‌ها", callback_data='archive:recent')])
        await query.edit_message_text(
            "🎥 <b>آرشیو کلاس‌ها</b>\n\nدرس را انتخاب کنید:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'lesson':
        lesson = ':'.join(parts[2:])
        videos = await db.get_videos(lesson=lesson)
        if not videos:
            await query.edit_message_text(
                f"🎥 <b>{lesson}</b>\n\n❌ ویدیویی ثبت نشده.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='archive:main')]])
            )
            return
        teachers = {}
        for v in videos:
            t = v.get('teacher', 'نامشخص')
            teachers[t] = teachers.get(t, 0) + 1
        keyboard = []
        for t, cnt in teachers.items():
            keyboard.append([InlineKeyboardButton(
                f"👨‍🏫 {t} ({cnt})", callback_data=f'archive:teacher:{lesson}:{t}'[:64]
            )])
        keyboard.append([InlineKeyboardButton(f"📂 همه ({len(videos)})", callback_data=f'archive:teacher:{lesson}:همه'[:64])])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='archive:main')])
        await query.edit_message_text(
            f"🎥 <b>{lesson}</b> — {len(videos)} ویدیو\n\nاستاد را انتخاب کنید:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'teacher':
        lesson, teacher = parts[2], ':'.join(parts[3:])
        videos = await db.get_videos(lesson=lesson, teacher=teacher)
        if not videos:
            await query.edit_message_text("❌ ویدیویی یافت نشد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data=f'archive:lesson:{lesson}'[:64])]]))
            return
        keyboard = []
        for v in videos:
            vid_id = str(v['_id'])
            label = f"🎬 {v.get('topic','کلاس')} | {v.get('date','')} | 👁{v.get('views',0)}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f'download_video:{vid_id}')])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f'archive:lesson:{lesson}'[:64])])
        await query.edit_message_text(
            f"🎥 <b>{lesson}</b>{' — '+teacher if teacher != 'همه' else ''}\n{len(videos)} ویدیو:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'recent':
        videos = await db.get_videos()
        if not videos:
            await query.edit_message_text("❌ ویدیویی ثبت نشده.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='archive:main')]]))
            return
        keyboard = []
        for v in videos[:10]:
            vid_id = str(v['_id'])
            label = f"🎬 {v.get('lesson','')} | {v.get('teacher','')} | {v.get('date','')}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f'download_video:{vid_id}')])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='archive:main')])
        await query.edit_message_text(
            f"📅 <b>آخرین کلاس‌ها</b>\n{len(videos[:10])} ویدیو:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

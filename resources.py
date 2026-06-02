import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
TERMS = ['ترم ۱', 'ترم ۲', 'ترم ۳', 'ترم ۴', 'ترم ۵']
RESOURCE_TYPES = ['📄 جزوه', '📊 پاورپوینت', '📝 نکات', '🧠 خلاصه', '🧪 تست', '🎙 ویس']

logger = logging.getLogger(__name__)
UPLOAD_METADATA = 1
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
CHANNEL_ID = os.getenv('CHANNEL_ID', '')


async def resources_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split(':')

    if data.startswith('download_resource:'):
        rid = parts[1]
        resource = await db.get_resource(rid)
        if not resource:
            await query.answer("❌ فایل پیدا نشد!", show_alert=True)
            return
        await db.inc_download(rid, update.effective_user.id)
        m = resource['metadata']
        rtype = resource.get('type', '')
        caption = (
            f"{rtype} <b>{resource.get('lesson','')} / {resource.get('topic','')}</b>\n"
            f"📌 نسخه {m.get('version','1')} | {'⭐'*m.get('importance',3)}\n"
            f"🏷 {', '.join(m.get('tags',[]))}\n"
            f"📝 {m.get('description','')}"
        )
        # ویس = ارسال به عنوان audio
        if '🎙' in rtype:
            try:
                await context.bot.send_audio(update.effective_chat.id, resource['file_id'],
                                              caption=caption, parse_mode='HTML')
                return
            except:
                pass
        try:
            await context.bot.send_document(update.effective_chat.id, resource['file_id'],
                                            caption=caption, parse_mode='HTML')
        except:
            try:
                await context.bot.send_voice(update.effective_chat.id, resource['file_id'],
                                             caption=caption, parse_mode='HTML')
            except:
                await query.answer("❌ خطا در ارسال فایل!", show_alert=True)
        return

    action = parts[1] if len(parts) > 1 else 'main'

    if action in ('main', 'back_main'):
        keyboard = []
        for i in range(0, len(TERMS), 2):
            row = [InlineKeyboardButton(TERMS[i], callback_data=f'resources:term:{TERMS[i]}'[:64])]
            if i + 1 < len(TERMS):
                row.append(InlineKeyboardButton(TERMS[i+1], callback_data=f'resources:term:{TERMS[i+1]}'[:64]))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔍 جستجو", callback_data='resources:search')])
        await query.edit_message_text(
            "📚 <b>منابع درسی</b>\n\nترم را انتخاب کنید:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'term':
        term = ':'.join(parts[2:])
        lessons = await db.get_lessons()
        keyboard = []
        for i in range(0, len(lessons), 2):
            row = [InlineKeyboardButton(lessons[i], callback_data=f'resources:lesson:{term}:{lessons[i]}'[:64])]
            if i + 1 < len(lessons):
                row.append(InlineKeyboardButton(lessons[i+1], callback_data=f'resources:lesson:{term}:{lessons[i+1]}'[:64]))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='resources:main')])
        await query.edit_message_text(
            f"📚 <b>{term}</b>\n\nدرس را انتخاب کنید:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'lesson':
        term, lesson = parts[2], parts[3]
        topics = await db.get_topics(lesson)
        keyboard = [[InlineKeyboardButton(t, callback_data=f'resources:topic:{term}:{lesson}:{t}'[:64])] for t in topics]
        keyboard.append([InlineKeyboardButton("📂 همه مباحث", callback_data=f'resources:topic:{term}:{lesson}:همه'[:64])])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f'resources:term:{term}'[:64])])
        await query.edit_message_text(
            f"📚 <b>{lesson}</b> — {term}\n\nمبحث را انتخاب کنید:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'topic':
        term, lesson, topic = parts[2], parts[3], ':'.join(parts[4:])
        keyboard = [[InlineKeyboardButton(rt, callback_data=f'resources:files:{term}:{lesson}:{topic}:{rt}'[:64])] for rt in RESOURCE_TYPES]
        keyboard.append([InlineKeyboardButton("📂 همه انواع", callback_data=f'resources:files:{term}:{lesson}:{topic}:همه'[:64])])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f'resources:lesson:{term}:{lesson}'[:64])])
        await query.edit_message_text(
            f"📚 <b>{topic}</b>\n{lesson} | {term}\n\nنوع فایل را انتخاب کنید:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'files':
        term, lesson, topic, rtype = parts[2], parts[3], parts[4], ':'.join(parts[5:])
        files = await db.get_resources(term=term, lesson=lesson, topic=topic, rtype=rtype)
        if not files:
            await query.edit_message_text(
                f"📂 <b>{rtype}</b> — {topic}\n\n❌ فایلی پیدا نشد.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت", callback_data=f'resources:topic:{term}:{lesson}:{topic}'[:64])
                ]])
            )
            return
        keyboard = []
        for f in files:
            fid = str(f['_id'])
            m = f['metadata']
            stars = '⭐' * m.get('importance', 3)
            rtype_icon = f.get('type', '')
            label = f"📥 {rtype_icon} v{m.get('version','1')} {stars} ⬇️{m.get('downloads',0)}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f'download_resource:{fid}')])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f'resources:topic:{term}:{lesson}:{topic}'[:64])])
        await query.edit_message_text(
            f"📂 <b>{rtype}</b> — {topic}\n{lesson} | {term}\n\n{len(files)} فایل:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'search':
        context.user_data['search_mode'] = 'resources'
        context.user_data['awaiting_search'] = True
        await query.edit_message_text(
            "🔍 <b>جستجو در منابع</b>\n\nکلمه کلیدی:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='resources:main')]])
        )


async def upload_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    mode = context.user_data.get('upload_mode', '')

    # تشخیص نوع فایل
    file_obj = (update.message.document or update.message.video or
                update.message.audio or update.message.voice)
    if not file_obj:
        return

    file_id = getattr(file_obj, 'file_id', '')

    if not mode:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 منبع درسی", callback_data='admin:set_mode:resource')],
            [InlineKeyboardButton("🎥 ویدیو کلاس", callback_data='admin:set_mode:video')],
            [InlineKeyboardButton("🧪 بانک سوال (فایل)", callback_data='admin:set_mode:qbank')]
        ])
        context.user_data['pending_file_id'] = file_id
        await update.message.reply_text("📤 فایل دریافت شد. نوع را انتخاب کنید:", reply_markup=keyboard)
        return

    context.user_data['upload_file_id'] = file_id

    if mode == 'resource':
        path = context.user_data.get('upload_path', {})
        p = f"{path.get('term','؟')} ← {path.get('lesson','؟')} ← {path.get('topic','؟')} ← {path.get('type','؟')}"
        await update.message.reply_text(
            f"📤 فایل دریافت شد.\n📌 مسیر: {p}\n\n"
            "متادیتا:\n`نسخه, تگ‌ها, اهمیت(1-5), توضیحات`\n"
            "مثال: `2.0, قلب عروق, 5, جزوه دکتر محمدی`",
            parse_mode='Markdown'
        )
        return UPLOAD_METADATA

    elif mode == 'video':
        await update.message.reply_text(
            "📹 ویدیو دریافت شد.\n\n"
            "اطلاعات:\n`استاد, تاریخ(YYYY-MM-DD), توضیح`\n"
            "مثال: `دکتر محمدی, 2024-03-15, جلسه اول`",
            parse_mode='Markdown'
        )
        return UPLOAD_METADATA

    elif mode == 'qbank':
        path = context.user_data.get('upload_path', {})
        await update.message.reply_text(
            f"🧪 فایل بانک سوال دریافت شد.\n"
            f"📌 {path.get('lesson','؟')} — {path.get('topic','؟')}\n\n"
            "توضیح کوتاه بنویسید:\n"
            "مثال: `بانک سوال امتحانات قبلی دکتر احمدی`",
            parse_mode='Markdown'
        )
        return UPLOAD_METADATA


async def upload_metadata_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    mode = context.user_data.get('upload_mode', 'resource')
    file_id = context.user_data.get('upload_file_id', '')

    try:
        parts = [p.strip() for p in text.split(',')]

        if mode == 'resource':
            if len(parts) < 3:
                raise ValueError("حداقل ۳ فیلد لازم است")
            version = parts[0]
            tags = parts[1].split() if parts[1] else []
            importance = max(1, min(5, int(parts[2])))
            description = parts[3] if len(parts) > 3 else ''
            path = context.user_data.get('upload_path', {})

            await db.add_resource(
                path.get('term', 'ترم ۱'),
                path.get('lesson', 'عمومی'),
                path.get('topic', 'عمومی'),
                path.get('type', '📄 جزوه'),
                file_id,
                {'version': version, 'tags': tags, 'importance': importance, 'description': description}
            )

            if CHANNEL_ID:
                try:
                    await context.bot.send_document(
                        CHANNEL_ID, file_id,
                        caption=f"📚 {path.get('lesson','')} — {path.get('topic','')}\n{path.get('type','')} v{version}",
                        parse_mode='HTML'
                    )
                except:
                    pass

            users = await db.notif_users('new_resources')
            count = 0
            for u in users:
                if u['user_id'] != ADMIN_ID:
                    try:
                        await context.bot.send_message(
                            u['user_id'],
                            f"📚 <b>منبع جدید:</b> {path.get('lesson','')} — {path.get('topic','')}\n{path.get('type','')}",
                            parse_mode='HTML'
                        )
                        count += 1
                    except:
                        pass

            await update.message.reply_text(
                f"✅ منبع اضافه شد!\n🔔 {count} نفر مطلع شدند."
            )

        elif mode == 'video':
            if len(parts) < 2:
                raise ValueError("حداقل ۲ فیلد")
            teacher = parts[0]
            date = parts[1]
            description = parts[2] if len(parts) > 2 else ''
            path = context.user_data.get('upload_path', {})
            await db.add_video(path.get('lesson', ''), path.get('topic', ''), teacher, date, file_id)
            await update.message.reply_text(f"✅ ویدیو اضافه شد!\n🎥 {path.get('lesson','')} | {teacher} | {date}")

        elif mode == 'qbank':
            description = text
            path = context.user_data.get('upload_path', {})
            is_voice = False
            await db.add_qbank_file(
                path.get('lesson', ''), path.get('topic', ''),
                file_id, description,
                file_type='voice' if is_voice else 'document'
            )
            await update.message.reply_text(
                f"✅ فایل بانک سوال اضافه شد!\n"
                f"📚 {path.get('lesson','')} — {path.get('topic','')}"
            )

    except ValueError as e:
        await update.message.reply_text(f"❌ خطا: {e}\nدوباره وارد کنید:")
        return UPLOAD_METADATA
    except Exception as e:
        logger.error(f"upload_metadata error: {e}")
        await update.message.reply_text("❌ خطا. دوباره تلاش کنید:")
        return UPLOAD_METADATA

    for k in ['upload_mode', 'upload_file_id', 'upload_path', 'pending_file_id']:
        context.user_data.pop(k, None)
    return ConversationHandler.END

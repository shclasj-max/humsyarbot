"""
سیستم پشتیبان‌گیری و بازیابی ربات
- Export: JSON کامل از همه دیتابیس‌ها
- Import: بازیابی از فایل JSON
- فقط ادمین اصلی دسترسی دارد
"""
import os, json, logging, io
from datetime import datetime
from bson import ObjectId
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))


# ── JSON encoder برای ObjectId و datetime ──
class _Enc(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId): return str(o)
        if isinstance(o, datetime):  return o.isoformat()
        return super().default(o)


# ══════════════════════════════════════════════════
#  Callback اصلی
# ══════════════════════════════════════════════════
async def backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = update.effective_user.id
    if uid != ADMIN_ID:
        await query.answer("❌ فقط ادمین اصلی دسترسی دارد!", show_alert=True); return
    await query.answer()

    data   = query.data
    parts  = data.split(':')
    action = parts[1] if len(parts) > 1 else 'menu'

    if action == 'menu':
        await _show_menu(query)

    elif action == 'export_all':
        await query.edit_message_text(
            "⏳ <b>در حال آماده‌سازی پشتیبان...</b>\n\nلطفاً چند ثانیه صبر کنید.",
            parse_mode='HTML')
        await _export_all(query, context)

    elif action == 'export_users':
        await query.edit_message_text("⏳ در حال آماده‌سازی...", parse_mode='HTML')
        await _export_section(query, 'users')

    elif action == 'export_content':
        await query.edit_message_text("⏳ در حال آماده‌سازی...", parse_mode='HTML')
        await _export_section(query, 'content')

    elif action == 'export_refs':
        await query.edit_message_text("⏳ در حال آماده‌سازی...", parse_mode='HTML')
        await _export_section(query, 'refs')

    elif action == 'export_qbank':
        await query.edit_message_text("⏳ در حال آماده‌سازی...", parse_mode='HTML')
        await _export_section(query, 'qbank')

    elif action == 'restore_prompt':
        await query.edit_message_text(
            "📥 <b>بازیابی از فایل پشتیبان</b>\n\n"
            "⚠️ <b>هشدار:</b> این عملیات داده‌های فعلی را با داده‌های فایل پشتیبان <b>جایگزین</b> می‌کند!\n\n"
            "فایل JSON پشتیبان را ارسال کنید:\n"
            "<i>(فایلی که قبلاً با دکمه «پشتیبان کامل» دریافت کرده‌اید)</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='backup:menu')
            ]]))
        context.user_data['backup_mode'] = 'waiting_restore'


async def _show_menu(query):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    kb = [
        [InlineKeyboardButton("💾 پشتیبان کامل (همه بخش‌ها)", callback_data='backup:export_all')],
        [InlineKeyboardButton("👥 فقط کاربران",    callback_data='backup:export_users'),
         InlineKeyboardButton("📚 علوم پایه",       callback_data='backup:export_content')],
        [InlineKeyboardButton("📖 رفرنس‌ها",        callback_data='backup:export_refs'),
         InlineKeyboardButton("🧪 بانک سوال",       callback_data='backup:export_qbank')],
        [InlineKeyboardButton("📥 بازیابی از فایل", callback_data='backup:restore_prompt')],
        [InlineKeyboardButton("🔙 بازگشت به پنل",   callback_data='admin:main')],
    ]
    await query.edit_message_text(
        f"💾 <b>پشتیبان‌گیری و بازیابی</b>\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"🕐 زمان سرور: <code>{now}</code>\n\n"
        f"برای <b>پشتیبان‌گیری</b>، یکی از بخش‌ها را انتخاب کنید.\n"
        f"برای <b>بازیابی</b>، فایل JSON را آپلود کنید.\n\n"
        f"<i>⚠️ فایل پشتیبان شامل file_id های تلگرام است —\n"
        f"برای بازیابی کامل فایل‌ها، ربات باید به همان bot token دسترسی داشته باشد.</i>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(kb))


# ══════════════════════════════════════════════════
#  Export توابع
# ══════════════════════════════════════════════════

async def _export_all(query, context):
    """پشتیبان کامل از همه بخش‌ها"""
    try:
        data = {
            'backup_version': '2.0',
            'created_at':     datetime.now().isoformat(),
            'sections':       {}
        }

        # ── کاربران ──
        users = await db.users.find({}).to_list(10000)
        data['sections']['users'] = {
            'description': 'اطلاعات کاربران ثبت‌نام شده',
            'count':       len(users),
            'data':        users
        }

        # ── علوم پایه ──
        lessons  = await db.bs_lessons.find({}).to_list(1000)
        sessions = await db.bs_sessions.find({}).to_list(5000)
        content  = await db.bs_content.find({}).to_list(10000)
        data['sections']['basic_science'] = {
            'description': 'علوم پایه — درس‌ها، جلسات و محتوا',
            'lessons':     {'count': len(lessons),  'data': lessons},
            'sessions':    {'count': len(sessions), 'data': sessions},
            'content':     {'count': len(content),  'data': content},
        }

        # ── رفرنس‌ها ──
        subjects  = await db.ref_subjects.find({}).to_list(500)
        books     = await db.ref_books.find({}).to_list(2000)
        ref_files = await db.ref_files.find({}).to_list(5000)
        data['sections']['references'] = {
            'description': 'رفرنس‌های درسی — درس‌ها، کتاب‌ها و فایل‌ها',
            'subjects':    {'count': len(subjects),  'data': subjects},
            'books':       {'count': len(books),     'data': books},
            'files':       {'count': len(ref_files), 'data': ref_files},
        }

        # ── بانک سوال ──
        questions  = await db.questions.find({}).to_list(10000)
        qbank_files= await db.qbank_files.find({}).to_list(1000)
        data['sections']['qbank'] = {
            'description': 'بانک سوال — سوالات و فایل‌ها',
            'questions':   {'count': len(questions),   'data': questions},
            'files':       {'count': len(qbank_files), 'data': qbank_files},
        }

        # ── برنامه ──
        schedules = await db.schedules.find({}).to_list(5000)
        data['sections']['schedules'] = {
            'description': 'برنامه کلاس‌ها و امتحانات',
            'count':       len(schedules),
            'data':        schedules
        }

        # ── FAQ ──
        faqs = await db.faq.find({}).to_list(500)
        data['sections']['faq'] = {
            'description': 'سوالات متداول',
            'count':       len(faqs),
            'data':        faqs
        }

        # ── تیکت‌ها ──
        tickets = await db.tickets.find({}).to_list(5000)
        data['sections']['tickets'] = {
            'description': 'تیکت‌های پشتیبانی',
            'count':       len(tickets),
            'data':        tickets
        }

        # آمار خلاصه
        data['summary'] = {
            'users':        len(users),
            'lessons':      len(lessons),
            'sessions':     len(sessions),
            'content_files':len(content),
            'ref_subjects': len(subjects),
            'ref_books':    len(books),
            'ref_files':    len(ref_files),
            'questions':    len(questions),
            'schedules':    len(schedules),
            'faqs':         len(faqs),
            'tickets':      len(tickets),
        }

        await _send_json_file(query, data, filename='backup_full')

    except Exception as e:
        logger.error(f"Backup error: {e}")
        await query.edit_message_text(
            f"❌ خطا در پشتیبان‌گیری:\n<code>{e}</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='backup:menu')
            ]]))


async def _export_section(query, section: str):
    """پشتیبان از یک بخش خاص"""
    try:
        data = {
            'backup_version': '2.0',
            'section':        section,
            'created_at':     datetime.now().isoformat(),
        }

        if section == 'users':
            rows = await db.users.find({}).to_list(10000)
            data['description'] = 'کاربران ثبت‌نام شده'
            data['count']       = len(rows)
            data['data']        = rows

        elif section == 'content':
            lessons  = await db.bs_lessons.find({}).to_list(1000)
            sessions = await db.bs_sessions.find({}).to_list(5000)
            content  = await db.bs_content.find({}).to_list(10000)
            data['description'] = 'علوم پایه'
            data['lessons']     = {'count': len(lessons),  'data': lessons}
            data['sessions']    = {'count': len(sessions), 'data': sessions}
            data['content']     = {'count': len(content),  'data': content}

        elif section == 'refs':
            subjects  = await db.ref_subjects.find({}).to_list(500)
            books     = await db.ref_books.find({}).to_list(2000)
            ref_files = await db.ref_files.find({}).to_list(5000)
            data['description'] = 'رفرنس‌های درسی'
            data['subjects']    = {'count': len(subjects),  'data': subjects}
            data['books']       = {'count': len(books),     'data': books}
            data['files']       = {'count': len(ref_files), 'data': ref_files}

        elif section == 'qbank':
            questions   = await db.questions.find({}).to_list(10000)
            qbank_files = await db.qbank_files.find({}).to_list(1000)
            data['description'] = 'بانک سوال'
            data['questions']   = {'count': len(questions),   'data': questions}
            data['files']       = {'count': len(qbank_files), 'data': qbank_files}

        await _send_json_file(query, data, filename=f'backup_{section}')

    except Exception as e:
        logger.error(f"Backup section error: {e}")
        await query.edit_message_text(
            f"❌ خطا:\n<code>{e}</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='backup:menu')
            ]]))


async def _send_json_file(query, data: dict, filename: str):
    """ارسال فایل JSON به ادمین"""
    json_str  = json.dumps(data, ensure_ascii=False, indent=2, cls=_Enc)
    file_bytes= json_str.encode('utf-8')
    file_obj  = io.BytesIO(file_bytes)
    now_str   = datetime.now().strftime('%Y%m%d_%H%M')
    fname     = f"{filename}_{now_str}.json"
    file_obj.name = fname

    # خلاصه آمار
    summary = data.get('summary', {})
    if summary:
        stats_lines = [
            f"👥 کاربران: {summary.get('users',0)}",
            f"📖 درس‌ها: {summary.get('lessons',0)}",
            f"📌 جلسات: {summary.get('sessions',0)}",
            f"📁 فایل محتوا: {summary.get('content_files',0)}",
            f"📚 رفرنس (درس): {summary.get('ref_subjects',0)}",
            f"📘 رفرنس (کتاب): {summary.get('ref_books',0)}",
            f"📄 رفرنس (فایل): {summary.get('ref_files',0)}",
            f"🧪 سوالات: {summary.get('questions',0)}",
        ]
        stats_text = "\n".join(stats_lines)
    else:
        size_kb = len(file_bytes) // 1024
        stats_text = f"📦 حجم: {size_kb} KB"

    caption = (
        f"💾 <b>پشتیبان‌گیری موفق</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"{stats_text}\n\n"
        f"📦 حجم: {len(file_bytes)//1024} KB\n\n"
        f"<i>این فایل را در جای امنی نگه‌دارید.\n"
        f"برای بازیابی، از دکمه «بازیابی از فایل» استفاده کنید.</i>"
    )

    try:
        await query.message.reply_document(
            document=file_obj,
            caption=caption,
            parse_mode='HTML',
            filename=fname
        )
        await query.edit_message_text(
            "✅ <b>پشتیبان با موفقیت ارسال شد!</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت به پشتیبان‌گیری", callback_data='backup:menu'),
                InlineKeyboardButton("🏠 پنل ادمین", callback_data='admin:main'),
            ]]))
    except Exception as e:
        logger.error(f"Send backup error: {e}")
        await query.edit_message_text(
            f"❌ خطا در ارسال فایل:\n<code>{e}</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='backup:menu')
            ]]))


# ══════════════════════════════════════════════════
#  Restore — بازیابی از فایل
# ══════════════════════════════════════════════════

async def backup_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت فایل JSON برای بازیابی"""
    uid = update.effective_user.id
    if uid != ADMIN_ID: return
    if context.user_data.get('backup_mode') != 'waiting_restore': return

    doc = update.message.document
    if not doc or not doc.file_name.endswith('.json'):
        await update.message.reply_text(
            "❌ لطفاً یک فایل <b>.json</b> ارسال کنید.",
            parse_mode='HTML')
        return

    if doc.file_size > 50 * 1024 * 1024:  # 50MB limit
        await update.message.reply_text("❌ فایل خیلی بزرگ است (حداکثر ۵۰ مگابایت).")
        return

    await update.message.reply_text("⏳ <b>در حال بررسی فایل...</b>", parse_mode='HTML')

    try:
        tg_file    = await context.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        data       = json.loads(file_bytes.decode('utf-8'))

        version = data.get('backup_version', '1.0')
        created = data.get('created_at', 'نامشخص')[:19]
        section = data.get('section', 'full')

        # ذخیره داده برای تأیید
        context.user_data['restore_data']    = data
        context.user_data['restore_section'] = section

        # آمار فایل
        summary = data.get('summary', {})
        if summary:
            info = "\n".join([
                f"👥 کاربران: {summary.get('users',0)}",
                f"📖 درس‌ها: {summary.get('lessons',0)}",
                f"📁 فایل محتوا: {summary.get('content_files',0)}",
                f"📘 رفرنس کتاب: {summary.get('ref_books',0)}",
                f"🧪 سوالات: {summary.get('questions',0)}",
            ])
        else:
            count = data.get('count', '?')
            info  = f"تعداد رکورد: {count}"

        await update.message.reply_text(
            f"📋 <b>اطلاعات فایل پشتیبان:</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📅 تاریخ ساخت: <code>{created}</code>\n"
            f"🔖 نسخه: {version}\n"
            f"📦 بخش: {section}\n\n"
            f"{info}\n\n"
            f"⚠️ <b>آیا مطمئن هستید؟</b>\n"
            f"داده‌های فعلی با این فایل جایگزین می‌شوند!",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ بله، بازیابی کن", callback_data='backup:confirm_restore')],
                [InlineKeyboardButton("❌ لغو",              callback_data='backup:menu')],
            ]))

    except json.JSONDecodeError:
        await update.message.reply_text("❌ فایل معتبر نیست — JSON خراب است.")
    except Exception as e:
        logger.error(f"Restore parse error: {e}")
        await update.message.reply_text(f"❌ خطا در پردازش فایل:\n<code>{e}</code>",
                                        parse_mode='HTML')


async def backup_confirm_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأیید و اجرای بازیابی"""
    query = update.callback_query
    uid   = update.effective_user.id
    if uid != ADMIN_ID:
        await query.answer("❌ دسترسی ندارید!", show_alert=True); return
    await query.answer()

    data    = context.user_data.get('restore_data')
    section = context.user_data.get('restore_section', 'full')
    if not data:
        await query.edit_message_text("❌ داده‌ای برای بازیابی پیدا نشد. دوباره فایل ارسال کنید.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='backup:menu')
            ]]))
        return

    await query.edit_message_text("⏳ <b>در حال بازیابی اطلاعات...</b>", parse_mode='HTML')

    try:
        restored = {}

        sections = data.get('sections', {})
        if not sections:
            # فایل بخشی (نه کامل)
            sections = {section: data}

        for sec_name, sec_data in sections.items():
            count = await _restore_section(sec_name, sec_data)
            restored[sec_name] = count

        context.user_data.pop('restore_data', None)
        context.user_data.pop('restore_section', None)
        context.user_data.pop('backup_mode', None)

        result_lines = []
        labels = {
            'users':         '👥 کاربران',
            'basic_science': '📘 علوم پایه',
            'references':    '📚 رفرنس‌ها',
            'qbank':         '🧪 بانک سوال',
            'schedules':     '📅 برنامه',
            'faq':           '❓ FAQ',
            'tickets':       '🎫 تیکت‌ها',
        }
        for k, v in restored.items():
            result_lines.append(f"{labels.get(k, k)}: {v} رکورد")

        await query.edit_message_text(
            f"✅ <b>بازیابی با موفقیت انجام شد!</b>\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            + "\n".join(result_lines),
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 پنل ادمین", callback_data='admin:main')
            ]]))

    except Exception as e:
        logger.error(f"Restore error: {e}")
        await query.edit_message_text(
            f"❌ خطا در بازیابی:\n<code>{e}</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='backup:menu')
            ]]))


async def _restore_section(section: str, sec_data: dict) -> int:
    """بازیابی یک بخش — upsert بر اساس _id"""
    from bson import ObjectId

    def _prep(doc):
        """تبدیل string _id به ObjectId"""
        d = dict(doc)
        if '_id' in d and isinstance(d['_id'], str):
            try: d['_id'] = ObjectId(d['_id'])
            except: pass
        # فیلدهای رابطه‌ای
        for fk in ['lesson_id','session_id','subject_id','book_id','user_id']:
            if fk in d and isinstance(d[fk], str) and len(d[fk]) == 24:
                try: d[fk] = str(d[fk])  # نگه داریم به صورت str
                except: pass
        return d

    async def _upsert_many(col, docs):
        count = 0
        for doc in docs:
            doc = _prep(doc)
            _id = doc.get('_id')
            if _id:
                await col.replace_one({'_id': _id}, doc, upsert=True)
            else:
                await col.insert_one(doc)
            count += 1
        return count

    total = 0

    if section == 'users':
        rows = sec_data.get('data', [])
        total += await _upsert_many(db.users, rows)

    elif section == 'basic_science':
        for sub, col in [('lessons','bs_lessons'),('sessions','bs_sessions'),('content','bs_content')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section == 'references':
        for sub, col in [('subjects','ref_subjects'),('books','ref_books'),('files','ref_files')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section == 'qbank':
        for sub, col in [('questions','questions'),('files','qbank_files')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section == 'schedules':
        rows = sec_data.get('data', [])
        total += await _upsert_many(db.schedules, rows)

    elif section == 'faq':
        rows = sec_data.get('data', [])
        total += await _upsert_many(db.faq, rows)

    elif section == 'tickets':
        rows = sec_data.get('data', [])
        total += await _upsert_many(db.tickets, rows)

    return total

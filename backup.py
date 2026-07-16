"""
سیستم پشتیبان‌گیری و بازیابی ربات
- Export: JSON کامل از همه دیتابیس‌ها
- Import: بازیابی از فایل JSON
- فقط ادمین اصلی دسترسی دارد
"""
import os, json, logging, io
from datetime import datetime
from utils import fmt_jalali_dt, now_tehran
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

    elif action == 'export_subscription':
        await query.edit_message_text("⏳ در حال آماده‌سازی...", parse_mode='HTML')
        await _export_section(query, 'subscription')

    elif action == 'export_grades':
        await query.edit_message_text("⏳ در حال آماده‌سازی...", parse_mode='HTML')
        await _export_section(query, 'grades')

    elif action == 'export_access':
        await query.edit_message_text("⏳ در حال آماده‌سازی...", parse_mode='HTML')
        await _export_section(query, 'access')

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

    # ══════════════════════════════════════════════
    # FIX جدید: بکاپ خودکار زمان‌بندی‌شده
    # ══════════════════════════════════════════════
    elif action == 'auto_settings':
        await _show_auto_settings(query)

    elif action == 'auto_toggle':
        current = await db.get_setting('auto_backup_enabled', False)
        await db.set_setting('auto_backup_enabled', not current)
        await query.answer("✅ بکاپ خودکار فعال شد" if not current else "❌ بکاپ خودکار غیرفعال شد", show_alert=True)
        await _show_auto_settings(query)

    elif action == 'auto_hour':
        hour = int(parts[2])
        await db.set_setting('auto_backup_hour', hour)
        await query.answer(f"✅ ساعت بکاپ خودکار: {hour}:00", show_alert=True)
        await _show_auto_settings(query)

    elif action == 'auto_hour_custom':
        context.user_data['mode'] = 'set_auto_backup_hour'
        await query.edit_message_text(
            "✏️ <b>ساعت بکاپ خودکار</b>\n\n"
            "عددی بین ۰ تا ۲۳ بفرستید (به‌وقت تهران):",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='backup:auto_settings')
            ]])
        )


async def _show_auto_settings(query):
    """
    FIX جدید: تنظیمات بکاپ خودکار — روشن/خاموش + انتخاب ساعت اجرا.
    بکاپ تولیدشده مستقیماً برای ادمین ارشد (ADMIN_ID) ارسال می‌شود.
    """
    enabled = await db.get_setting('auto_backup_enabled', False)
    hour    = await db.get_setting('auto_backup_hour', 3)
    last_run = await db.get_setting('auto_backup_last_run', None)
    last_run_label = last_run[:16].replace('T', ' ') if last_run else 'هنوز اجرا نشده'

    status_label = f"✅ فعال — هر روز ساعت {hour}:00" if enabled else "⬜ غیرفعال"
    toggle_label  = "🔴 غیرفعال کردن" if enabled else "🟢 فعال کردن"

    text = (
        "⏰ <b>بکاپ خودکار</b>\n━━━━━━━━━━━━━━━━\n\n"
        f"وضعیت: <b>{status_label}</b>\n"
        f"🕐 آخرین اجرا: <code>{last_run_label}</code>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📌 بکاپ کامل هر روز در ساعت تعیین‌شده (به‌وقت تهران) "
        "خودکار ساخته و برای شما ارسال می‌شود."
    )
    keyboard = [
        [InlineKeyboardButton(toggle_label, callback_data='backup:auto_toggle')],
        [
            InlineKeyboardButton("01:00" + (" ✅" if hour == 1 else ""), callback_data='backup:auto_hour:1'),
            InlineKeyboardButton("02:00" + (" ✅" if hour == 2 else ""), callback_data='backup:auto_hour:2'),
            InlineKeyboardButton("03:00" + (" ✅" if hour == 3 else ""), callback_data='backup:auto_hour:3'),
        ],
        [
            InlineKeyboardButton("04:00" + (" ✅" if hour == 4 else ""), callback_data='backup:auto_hour:4'),
            InlineKeyboardButton("05:00" + (" ✅" if hour == 5 else ""), callback_data='backup:auto_hour:5'),
            InlineKeyboardButton("23:00" + (" ✅" if hour == 23 else ""), callback_data='backup:auto_hour:23'),
        ],
        [InlineKeyboardButton("✏️ ساعت دیگر (عدد ۰ تا ۲۳)", callback_data='backup:auto_hour_custom')],
        [InlineKeyboardButton("🔙 بازگشت", callback_data='backup:menu')],
    ]
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_menu(query):
    now = fmt_jalali_dt(now_tehran().isoformat())
    auto_on = await db.get_setting('auto_backup_enabled', False)
    auto_hour = await db.get_setting('auto_backup_hour', 3)
    auto_label = f"⏰ بکاپ خودکار: {'فعال — ساعت ' + str(auto_hour) + ':00' if auto_on else 'غیرفعال'}"
    kb = [
        [InlineKeyboardButton("💾 پشتیبان کامل (همه بخش‌ها)", callback_data='backup:export_all')],
        [InlineKeyboardButton("👥 فقط کاربران",    callback_data='backup:export_users'),
         InlineKeyboardButton("📚 علوم پایه",       callback_data='backup:export_content')],
        [InlineKeyboardButton("📖 رفرنس‌ها",        callback_data='backup:export_refs'),
         InlineKeyboardButton("🧪 بانک سوال",       callback_data='backup:export_qbank')],
        [InlineKeyboardButton("💳 اشتراک و پرداخت", callback_data='backup:export_subscription'),
         InlineKeyboardButton("📊 نمرات",           callback_data='backup:export_grades')],
        [InlineKeyboardButton("🔐 دسترسی‌ها و تنظیمات", callback_data='backup:export_access')],
        [InlineKeyboardButton("📥 بازیابی از فایل", callback_data='backup:restore_prompt')],
        [InlineKeyboardButton(auto_label, callback_data='backup:auto_settings')],
        [InlineKeyboardButton("🔙 بازگشت به پنل",   callback_data='admin:cat_settings')],
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

async def build_full_backup_data() -> dict:
    """
    FIX جدید: منطق ساخت بکاپ کامل از _export_all جدا شد تا هم از
    callback پنل ادمین و هم از job بکاپ خودکار قابل استفاده باشد.
    """
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

    # ── FIX جدید: دسترسی‌ها و امنیت — نقش‌های ادمین، بلک‌لیست، ورودی‌ها ──
    # این‌ها حیاتی‌اند: اگه گم بشن، همه‌ی نقش‌های تفویض‌شده (نماینده‌ها،
    # مدیران محتوای محدود و...) و لیست کاربران بلاک‌شده از دست می‌ره.
    admin_roles = await db.admin_roles.find({}).to_list(1000)
    blacklist   = await db.blacklist.find({}).to_list(5000)
    intakes     = await db.intakes.find({}).to_list(500)
    data['sections']['access_control'] = {
        'description': 'دسترسی‌ها و امنیت — نقش‌های ادمین، بلک‌لیست، ورودی‌ها',
        'admin_roles': {'count': len(admin_roles), 'data': admin_roles},
        'blacklist':   {'count': len(blacklist),   'data': blacklist},
        'intakes':     {'count': len(intakes),     'data': intakes},
    }

    # ── FIX جدید: سیستم اشتراک — دقیقاً همون چیزی که قبلاً توی بکاپ نبود ──
    sub_plans     = await db.sub_plans.find({}).to_list(200)
    subscriptions = await db.subscriptions.find({}).to_list(20000)
    sub_payments  = await db.sub_payments.find({}).to_list(20000)
    discount_codes= await db.discount_codes.find({}).to_list(1000)
    data['sections']['subscription_system'] = {
        'description': 'سیستم اشتراک — پلن‌ها، وضعیت هر کاربر، رسیدهای پرداخت، کدهای تخفیف',
        'plans':          {'count': len(sub_plans),      'data': sub_plans},
        'subscriptions':  {'count': len(subscriptions),  'data': subscriptions},
        'payments':       {'count': len(sub_payments),   'data': sub_payments},
        'discount_codes': {'count': len(discount_codes), 'data': discount_codes},
    }

    # ── FIX جدید: نمرات ──
    grades = await db.grades.find({}).to_list(20000)
    data['sections']['grades'] = {
        'description': 'نمرات ثبت‌شده توسط ادمین/نماینده‌های ورودی',
        'count':       len(grades),
        'data':        grades
    }

    # ── FIX جدید: تنظیمات کلی ربات — یک سند واحد (شماره کارت، کلید
    # اجباری اشتراک، بازه نوتیف، حالت تعمیر، لینک حمایت مالی و...) ──
    settings_doc = await db.settings.find_one({'_id': 'global'})
    data['sections']['settings'] = {
        'description': 'تنظیمات کلی ربات (یک سند واحد)',
        'count':       1 if settings_doc else 0,
        'data':        settings_doc or {},
    }

    # ── FIX جدید: گزارش‌ها و لاگ‌ها — کمتر حیاتی، ولی برای پیگیری مفیدن ──
    content_reports = await db.content_reports.find({}).to_list(3000)
    audit_logs       = await db.audit_logs.find({}).to_list(3000)
    notif_runs        = await db.notif_runs.find({}).to_list(1000)
    data['sections']['logs'] = {
        'description': 'گزارش محتوا، لاگ فعالیت‌های حساس، تاریخچه‌ی اجرای نوتیف‌ها',
        'content_reports': {'count': len(content_reports), 'data': content_reports},
        'audit_logs':       {'count': len(audit_logs),       'data': audit_logs},
        'notif_runs':        {'count': len(notif_runs),        'data': notif_runs},
    }

    # ── FIX جدید: آمار خام — پاسخ‌های دانشجویان به سوالات ──
    stats_rows = await db.stats_col.find({}).to_list(20000)
    answers    = await db.answers.find({}).to_list(30000)
    data['sections']['stats'] = {
        'description': 'آمار خام تمرین‌ها — ممکن است در حجم خیلی بالا محدود (cap) شده باشد',
        'stats':   {'count': len(stats_rows), 'data': stats_rows},
        'answers': {'count': len(answers),    'data': answers},
    }

    # آمار خلاصه
    data['summary'] = {
        'users':          len(users),
        'lessons':        len(lessons),
        'sessions':       len(sessions),
        'content_files':  len(content),
        'ref_subjects':   len(subjects),
        'ref_books':      len(books),
        'ref_files':      len(ref_files),
        'questions':      len(questions),
        'schedules':      len(schedules),
        'faqs':           len(faqs),
        'tickets':        len(tickets),
        'admin_roles':    len(admin_roles),
        'blacklist':      len(blacklist),
        'intakes':        len(intakes),
        'sub_plans':      len(sub_plans),
        'subscriptions':  len(subscriptions),
        'sub_payments':   len(sub_payments),
        'discount_codes': len(discount_codes),
        'grades':         len(grades),
        'settings':       1 if settings_doc else 0,
        'content_reports':len(content_reports),
        'audit_logs':     len(audit_logs),
        'notif_runs':     len(notif_runs),
        'stats_rows':     len(stats_rows),
        'answers':        len(answers),
    }
    return data


async def _export_all(query, context):
    """پشتیبان کامل از همه بخش‌ها — برای دکمه پنل ادمین"""
    try:
        data = await build_full_backup_data()
        await _send_json_file(query, data, filename='backup_full')
    except Exception as e:
        logger.error(f"Backup error: {e}")
        await query.edit_message_text(
            f"❌ خطا در پشتیبان‌گیری:\n<code>{e}</code>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='backup:menu')
            ]]))


async def send_backup_to_bot_chat(bot, chat_id: int, data: dict, filename: str = 'backup_auto'):
    """
    FIX جدید: ارسال فایل بکاپ مستقیماً با bot.send_document — برای
    استفاده در job بکاپ خودکار، که query/callback در دسترس نیست.
    """
    json_str   = json.dumps(data, ensure_ascii=False, indent=2, cls=_Enc)
    file_bytes = json_str.encode('utf-8')
    file_obj   = io.BytesIO(file_bytes)
    now_str    = datetime.now().strftime('%Y%m%d_%H%M')
    fname      = f"{filename}_{now_str}.json"
    file_obj.name = fname

    summary = data.get('summary', {})
    stats_lines = [
        f"👥 کاربران: {summary.get('users',0)}",
        f"📖 درس‌ها: {summary.get('lessons',0)}",
        f"🧪 سوالات: {summary.get('questions',0)}",
        f"🎫 تیکت‌ها: {summary.get('tickets',0)}",
    ]
    caption = (
        f"💾 <b>بکاپ خودکار روزانه</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🕐 {fmt_jalali_dt(now_tehran().isoformat())}\n\n"
        + '\n'.join(stats_lines) +
        f"\n\n📦 حجم: {len(file_bytes)//1024} KB"
    )
    await bot.send_document(
        chat_id, document=file_obj, caption=caption,
        parse_mode='HTML', filename=fname
    )


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

        elif section == 'subscription':
            sub_plans      = await db.sub_plans.find({}).to_list(200)
            subscriptions  = await db.subscriptions.find({}).to_list(20000)
            sub_payments   = await db.sub_payments.find({}).to_list(20000)
            discount_codes = await db.discount_codes.find({}).to_list(1000)
            data['description']     = 'سیستم اشتراک — پلن‌ها، وضعیت کاربران، رسیدها، کدهای تخفیف'
            data['plans']           = {'count': len(sub_plans),      'data': sub_plans}
            data['subscriptions']   = {'count': len(subscriptions),  'data': subscriptions}
            data['payments']        = {'count': len(sub_payments),   'data': sub_payments}
            data['discount_codes']  = {'count': len(discount_codes), 'data': discount_codes}

        elif section == 'grades':
            grades = await db.grades.find({}).to_list(20000)
            data['description'] = 'نمرات ثبت‌شده'
            data['count']       = len(grades)
            data['data']        = grades

        elif section == 'access':
            admin_roles  = await db.admin_roles.find({}).to_list(1000)
            blacklist    = await db.blacklist.find({}).to_list(5000)
            intakes      = await db.intakes.find({}).to_list(500)
            settings_doc = await db.settings.find_one({'_id': 'global'})
            data['description'] = 'دسترسی‌ها (نقش/بلک‌لیست/ورودی) + تنظیمات ربات'
            data['admin_roles'] = {'count': len(admin_roles), 'data': admin_roles}
            data['blacklist']   = {'count': len(blacklist),   'data': blacklist}
            data['intakes']     = {'count': len(intakes),     'data': intakes}
            data['settings']    = {'count': 1 if settings_doc else 0, 'data': settings_doc or {}}

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
        f"🕐 {fmt_jalali_dt(now_tehran().isoformat())}\n\n"
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

async def handle_auto_backup_hour_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """FIX جدید: دریافت ساعت دلخواه بکاپ خودکار به‌صورت متنی"""
    text = update.message.text.strip()
    context.user_data.pop('mode', None)
    if not text.isdigit() or not (0 <= int(text) <= 23):
        await update.message.reply_text("❌ عدد باید بین ۰ تا ۲۳ باشد. دوباره تلاش کنید.")
        return
    hour = int(text)
    await db.set_setting('auto_backup_hour', hour)
    await update.message.reply_text(
        f"✅ ساعت بکاپ خودکار روی <b>{hour}:00</b> تنظیم شد.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⏰ بازگشت به تنظیمات بکاپ", callback_data='backup:auto_settings')
        ]])
    )


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
                f"💳 اشتراک‌ها: {summary.get('subscriptions',0)}",
                f"🧾 رسیدهای پرداخت: {summary.get('sub_payments',0)}",
                f"📊 نمرات: {summary.get('grades',0)}",
                f"🔐 نقش‌های ادمین: {summary.get('admin_roles',0)}",
                f"⚙️ تنظیمات ربات: {'دارد' if summary.get('settings',0) else 'ندارد'}",
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
            'users':               '👥 کاربران',
            'basic_science':       '📘 علوم پایه',
            'references':          '📚 رفرنس‌ها',
            'qbank':                '🧪 بانک سوال',
            'schedules':            '📅 برنامه',
            'faq':                  '❓ FAQ',
            'tickets':              '🎫 تیکت‌ها',
            'access_control':       '🔐 دسترسی‌ها (نقش/بلک‌لیست/ورودی)',
            'subscription_system':  '💳 اشتراک و پرداخت',
            'grades':                '📊 نمرات',
            'settings':              '⚙️ تنظیمات ربات',
            'logs':                  '📋 گزارش‌ها و لاگ‌ها',
            'stats':                 '📈 آمار خام تمرین‌ها',
        }
        for k, v in restored.items():
            result_lines.append(f"{labels.get(k, k)}: {v} رکورد")

        # FIX جدید طبق سند: بازیابی بکاپ = CRITICAL — این عمل می‌تواند
        # کل دیتابیس را بازنویسی کند، باید بسیار برجسته و قابل ردیابی باشد.
        from utils import send_audit_log
        admin_user_doc = await db.get_user(uid)
        actor_name = admin_user_doc.get('name', 'ادمین') if admin_user_doc else 'ادمین'
        actor_role = await db.get_actor_role_label(uid)
        await send_audit_log(
            context.bot, 'admin', actor_name, uid,
            "بازیابی بکاپ", module='Backup', severity='CRITICAL',
            actor_role=actor_role,
            target_type='backup', target_label=section,
            details=' | '.join(result_lines),
            tags=['بازیابی_بکاپ']
        )

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
        try:
            from utils import send_audit_log
            await send_audit_log(
                context.bot, 'admin', 'ادمین', uid,
                "خطا در بازیابی بکاپ", module='Backup', severity='CRITICAL',
                details=str(e)[:200], tags=['خطای_بازیابی']
            )
        except Exception:
            pass
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

    elif section in ('basic_science', 'content'):
        for sub, col in [('lessons','bs_lessons'),('sessions','bs_sessions'),('content','bs_content')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section in ('references', 'refs'):
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

    # ── FIX جدید: بازیابی بخش‌های تازه‌اضافه‌شده — با alias برای هر دو
    # نامی که ممکنه فایل بکاپ داشته باشه (بکاپ کامل در برابر بکاپ سریع) ──
    elif section in ('access_control', 'access'):
        for sub, col in [('admin_roles', 'admin_roles'), ('blacklist', 'blacklist'), ('intakes', 'intakes')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)
        # بکاپ سریع «دسترسی‌ها و تنظیمات» شامل settings هم می‌شود
        settings_data = dict(sec_data.get('settings', {}).get('data', {}) or {})
        if settings_data:
            settings_data.pop('_id', None)
            await db.settings.update_one({'_id': 'global'}, {'$set': settings_data}, upsert=True)
            total += 1

    elif section in ('subscription_system', 'subscription'):
        for sub, col in [('plans', 'sub_plans'), ('subscriptions', 'subscriptions'),
                          ('payments', 'sub_payments'), ('discount_codes', 'discount_codes')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section == 'grades':
        rows = sec_data.get('data', [])
        total += await _upsert_many(db.grades, rows)

    elif section == 'settings':
        # سند تنظیمات یک رکورد واحده (_id='global')، نه لیست — merge
        # می‌کنیم (نه جایگزینی کامل) تا تنظیماتی که بعد از این بکاپ
        # روی سرور فعلی ست شده‌اند حذف نشوند.
        settings_data = dict(sec_data.get('data', {}) or {})
        if settings_data:
            settings_data.pop('_id', None)
            await db.settings.update_one({'_id': 'global'}, {'$set': settings_data}, upsert=True)
            total += 1

    elif section == 'logs':
        for sub, col in [('content_reports', 'content_reports'),
                          ('audit_logs', 'audit_logs'), ('notif_runs', 'notif_runs')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    elif section == 'stats':
        for sub, col in [('stats', 'stats_col'), ('answers', 'answers')]:
            rows = sec_data.get(sub, {}).get('data', [])
            total += await _upsert_many(getattr(db, col), rows)

    return total

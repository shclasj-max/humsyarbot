"""
⚠️ سیستم گزارش ایراد سوال/جزوه
  ✅ دانشجو دلیل را انتخاب می‌کند (پاسخ اشتباه، فایل خراب و غیره)
  ✅ همزمان به مدیریت اصلی + ادمین محتوا + طراح سوال + رول خرخون ارسال می‌شود
  ✅ داشبورد مدیریت گزارشات با وضعیت (جدید/در حال بررسی/رفع شده/رد شده)
"""
import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from utils import send_audit_log

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))


async def report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ورودی: report:question:<qid> یا report:resource:<rid> یا report:reason:<reason>"""
    query  = update.callback_query
    await query.answer()
    uid    = update.effective_user.id
    parts  = query.data.split(':')
    action = parts[1] if len(parts) > 1 else ''

    if action in ('question', 'resource'):
        target_type = action
        target_id   = parts[2]
        context.user_data['report_target_type'] = target_type
        context.user_data['report_target_id']   = target_id
        await _show_reason_picker(query, target_type)

    elif action == 'reason':
        reason = parts[2]
        if reason == 'other':
            context.user_data['report_reason'] = reason
            context.user_data['mode'] = 'report_note'
            await query.edit_message_text(
                "📝 <b>توضیح ایراد را بنویسید:</b>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ لغو", callback_data='report:cancel')
                ]])
            )
            return
        await _finalize_report(update, context, reason, '')

    elif action == 'cancel':
        for k in ('report_target_type', 'report_target_id', 'report_reason', 'mode'):
            context.user_data.pop(k, None)
        await query.edit_message_text("❌ گزارش لغو شد.")

    elif action == 'manage':
        await _show_reports_dashboard(query, parts[2] if len(parts) > 2 else None)

    elif action == 'view':
        rid = int(parts[2])
        await _show_report_detail(query, rid)

    elif action == 'status':
        rid    = int(parts[2])
        status = parts[3]
        await db.update_report_status(rid, status, uid)
        admin_user = await db.get_user(uid)
        actor_name = admin_user.get('name', 'ادمین') if admin_user else 'ادمین'
        status_fa  = {'reviewing': 'در حال بررسی', 'resolved': 'رفع شد', 'rejected': 'رد شد'}.get(status, status)
        await send_audit_log(
            context.bot, 'content', actor_name, uid,
            f"تغییر وضعیت گزارش #{rid}", f"وضعیت جدید: {status_fa}"
        )
        await query.answer(f"✅ وضعیت: {status_fa}", show_alert=True)
        await _show_report_detail(query, rid)


async def _show_reason_picker(query, target_type: str):
    label = "سوال" if target_type == 'question' else "جزوه/فایل"
    keyboard = [
        [InlineKeyboardButton(f"❌ {v}", callback_data=f'report:reason:{k}')]
        for k, v in db.REPORT_REASONS.items()
    ]
    keyboard.append([InlineKeyboardButton("🔙 انصراف", callback_data='report:cancel')])
    await query.edit_message_text(
        f"⚠️ <b>گزارش ایراد {label}</b>\n\n"
        "دلیل گزارش را انتخاب کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_report_note_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت متن توضیح وقتی دلیل 'سایر' انتخاب شده"""
    note = update.message.text.strip()
    reason = context.user_data.get('report_reason', 'other')
    context.user_data.pop('mode', None)
    await _finalize_report(update, context, reason, note)


async def _finalize_report(update_or_query, context, reason: str, note: str):
    """
    ثبت نهایی گزارش + ارسال همزمان به مدیریت اصلی، ادمین محتوا،
    طراح سوال (اگر target سوال بود)، و همه‌ی اعضای رول خرخون.
    """
    target_type = context.user_data.pop('report_target_type', '')
    target_id   = context.user_data.pop('report_target_id', '')
    context.user_data.pop('report_reason', None)

    is_callback = hasattr(update_or_query, 'callback_query') and update_or_query.callback_query is not None
    query = update_or_query.callback_query if is_callback else None
    uid   = update_or_query.effective_user.id
    reporter = await db.get_user(uid)
    reporter_name = reporter.get('name', 'کاربر') if reporter else 'کاربر'

    # عنوان و طراح (اگه سوال باشد)
    designer_id = None
    title = ''
    if target_type == 'question':
        q = await db.get_question_by_id(target_id)
        if q:
            title = q.get('question', '')[:80]
            designer_id = q.get('creator_id')
    else:
        item = await db.bs_get_content_item(target_id)
        if item:
            title = item.get('description', '') or 'فایل بدون توضیح'

    report_id = await db.create_content_report(
        target_type, target_id, uid, reporter_name, reason, note, designer_id
    )

    reason_fa = db.REPORT_REASONS.get(reason, reason)
    target_label = "🧪 سوال" if target_type == 'question' else "📁 جزوه/فایل"

    notify_text = (
        f"🆕 <b>گزارش ایراد جدید #{report_id}</b>\n\n"
        f"{target_label}: {title}\n"
        f"❌ دلیل: {reason_fa}\n"
        + (f"📝 توضیح: {note}\n" if note else "") +
        f"👤 گزارش‌دهنده: {reporter_name}\n\n"
        f"برای بررسی به پنل ادمین مراجعه کنید."
    )
    notify_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔍 بررسی گزارش", callback_data=f'report:view:{report_id}')
    ]])

    # ── ارسال همزمان به همه ذی‌نفعان ──
    recipients = set()
    recipients.add(ADMIN_ID)
    content_admins = await db.get_content_admins()
    for ca in content_admins:
        recipients.add(ca['user_id'])
    reviewers = await db.get_reviewers()
    recipients.update(reviewers)
    if designer_id:
        recipients.add(designer_id)
    recipients.discard(uid)  # خود گزارش‌دهنده نباید نوتیف بگیرد

    for rid_target in recipients:
        try:
            # برای طراح سوال متن کمی متفاوت — لحن همکارانه
            if rid_target == designer_id and rid_target not in (ADMIN_ID,):
                designer_text = (
                    f"🔔 <b>گزارش روی سوال شما ثبت شد</b>\n\n"
                    f"🧪 سوال: {title}\n"
                    f"❌ دلیل: {reason_fa}\n"
                    + (f"📝 توضیح: {note}\n" if note else "") +
                    f"\nلطفاً سوال را بررسی و در صورت نیاز اصلاح کنید 🙏"
                )
                await context.bot.send_message(rid_target, designer_text, parse_mode='HTML')
            else:
                await context.bot.send_message(rid_target, notify_text, parse_mode='HTML',
                                               reply_markup=notify_kb)
        except Exception as e:
            logger.debug(f"report notify failed for {rid_target}: {e}")

    confirm_text = (
        f"✅ <b>گزارش شما با شماره #{report_id} ثبت شد!</b>\n\n"
        "تیم مدیریت و طراح محتوا مطلع شدند. متشکریم از همکاری شما 🙏"
    )
    if query:
        await query.edit_message_text(confirm_text, parse_mode='HTML')
    else:
        await update_or_query.message.reply_text(confirm_text, parse_mode='HTML')


# ══════════════════════════════════════════════════
#  داشبورد مدیریت گزارشات
# ══════════════════════════════════════════════════

async def show_reports_main(message, uid: int):
    """فراخوانی از منوی پنل ادمین/محتوا"""
    stats = await db.content_reports_stats()
    text = (
        "📋 <b>گزارشات سوال و جزوه</b>\n━━━━━━━━━━━━━━━━\n\n"
        f"🆕 جدید: <b>{stats['new']}</b>\n"
        f"🔍 در حال بررسی: <b>{stats['reviewing']}</b>\n"
        f"✅ رفع شده: <b>{stats['resolved']}</b>\n"
        f"❌ رد شده: <b>{stats['rejected']}</b>"
    )
    keyboard = [
        [InlineKeyboardButton(f"🆕 جدید ({stats['new']})", callback_data='report:manage:new')],
        [InlineKeyboardButton(f"🔍 در حال بررسی ({stats['reviewing']})", callback_data='report:manage:reviewing')],
        [InlineKeyboardButton("📋 همه گزارشات", callback_data='report:manage:all')],
    ]
    await message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_reports_dashboard(query, status_filter: str = None):
    status = None if status_filter in (None, 'all') else status_filter
    reports = await db.get_content_reports(status, limit=20)
    status_fa = {'new': 'جدید', 'reviewing': 'در حال بررسی', None: 'همه'}.get(status, status)

    if not reports:
        await query.edit_message_text(
            f"📋 گزارشات ({status_fa}): هیچ موردی یافت نشد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data='admin:main')
            ]])
        )
        return

    keyboard = []
    for r in reports:
        rid = r['report_id']
        icon = {'new': '🆕', 'reviewing': '🔍', 'resolved': '✅', 'rejected': '❌'}.get(r['status'], '❔')
        label = f"{icon} #{rid} — {db.REPORT_REASONS.get(r['reason'], r['reason'])}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f'report:view:{rid}')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:main')])
    await query.edit_message_text(
        f"📋 <b>گزارشات — {status_fa}</b>\n━━━━━━━━━━━━━━━━",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_report_detail(query, report_id: int):
    r = await db.get_content_report(report_id)
    if not r:
        await query.answer("❌ گزارش پیدا نشد!", show_alert=True)
        return

    target_label = "🧪 سوال" if r['target_type'] == 'question' else "📁 جزوه/فایل"
    title = ''
    if r['target_type'] == 'question':
        q = await db.get_question_by_id(r['target_id'])
        if q:
            title = q.get('question', '')
    else:
        item = await db.bs_get_content_item(r['target_id'])
        if item:
            title = item.get('description', '')

    status_fa = {'new': '🆕 جدید', 'reviewing': '🔍 در حال بررسی',
                 'resolved': '✅ رفع شده', 'rejected': '❌ رد شده'}.get(r['status'], r['status'])
    reason_fa = db.REPORT_REASONS.get(r['reason'], r['reason'])

    text = (
        f"📋 <b>گزارش #{r['report_id']}</b>\n━━━━━━━━━━━━━━━━\n\n"
        f"{target_label}: {title}\n\n"
        f"❌ دلیل: {reason_fa}\n"
        + (f"📝 توضیح: {r.get('note','')}\n" if r.get('note') else "") +
        f"👤 گزارش‌دهنده: {r['reporter_name']}\n"
        f"🕐 تاریخ: {r['created_at'][:16].replace('T',' ')}\n\n"
        f"📊 وضعیت: <b>{status_fa}</b>"
    )
    keyboard = []
    if r['status'] not in ('resolved', 'rejected'):
        keyboard.append([
            InlineKeyboardButton("🔍 در حال بررسی", callback_data=f'report:status:{report_id}:reviewing'),
        ])
        keyboard.append([
            InlineKeyboardButton("✅ رفع شد",  callback_data=f'report:status:{report_id}:resolved'),
            InlineKeyboardButton("❌ رد شد",   callback_data=f'report:status:{report_id}:rejected'),
        ])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به لیست", callback_data='report:manage:all')])
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

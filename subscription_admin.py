"""
💳 پنل مدیریت اشتراک — فقط ادمین ارشد (ADMIN_ID)
  ✅ کلید اجباری‌سازی سراسری (پیش‌فرض خاموش)
  ✅ چند پلن هم‌زمان — قیمت/روز هرکدام مستقل
  ✅ شماره کارت
  ✅ صف رسیدهای در انتظار
  ✅ مدیریت دستی اشتراک هر کاربر (فعال/تمدید/لغو با دلیل)
  ✅ کدهای تخفیف درصدی
  ✅ اعطای رایگان دسته‌جمعی بر اساس نقش
  ✅ آمار
"""
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from utils import send_audit_log, safe_send

logger = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))


def _fmt_price(p: int) -> str:
    return f"{p:,}".replace(',', '٬') + " تومان"


def _back(cb='suba:main'):
    return [InlineKeyboardButton("🔙 بازگشت", callback_data=cb)]


# ══════════════════════════════════════════════════
#  منوی اصلی
# ══════════════════════════════════════════════════

async def _show_main(query):
    enforced = await db.get_setting('subscription_enforced', False)
    protect  = await db.get_setting('protect_content_enabled', True)
    stats = await db.sub_stats()
    status_txt  = "🟢 اجباری (فعال روی همه)" if enforced else "🔴 غیرفعال (فعلاً همه دسترسی دارن)"
    protect_txt = "🟢 روشن (فوروارد/ذخیره غیرفعاله)" if protect else "🔴 خاموش (فوروارد/ذخیره آزاده)"
    text = (
        f"💳 <b>مدیریت اشتراک</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"وضعیت اجباری اشتراک: {status_txt}\n"
        f"🔒 محافظت کپی‌رایت فایل‌ها: {protect_txt}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"✅ فعال: <b>{stats['active']}</b>  |  ⏳ در انتظار: <b>{stats['pending']}</b>\n"
        f"⌛ منقضی: {stats['expired']}  |  🚫 لغوشده: {stats['revoked']}\n\n"
        f"💰 درآمد این ماه: <b>{_fmt_price(stats['revenue_month'])}</b>\n"
        f"💰 درآمد کل: {_fmt_price(stats['revenue'])}\n"
        f"📈 نرخ تأیید: {stats['conv_rate']}٪  ({stats['approved_total']} تأیید / {stats['rejected_total']} رد)\n"
        f"🏆 پرفروش‌ترین پلن: {stats['top_plan']}"
    )
    toggle_label  = "🔴 خاموش‌کردن اجباری اشتراک" if enforced else "🟢 اجباری‌کردن اشتراک برای همه"
    protect_label = "🔴 خاموش‌کردن محافظت فایل‌ها" if protect else "🟢 روشن‌کردن محافظت فایل‌ها"
    keyboard = [
        [InlineKeyboardButton(toggle_label, callback_data='suba:toggle_enforce')],
        [InlineKeyboardButton(protect_label, callback_data='suba:toggle_protect')],
        [InlineKeyboardButton("📋 پلن‌ها", callback_data='suba:plans'),
         InlineKeyboardButton("💳 شماره کارت", callback_data='suba:card')],
        [InlineKeyboardButton(f"📥 صف در انتظار ({stats['pending']})", callback_data='suba:pending'),
         InlineKeyboardButton("📜 تاریخچه‌ی کامل", callback_data='suba:history:all:0')],
        [InlineKeyboardButton(f"📋 لیست مشترکین فعال ({stats['active']})", callback_data='suba:subscribers:0')],
        [InlineKeyboardButton("👤 مدیریت اشتراک کاربر", callback_data='suba:user_search')],
        [InlineKeyboardButton("🎟 کدهای تخفیف", callback_data='suba:discounts')],
        [InlineKeyboardButton("🎁 اعطای رایگان دسته‌جمعی", callback_data='suba:grant')],
        _back('admin:cat_settings'),
    ]
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════════
#  تاریخچه‌ی کامل رسیدها (همه‌ی وضعیت‌ها + فیلتر + صفحه‌بندی)
# ══════════════════════════════════════════════════

_HISTORY_FILTERS = {
    'all': ('همه', None), 'pending': ('در انتظار', 'pending'),
    'approved': ('تأییدشده', 'approved'), 'rejected': ('ردشده', 'rejected'),
}
_HISTORY_PAGE_SIZE = 8


async def _show_history(query, filt: str, page: int):
    label, status = _HISTORY_FILTERS.get(filt, ('همه', None))
    total = await db.sub_payment_count_all(status)
    items = await db.sub_payment_list_all(status, skip=page * _HISTORY_PAGE_SIZE, limit=_HISTORY_PAGE_SIZE)
    icons = {'pending': '⏳', 'approved': '✅', 'rejected': '❌'}

    lines = [f"📜 <b>تاریخچه‌ی رسیدها</b> — {label} ({total})\n━━━━━━━━━━━━━━━━"]
    if not items:
        lines.append("چیزی پیدا نشد.")
    for p in items:
        user = await db.get_user(p['user_id'])
        name = user.get('name', str(p['user_id'])) if user else str(p['user_id'])
        icon = icons.get(p['status'], '•')
        lines.append(f"{icon} {name} — {p['plan_name']} — {_fmt_price(p['final_price'])}")

    # فیلترها
    filter_row = [
        InlineKeyboardButton(('🔘 ' if k == filt else '') + v[0], callback_data=f'suba:history:{k}:0')
        for k, v in _HISTORY_FILTERS.items()
    ]
    keyboard = [filter_row]

    # صفحه‌بندی
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ قبلی", callback_data=f'suba:history:{filt}:{page-1}'))
    if (page + 1) * _HISTORY_PAGE_SIZE < total:
        nav_row.append(InlineKeyboardButton("بعدی ▶️", callback_data=f'suba:history:{filt}:{page+1}'))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append(_back())
    await query.edit_message_text("\n".join(lines), parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════════
#  پلن‌ها
# ══════════════════════════════════════════════════

async def _show_plans(query):
    plans = await db.sub_plan_list()
    lines = ["📋 <b>پلن‌های اشتراک</b>\n━━━━━━━━━━━━━━━━"]
    keyboard = []
    if not plans:
        lines.append("هنوز پلنی تعریف نشده.")
    for p in plans:
        mark = "✅" if p.get('active') else "⛔️"
        sold = await db.sub_payments.count_documents({'plan_id': str(p['_id']), 'status': 'approved'})
        lines.append(f"{mark} {p['name']} — {p['days']} روز — {_fmt_price(p['price'])} — 🛒 {sold} فروش")
        keyboard.append([
            InlineKeyboardButton("✏️ ویرایش", callback_data=f"suba:plan_edit:{p['_id']}"),
            InlineKeyboardButton(f"{'⛔️ غیرفعال' if p.get('active') else '✅ فعال'}",
                                  callback_data=f"suba:plan_toggle:{p['_id']}"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"suba:plan_del:{p['_id']}"),
        ])
    keyboard.append([InlineKeyboardButton("➕ پلن جدید", callback_data='suba:plan_add')])
    keyboard.append(_back())
    await query.edit_message_text("\n".join(lines), parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _prompt_plan_edit(query, context, plan_id: str):
    plan = await db.sub_plan_get(plan_id)
    if not plan:
        await query.answer("❌ پلن پیدا نشد.", show_alert=True)
        return
    context.user_data['mode'] = 'suba_plan_edit'
    context.user_data['suba_plan_edit_id'] = plan_id
    await query.edit_message_text(
        f"✏️ <b>ویرایش «{plan['name']}»</b>\n\n"
        f"مقدار فعلی: {plan['days']} روز — {_fmt_price(plan['price'])}\n\n"
        "فرم جدید رو بفرست:\n<code>نام | روز | قیمت</code>\n\n"
        f"مثال:\n<code>{plan['name']} | {plan['days']} | {plan['price']}</code>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup([_back('suba:plans')])
    )


async def handle_plan_edit_text(update, context):
    plan_id = context.user_data.pop('suba_plan_edit_id', None)
    context.user_data.pop('mode', None)
    text = update.message.text.strip()
    if not plan_id:
        return
    try:
        name, days_s, price_s = [p.strip() for p in text.split('|')]
        days, price = int(days_s), int(price_s)
        await db.sub_plan_update(plan_id, {'name': name, 'days': days, 'price': price})
        await update.message.reply_text(f"✅ پلن به‌روزرسانی شد: «{name}» ({days} روز، {_fmt_price(price)})")
    except Exception:
        await update.message.reply_text(
            "❌ فرمت اشتباه بود.\nمثال درست: <code>یک ماهه | 30 | 100000</code>", parse_mode='HTML'
        )


async def _prompt_plan_add(query, context):
    context.user_data['mode'] = 'suba_plan_add'
    await query.edit_message_text(
        "➕ <b>پلن جدید</b>\n\nبه این فرم بفرست:\n<code>نام | تعداد روز | قیمت (تومان)</code>\n\n"
        "مثال:\n<code>یک ماهه | 30 | 100000</code>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup([_back('suba:plans')])
    )


async def handle_plan_add_text(update, context):
    text = update.message.text.strip()
    context.user_data.pop('mode', None)
    try:
        name, days_s, price_s = [p.strip() for p in text.split('|')]
        days, price = int(days_s), int(price_s)
        await db.sub_plan_add(name, days, price)
        await update.message.reply_text(f"✅ پلن «{name}» ({days} روز، {_fmt_price(price)}) اضافه شد.")
    except Exception:
        await update.message.reply_text(
            "❌ فرمت اشتباه بود.\nدوباره از «📋 پلن‌ها → ➕ پلن جدید» امتحان کن.\n"
            "مثال درست: <code>یک ماهه | 30 | 100000</code>", parse_mode='HTML'
        )


# ══════════════════════════════════════════════════
#  شماره کارت
# ══════════════════════════════════════════════════

async def _show_card(query):
    num   = await db.get_setting('subscription_card_number', '—')
    owner = await db.get_setting('subscription_card_owner', '—')
    text = (
        f"💳 <b>اطلاعات کارت</b>\n━━━━━━━━━━━━━━━━\n"
        f"شماره: <code>{num}</code>\nصاحب حساب: {owner}"
    )
    keyboard = [
        [InlineKeyboardButton("✏️ ویرایش", callback_data='suba:card_edit')],
        _back(),
    ]
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _prompt_card_edit(query, context):
    context.user_data['mode'] = 'suba_card'
    await query.edit_message_text(
        "✏️ به این فرم بفرست:\n<code>شماره کارت | نام صاحب حساب</code>\n\n"
        "مثال:\n<code>6037-xxxx-xxxx-xxxx | امیرحسین ...</code>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup([_back('suba:card')])
    )


async def handle_card_text(update, context):
    text = update.message.text.strip()
    context.user_data.pop('mode', None)
    try:
        num, owner = [p.strip() for p in text.split('|', 1)]
        await db.set_setting('subscription_card_number', num)
        await db.set_setting('subscription_card_owner', owner)
        await update.message.reply_text("✅ اطلاعات کارت به‌روزرسانی شد.")
    except Exception:
        await update.message.reply_text("❌ فرمت اشتباه بود. مثال: <code>شماره | نام</code>", parse_mode='HTML')


# ══════════════════════════════════════════════════
#  صف در انتظار
# ══════════════════════════════════════════════════

async def _show_pending(query):
    pending = await db.sub_payment_list_pending()
    if not pending:
        text = "📥 <b>صف در انتظار</b>\n\n✅ چیزی در صف نیست."
        keyboard = [_back()]
    else:
        lines = ["📥 <b>صف در انتظار</b>\n━━━━━━━━━━━━━━━━"]
        keyboard = []
        for p in pending[:15]:
            user = await db.get_user(p['user_id'])
            name = user.get('name', str(p['user_id'])) if user else str(p['user_id'])
            lines.append(f"• {name} — {p['plan_name']} — {_fmt_price(p['final_price'])}")
            keyboard.append([
                InlineKeyboardButton(f"👁 {name[:20]}", callback_data=f"suba:view_pay:{p['_id']}")
            ])
        keyboard.append(_back())
        text = "\n".join(lines)
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _resend_payment_for_review(query, context, pid):
    """اگه پیام اصلی رسید گم/اسکرول شده، دوباره با دکمه تأیید/رد برای ادمین می‌فرسته"""
    p = await db.sub_payment_get(pid)
    if not p:
        await query.answer("❌ پیدا نشد.", show_alert=True)
        return
    user = await db.get_user(p['user_id'])
    name = user.get('name', str(p['user_id'])) if user else str(p['user_id'])
    reject_count = await db.sub_payment_reject_count(p['user_id'])
    warn_line = f"\n⚠️ این کاربر قبلاً {reject_count} بار رد شده" if reject_count > 0 else ""
    caption = (
        f"💳 <b>رسید پرداخت</b>\n\n👤 {name}\n🆔 <code>{p['user_id']}</code>\n"
        f"📦 {p['plan_name']} | 💰 {_fmt_price(p['final_price'])}{warn_line}"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأیید", callback_data=f"sub:appr:{pid}"),
        InlineKeyboardButton("❌ رد", callback_data=f"sub:rej:{pid}"),
    ]])
    await query.message.reply_photo(p['screenshot_file_id'], caption=caption, parse_mode='HTML', reply_markup=kb)


# ══════════════════════════════════════════════════
#  📋 لیست کامل مشترکین فعال (قابل مرور، نه فقط جستجو)
# ══════════════════════════════════════════════════

_SUBSCRIBERS_PAGE_SIZE = 10


async def _show_subscribers_list(query, page: int):
    from utils import fmt_jalali_dt
    total = await db.sub_count_by_status('active')
    items = await db.sub_list_by_status('active', skip=page * _SUBSCRIBERS_PAGE_SIZE, limit=_SUBSCRIBERS_PAGE_SIZE)

    lines = [f"📋 <b>مشترکین فعال</b> ({total} نفر)\n━━━━━━━━━━━━━━━━"]
    keyboard = []
    if not items:
        lines.append("فعلاً هیچ مشترک فعالی نیست.")
    for s in items:
        uid = s['_id']
        user = await db.get_user(uid)
        name = user.get('name', str(uid)) if user else str(uid)
        days_left = await db.sub_days_left(uid)
        soon = "🔴" if days_left <= 3 else "✅"
        lines.append(f"{soon} {name} — {s.get('plan_name','-')} — {days_left} روز مانده (تا {fmt_jalali_dt(s.get('end_date',''), with_time=False)})")
        keyboard.append([InlineKeyboardButton(f"👤 {name[:25]}", callback_data=f"suba:user:{uid}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ قبلی", callback_data=f'suba:subscribers:{page-1}'))
    if (page + 1) * _SUBSCRIBERS_PAGE_SIZE < total:
        nav_row.append(InlineKeyboardButton("بعدی ▶️", callback_data=f'suba:subscribers:{page+1}'))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔍 جستجو در مشترکین", callback_data='suba:user_search')])
    keyboard.append(_back())
    await query.edit_message_text("\n".join(lines), parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════════
#  مدیریت دستی اشتراک کاربر
# ══════════════════════════════════════════════════

async def _prompt_user_search(query, context):
    context.user_data['mode'] = 'suba_user_search'
    await query.edit_message_text(
        "🔍 آیدی عددی، یوزرنیم یا نام دانشجو رو بفرست:",
        reply_markup=InlineKeyboardMarkup([_back()])
    )


async def handle_user_search_text(update, context):
    context.user_data.pop('mode', None)
    text = update.message.text.strip()
    results = await db.search_users(text)
    if not results:
        await update.message.reply_text("❌ کاربری پیدا نشد.")
        return
    keyboard = []
    for u in results[:10]:
        keyboard.append([InlineKeyboardButton(
            f"👤 {u.get('name','?')} (@{u.get('username','-')})",
            callback_data=f"suba:user:{u['user_id']}"
        )])
    keyboard.append(_back())
    await update.message.reply_text(
        f"🔍 {len(results)} نتیجه:", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_user_detail(query, target_uid: int):
    user = await db.get_user(target_uid)
    name = user.get('name', str(target_uid)) if user else str(target_uid)
    s = await db.sub_get(target_uid)
    if s and s.get('status') == 'active' and await db.sub_is_active(target_uid):
        from utils import progress_bar
        days = await db.sub_days_left(target_uid)
        total = max(1, s.get('last_plan_days', days) or 1)
        pct = min(100, round(days / total * 100))
        status_txt = f"✅ فعال — {days} روز مانده ({s.get('plan_name','-')})\n<code>[{progress_bar(pct)}]</code> {pct}٪"
    elif s and s.get('status') == 'revoked':
        status_txt = f"🚫 لغوشده — دلیل: {s.get('revoke_reason','-')}"
    elif s and s.get('status') == 'expired':
        status_txt = "⌛ منقضی‌شده"
    else:
        status_txt = "⚠️ بدون اشتراک"

    reject_count = await db.sub_payment_reject_count(target_uid)
    reject_line = f"\n⚠️ {reject_count} بار رد شده" if reject_count > 0 else ""

    text = f"👤 <b>{name}</b>\n🆔 <code>{target_uid}</code>\n\n💳 وضعیت: {status_txt}{reject_line}"
    keyboard = [
        [
            InlineKeyboardButton("+7", callback_data=f"suba:manual_quick:{target_uid}:7"),
            InlineKeyboardButton("+30", callback_data=f"suba:manual_quick:{target_uid}:30"),
            InlineKeyboardButton("+90", callback_data=f"suba:manual_quick:{target_uid}:90"),
        ],
        [InlineKeyboardButton("✍️ تعداد دلخواه", callback_data=f"suba:manual_activate:{target_uid}")],
        [InlineKeyboardButton("🧾 تاریخچه‌ی این کاربر", callback_data=f"suba:user_history:{target_uid}")],
    ]
    if s and s.get('status') == 'active':
        keyboard.append([InlineKeyboardButton("🚫 لغو اشتراک (با دلیل)", callback_data=f"suba:revoke:{target_uid}")])
    keyboard.append(_back())
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _quick_activate(query, context, target_uid: int, days: int):
    await db.sub_activate(target_uid, days, plan_name=f'فعال‌سازی دستی (+{days} روز)',
                           source='admin_manual', granted_by=query.from_user.id, extend=True)
    days_left = await db.sub_days_left(target_uid)
    await safe_send(
        context.bot, target_uid,
        f"✅ <b>اشتراکت توسط ادمین فعال شد!</b>\n\n⏳ {days_left} روز اعتبار داری.\n"
        f"از بخش «👤 پروفایل» می‌تونی چک کنی.", parse_mode='HTML'
    )
    await query.answer(f"✅ {days} روز فعال شد.", show_alert=True)
    await send_audit_log(
        context.bot, 'admin', 'ادمین ارشد', query.from_user.id,
        f"فعال‌سازی دستی سریع (+{days} روز)", module='Subscription', severity='INFO',
        target_id=str(target_uid), target_type='user', tags=['اشتراک_دستی']
    )
    await _show_user_detail(query, target_uid)


async def _show_user_payment_history(query, target_uid: int):
    from utils import fmt_jalali_dt
    history = await db.sub_payment_history(target_uid)
    icons = {'pending': '⏳', 'approved': '✅', 'rejected': '❌'}
    lines = [f"🧾 <b>تاریخچه‌ی پرداخت کاربر {target_uid}</b>\n━━━━━━━━━━━━━━━━"]
    if not history:
        lines.append("هیچ رسیدی ثبت نکرده.")
    for p in history[:15]:
        icon = icons.get(p['status'], '•')
        date = fmt_jalali_dt(p.get('submitted_at', ''))
        lines.append(f"{icon} {p['plan_name']} — {_fmt_price(p['final_price'])} — {date}")
    await query.edit_message_text(
        "\n".join(lines), parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([_back(f'suba:user:{target_uid}')])
    )


async def _prompt_manual_days(query, context, target_uid):
    context.user_data['mode'] = 'suba_manual_days'
    context.user_data['suba_target_uid'] = target_uid
    await query.edit_message_text(
        "➕ تعداد روز اشتراک رو بفرست (فقط عدد، مثلاً 30):",
        reply_markup=InlineKeyboardMarkup([_back(f'suba:user:{target_uid}')])
    )


async def handle_manual_days_text(update, context):
    target_uid = context.user_data.pop('suba_target_uid', None)
    context.user_data.pop('mode', None)
    text = update.message.text.strip()
    if not target_uid or not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("❌ فقط یه عدد مثبت بفرست.")
        return
    days = int(text)
    await db.sub_activate(target_uid, days, plan_name='فعال‌سازی دستی',
                           source='admin_manual', granted_by=update.effective_user.id, extend=True)
    days_left = await db.sub_days_left(target_uid)
    await safe_send(
        context.bot, target_uid,
        f"✅ <b>اشتراکت توسط ادمین فعال شد!</b>\n\n⏳ {days_left} روز اعتبار داری.\n"
        f"از بخش «👤 پروفایل» می‌تونی چک کنی.", parse_mode='HTML'
    )
    await update.message.reply_text(f"✅ {days} روز برای کاربر {target_uid} فعال شد.")
    await send_audit_log(
        context.bot, 'admin', 'ادمین ارشد', update.effective_user.id,
        "فعال‌سازی دستی اشتراک", module='Subscription', severity='INFO',
        target_id=str(target_uid), target_type='user', tags=['اشتراک_دستی']
    )


async def _prompt_revoke_reason(query, context, target_uid):
    context.user_data['mode'] = 'suba_revoke_reason'
    context.user_data['suba_target_uid'] = target_uid
    await query.edit_message_text(
        "🚫 دلیل لغو اشتراک رو بنویس (برای دانشجو ارسال می‌شه):",
        reply_markup=InlineKeyboardMarkup([_back(f'suba:user:{target_uid}')])
    )


async def handle_revoke_reason_text(update, context):
    target_uid = context.user_data.pop('suba_target_uid', None)
    context.user_data.pop('mode', None)
    reason = update.message.text.strip()
    if not target_uid:
        return
    ok = await db.sub_revoke(target_uid, reason, update.effective_user.id)
    if ok:
        await safe_send(
            context.bot, target_uid,
            f"🚫 <b>اشتراکت لغو شد</b>\n\n📝 دلیل: {reason}", parse_mode='HTML'
        )
        await update.message.reply_text("✅ لغو شد و به کاربر اطلاع داده شد.")
        await send_audit_log(
            context.bot, 'admin', 'ادمین ارشد', update.effective_user.id,
            "لغو اشتراک", module='Subscription', severity='HIGH',
            target_id=str(target_uid), target_type='user',
            target_label=reason, tags=['لغو_اشتراک']
        )
    else:
        await update.message.reply_text("❌ این کاربر اصلاً اشتراکی نداشت.")


# ══════════════════════════════════════════════════
#  کدهای تخفیف
# ══════════════════════════════════════════════════

async def _show_discounts(query):
    from utils import fmt_jalali_dt
    codes = await db.discount_list()
    lines = ["🎟 <b>کدهای تخفیف</b>\n━━━━━━━━━━━━━━━━"]
    keyboard = []
    if not codes:
        lines.append("هنوز کدی ساخته نشده.")
    for c in codes[:20]:
        mark = "✅" if c.get('active') else "⛔️"
        used = f"{c.get('used_count',0)}/{c['max_uses'] if c.get('max_uses') else '∞'}"
        exp  = f" — تا {fmt_jalali_dt(c['expires_at'], with_time=False)}" if c.get('expires_at') else ""
        lines.append(f"{mark} <code>{c['code']}</code> — {c['percent']}٪ — استفاده: {used}{exp}")
        keyboard.append([
            InlineKeyboardButton(f"{'⛔️' if c.get('active') else '✅'} {c['code']}",
                                  callback_data=f"suba:disc_toggle:{c['code']}"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"suba:disc_del:{c['code']}"),
        ])
    keyboard.append([InlineKeyboardButton("➕ کد جدید", callback_data='suba:disc_add')])
    keyboard.append(_back())
    await query.edit_message_text("\n".join(lines), parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _prompt_discount_add(query, context):
    context.user_data['mode'] = 'suba_discount_add'
    await query.edit_message_text(
        "➕ <b>کد تخفیف جدید</b>\n\nفرم:\n"
        "<code>کد | درصد | سقف‌استفاده(0=نامحدود) | روز‌اعتبار(0=همیشگی)</code>\n\n"
        "مثال:\n<code>NOWRUZ20 | 20 | 0 | 30</code>\n(یعنی ۲۰٪ تخفیف، بی‌سقف استفاده، تا ۳۰ روز دیگه معتبر)\n\n"
        "برای کد ۱۰۰٪ رایگان، درصد رو 100 بذار.",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup([_back('suba:discounts')])
    )


async def handle_discount_add_text(update, context):
    from datetime import datetime, timedelta
    text = update.message.text.strip()
    context.user_data.pop('mode', None)
    try:
        parts = [p.strip() for p in text.split('|')]
        code, percent = parts[0], int(parts[1])
        max_uses = int(parts[2]) if len(parts) > 2 else 0
        exp_days = int(parts[3]) if len(parts) > 3 else 0
        expires_at = (datetime.now() + timedelta(days=exp_days)).isoformat() if exp_days > 0 else None
        ok = await db.discount_add(code, percent, max_uses, expires_at, update.effective_user.id)
        if ok:
            await update.message.reply_text(f"✅ کد <code>{code.upper()}</code> ساخته شد.", parse_mode='HTML')
        else:
            await update.message.reply_text("❌ این کد از قبل وجود داره.")
    except Exception:
        await update.message.reply_text(
            "❌ فرمت اشتباه بود.\nمثال: <code>NOWRUZ20 | 20 | 0 | 30</code>", parse_mode='HTML'
        )


# ══════════════════════════════════════════════════
#  اعطای رایگان دسته‌جمعی
# ══════════════════════════════════════════════════

async def _show_grant_menu(query):
    keyboard = [
        [InlineKeyboardButton("🎓 مدیر محتوا (کلی — از پروفایل کاربران)", callback_data='suba:grant_role:content_admin')],
    ]
    for role, label in db.ROLE_LABELS.items():
        if role == 'content_admin':
            continue  # از قبل بالا اضافه شد (منبع داده‌ش فرق داره: users.role نه admin_roles)
        keyboard.append([InlineKeyboardButton(label, callback_data=f'suba:grant_role:{role}')])
    keyboard.append([InlineKeyboardButton("📋 لیست آیدی دلخواه (چندتایی)", callback_data='suba:grant_list')])
    keyboard.append([InlineKeyboardButton("👤 دستی با آیدی/یوزرنیم (تک‌نفره)", callback_data='suba:user_search')])
    keyboard.append(_back())
    await query.edit_message_text(
        "🎁 <b>اعطای اشتراک رایگان دسته‌جمعی</b>\n\n"
        "یه نقش انتخاب کن، یا برای گروه دلخواه (مثلاً نماینده‌های چند دانشگاه)\n"
        "از «📋 لیست آیدی دلخواه» استفاده کن:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _prompt_grant_list(query, context):
    context.user_data['mode'] = 'suba_grant_list_ids'
    await query.edit_message_text(
        "📋 <b>لیست دانشجویان</b>\n\n"
        "هر نفر رو توی یه خط جدا بفرست — هرکدوم از این سه حالت می‌تونه باشه:\n"
        "• آیدی عددی تلگرام\n"
        "• یوزرنیم (با یا بدون @)\n"
        "• اسم دقیق ثبت‌شده توی ربات\n\n"
        "مثال:\n<code>123456789\n@ali_r\nسارا محمدی</code>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup([_back('suba:grant')])
    )


async def handle_grant_list_ids_text(update, context):
    """
    FIX مهم: قبلاً فقط آیدی عددی قبول می‌کرد و هر چیز دیگه (یوزرنیم،
    اسم) رو بی‌صدا نادیده می‌گرفت — حتی با split روی فاصله که اسم‌های
    چندکلمه‌ای رو هم خراب می‌کرد. حالا هر خط می‌تواند آیدی عددی،
    یوزرنیم (با/بدون @)، یا اسم ثبت‌شده در ربات باشد؛ هر خط جدا پردازش
    و به کاربر واقعی متصل می‌شود.
    """
    context.user_data.pop('mode', None)
    raw = update.message.text.strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not lines:
        await update.message.reply_text("❌ چیزی وارد نشد.")
        return

    resolved, not_found, ambiguous = [], [], []
    for line in lines:
        if line.lstrip('+-').isdigit():
            resolved.append((int(line), line))
            continue
        matches = await db.search_users(line)
        if len(matches) == 1:
            resolved.append((matches[0]['user_id'], matches[0].get('name', line)))
        elif len(matches) == 0:
            not_found.append(line)
        else:
            ambiguous.append(line)

    if not resolved:
        await update.message.reply_text(
            "❌ هیچ‌کدوم پیدا نشدن. هر خط می‌تونه آیدی عددی، یوزرنیم (با یا بدون @)، "
            "یا اسم دقیق ثبت‌شده توی ربات باشه."
        )
        return

    ids = [uid for uid, _ in resolved]
    context.user_data['suba_grant_list'] = ids
    context.user_data['mode'] = 'suba_grant_list_days'

    lines_out = [f"✅ {len(resolved)} نفر پیدا شد:"]
    lines_out += [f"   • {name}" for _, name in resolved[:15]]
    if len(resolved) > 15:
        lines_out.append(f"   … و {len(resolved)-15} نفر دیگر")
    if ambiguous:
        lines_out.append(f"\n⚠️ {len(ambiguous)} مورد چند نتیجه داشت (نادیده گرفته شد): " + "، ".join(ambiguous[:5]))
    if not_found:
        lines_out.append(f"\n❌ {len(not_found)} مورد پیدا نشد: " + "، ".join(not_found[:5]))
    lines_out.append("\nحالا چند روز اشتراک رایگان بدیم؟ (فقط عدد)")
    await update.message.reply_text("\n".join(lines_out))


async def handle_grant_list_days_text(update, context):
    ids = context.user_data.pop('suba_grant_list', [])
    context.user_data.pop('mode', None)
    text = update.message.text.strip()
    if not ids or not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("❌ فقط یه عدد مثبت بفرست.")
        return
    days = int(text)
    count = 0
    for uid in ids:
        user = await db.get_user(uid)
        if not user:
            continue
        await db.sub_activate(uid, days, plan_name='🎁 اشتراک رایگان',
                               source='free_grant', granted_by=update.effective_user.id, extend=True)
        days_left = await db.sub_days_left(uid)
        await safe_send(
            context.bot, uid,
            f"🎁 <b>یه اشتراک رایگان بهت هدیه داده شد!</b>\n\n"
            f"⏳ {days_left} روز اعتبار داری.\nاز بخش «👤 پروفایل» می‌تونی چک کنی.",
            parse_mode='HTML'
        )
        count += 1
    skipped = len(ids) - count
    msg = f"✅ اشتراک رایگان {days} روزه به {count} نفر فعال شد."
    if skipped:
        msg += f"\n⚠️ {skipped} آیدی در دیتابیس پیدا نشد (احتمالاً هنوز /start نزده)."
    await update.message.reply_text(msg)
    await send_audit_log(
        context.bot, 'admin', 'ادمین ارشد', update.effective_user.id,
        "اعطای رایگان دسته‌جمعی (لیست دستی)", module='Subscription', severity='INFO',
        target_label=f"{count} نفر — {days} روز", tags=['اشتراک_رایگان']
    )


async def _prompt_grant_days(query, context, role: str):
    context.user_data['mode'] = 'suba_grant_days'
    context.user_data['suba_grant_role'] = role
    label = 'مدیر محتوا (کلی)' if role == 'content_admin' else db.ROLE_LABELS.get(role, role)
    await query.edit_message_text(
        f"🎁 اعطا به «{label}»\n\nچند روز اشتراک رایگان بدیم؟ (فقط عدد)",
        reply_markup=InlineKeyboardMarkup([_back('suba:grant')])
    )


async def handle_grant_days_text(update, context):
    role = context.user_data.pop('suba_grant_role', None)
    context.user_data.pop('mode', None)
    text = update.message.text.strip()
    if not role or not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("❌ فقط یه عدد مثبت بفرست.")
        return
    days = int(text)

    if role == 'content_admin':
        target_uids = [u['user_id'] async for u in db.users.find({'role': 'content_admin'})]
    else:
        role_docs = await db.get_all_admin_roles()
        target_uids = [r['_id'] for r in role_docs if r.get('role') == role]

    if not target_uids:
        await update.message.reply_text("⚠️ هیچ کاربری با این نقش پیدا نشد.")
        return

    count = 0
    for uid in target_uids:
        await db.sub_activate(uid, days, plan_name='🎁 اشتراک رایگان',
                               source='free_grant', granted_by=update.effective_user.id, extend=True)
        days_left = await db.sub_days_left(uid)
        await safe_send(
            context.bot, uid,
            f"🎁 <b>یه اشتراک رایگان بهت هدیه داده شد!</b>\n\n"
            f"⏳ {days_left} روز اعتبار داری.\nاز بخش «👤 پروفایل» می‌تونی چک کنی.",
            parse_mode='HTML'
        )
        count += 1

    await update.message.reply_text(f"✅ اشتراک رایگان {days} روزه به {count} نفر فعال شد.")
    await send_audit_log(
        context.bot, 'admin', 'ادمین ارشد', update.effective_user.id,
        "اعطای رایگان دسته‌جمعی", module='Subscription', severity='INFO',
        target_label=f"{role} × {count} نفر — {days} روز", tags=['اشتراک_رایگان']
    )


# ══════════════════════════════════════════════════
#  callback اصلی
# ══════════════════════════════════════════════════

async def subscription_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = update.effective_user.id
    if uid != ADMIN_ID:
        await query.answer("❌ این بخش فقط در اختیار مدیر ارشد است.", show_alert=True)
        return
    await query.answer()
    parts  = query.data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    if action == 'main':
        await _show_main(query)

    elif action == 'toggle_enforce':
        cur = await db.get_setting('subscription_enforced', False)
        await db.set_setting('subscription_enforced', not cur)
        await send_audit_log(
            context.bot, 'admin', 'ادمین ارشد', uid,
            f"{'فعال‌سازی' if not cur else 'خاموش‌کردن'} اجباری اشتراک",
            module='Subscription', severity='HIGH', tags=['اشتراک_اجباری']
        )
        await _show_main(query)

    elif action == 'toggle_protect':
        cur = await db.get_setting('protect_content_enabled', True)
        await db.set_setting('protect_content_enabled', not cur)
        await send_audit_log(
            context.bot, 'admin', 'ادمین ارشد', uid,
            f"{'روشن‌کردن' if not cur else 'خاموش‌کردن'} محافظت کپی‌رایت فایل‌ها",
            module='Subscription', severity='INFO', tags=['محافظت_فایل']
        )
        await _show_main(query)

    elif action == 'plans':
        await _show_plans(query)
    elif action == 'plan_add':
        await _prompt_plan_add(query, context)
    elif action == 'plan_edit':
        await _prompt_plan_edit(query, context, parts[2])
    elif action == 'plan_toggle':
        await db.sub_plan_toggle(parts[2])
        await _show_plans(query)
    elif action == 'plan_del':
        await db.sub_plan_delete(parts[2])
        await _show_plans(query)

    elif action == 'card':
        await _show_card(query)
    elif action == 'card_edit':
        await _prompt_card_edit(query, context)

    elif action == 'pending':
        await _show_pending(query)
    elif action == 'view_pay':
        await _resend_payment_for_review(query, context, parts[2])
    elif action == 'history':
        await _show_history(query, parts[2], int(parts[3]))
    elif action == 'subscribers':
        await _show_subscribers_list(query, int(parts[2]))

    elif action == 'user_search':
        await _prompt_user_search(query, context)
    elif action == 'user':
        await _show_user_detail(query, int(parts[2]))
    elif action == 'user_history':
        await _show_user_payment_history(query, int(parts[2]))
    elif action == 'manual_activate':
        await _prompt_manual_days(query, context, int(parts[2]))
    elif action == 'manual_quick':
        await _quick_activate(query, context, int(parts[2]), int(parts[3]))
    elif action == 'revoke':
        await _prompt_revoke_reason(query, context, int(parts[2]))

    elif action == 'discounts':
        await _show_discounts(query)
    elif action == 'disc_add':
        await _prompt_discount_add(query, context)
    elif action == 'disc_toggle':
        await db.discount_toggle(parts[2])
        await _show_discounts(query)
    elif action == 'disc_del':
        await db.discount_delete(parts[2])
        await _show_discounts(query)

    elif action == 'grant':
        await _show_grant_menu(query)
    elif action == 'grant_role':
        await _prompt_grant_days(query, context, parts[2])
    elif action == 'grant_list':
        await _prompt_grant_list(query, context)


# ══════════════════════════════════════════════════
#  دیسپچر متن — همه‌ی حالت‌های suba_* از اینجا رد می‌شوند
# ══════════════════════════════════════════════════

TEXT_MODE_HANDLERS = {
    'suba_plan_add':        handle_plan_add_text,
    'suba_plan_edit':       handle_plan_edit_text,
    'suba_card':             handle_card_text,
    'suba_user_search':      handle_user_search_text,
    'suba_manual_days':      handle_manual_days_text,
    'suba_revoke_reason':    handle_revoke_reason_text,
    'suba_discount_add':     handle_discount_add_text,
    'suba_grant_days':       handle_grant_days_text,
    'suba_grant_list_ids':   handle_grant_list_ids_text,
    'suba_grant_list_days':  handle_grant_list_days_text,
}


async def subscription_admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get('mode', '')
    handler = TEXT_MODE_HANDLERS.get(mode)
    if handler:
        await handler(update, context)

"""
💳 سیستم اشتراک — بخش دانشجو + بررسی رسید توسط ادمین
  ✅ چند پلن هم‌زمان (روز/قیمت مستقل)
  ✅ کد تخفیف درصدی
  ✅ فقط عکس اسکرین‌شات — بدون فایل/متن
  ✅ بررسی فقط توسط ADMIN_ID
  ✅ غیرفعال به‌صورت پیش‌فرض — کلید اجباری‌سازی در پنل ادمین
"""
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from utils import ADMIN_ID as _ADMIN_ID_FALLBACK, safe_send

logger = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0')) or _ADMIN_ID_FALLBACK


def _fmt_price(p: int) -> str:
    return f"{p:,}".replace(',', '٬') + " تومان"


# ══════════════════════════════════════════════════
#  گیت دسترسی — نقطه‌ی واحدی که بخش منابع/بانک‌سوال صداش می‌زنن
# ══════════════════════════════════════════════════

async def has_access(uid: int) -> bool:
    """آیا این کاربر اجازه‌ی دسترسی به منابع/بانک‌سوال را دارد؟"""
    enforced = await db.get_setting('subscription_enforced', False)
    if not enforced:
        return True
    if uid == ADMIN_ID:
        return True
    return await db.sub_is_active(uid)


async def check_and_show_paywall(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int) -> bool:
    """
    اگر دسترسی داشت True برمی‌گرداند (ادامه‌ی مسیر عادی).
    اگر نداشت، خودش صفحه‌ی قفل را نشان می‌دهد و False برمی‌گرداند —
    فراخوان فقط کافیست چک کند و در صورت False چیز دیگری نفرستد.
    """
    if await has_access(uid):
        return True
    await show_paywall(update.message, uid)
    return False


# ══════════════════════════════════════════════════
#  صفحه‌ی قفل / انتخاب پلن
# ══════════════════════════════════════════════════

async def show_paywall(target, uid: int, edit: bool = False):
    plans = await db.sub_plan_list(only_active=True)
    discount = None
    if hasattr(target, 'get'):  # نباید پیش بیاد، فقط ایمنی
        pass

    header = (
        "🔒 <b>این بخش مخصوص دانشجوهای مشترک است</b>\n\n"
        "برای دسترسی به منابع درسی و بانک سوال، یکی از پلن‌های زیر رو انتخاب کن:\n"
        "━━━━━━━━━━━━━━━━\n"
    )
    if not plans:
        text = header + "⚠️ فعلاً هیچ پلنی تعریف نشده. با ادمین در تماس باش."
        kb = InlineKeyboardMarkup([])
    else:
        keyboard = []
        for p in plans:
            price_txt = _fmt_price(p['price'])
            keyboard.append([InlineKeyboardButton(
                f"💳 {p['name']} — {p['days']} روزه — {price_txt}",
                callback_data=f"sub:plan:{p['_id']}"
            )])
        keyboard.append([InlineKeyboardButton("🎟 کد تخفیف دارم", callback_data='sub:discount')])
        text = header + "هر پلن رو بزن تا جزئیات پرداخت رو ببینی 👇"
        kb = InlineKeyboardMarkup(keyboard)

    if edit:
        await target.edit_text(text, parse_mode='HTML', reply_markup=kb)
    else:
        await target.reply_text(text, parse_mode='HTML', reply_markup=kb)


async def _show_plan_detail(query, context, plan_id: str, uid: int):
    plan = await db.sub_plan_get(plan_id)
    if not plan or not plan.get('active'):
        await query.answer("❌ این پلن دیگه در دسترس نیست.", show_alert=True)
        return

    price = plan['price']
    discount_code = context.user_data.get('sub_discount_code')
    final_price = price
    if discount_code:
        v = await db.discount_validate(discount_code)
        if not v['ok']:
            context.user_data.pop('sub_discount_code', None)
            discount_code = None
        else:
            final_price = round(price * (100 - v['percent']) / 100)

    context.user_data['sub_plan_id']    = str(plan['_id'])
    context.user_data['sub_final_price'] = final_price
    context.user_data.pop('sub_mode', None)  # هنوز منتظر عکس نیستیم — اول باید قوانین تأیید بشه

    await _show_rules(query, plan_id)


# ══════════════════════════════════════════════════
#  ✅ قوانین و تعهدنامه — مرحله‌ی اجباری قبل از دیدن شماره کارت
# ══════════════════════════════════════════════════

RULES_TEXT = (
    "📜 <b>قبل از پرداخت، این قوانین رو حتماً بخون</b>\n"
    "━━━━━━━━━━━━━━━━\n\n"
    "1️⃣ فایل‌های منابع و بانک سوال فقط برای استفاده‌ی <b>شخصی خودت</b>ه.\n"
    "فوروارد کردن، اشتراک‌گذاری یا ارسال به هر شخص دیگه (حتی همکلاسی) "
    "به هر شکلی (تلگرام، گروه، فضای مجازی) <b>ممنوعه</b>.\n\n"
    "2️⃣ اگه به هر دلیلی بخشی از محتوا رو جای دیگه استفاده کردی، "
    "<b>ذکر منبع (هامزیار)</b> الزامیه.\n\n"
    "3️⃣ 🚫 <b>هرگونه نقض این قوانین (فوروارد/کپی/انتشار بدون منبع) "
    "= بن دائم و خودکار از ربات + لغو فوری اشتراک، بدون بازگشت وجه.</b>\n"
    "هیچ عذر یا استثنایی («فقط برای یه نفر فرستادم»، «نمی‌دونستم» و امثالش) "
    "پذیرفته نیست.\n\n"
    "4️⃣ قبل از ارسال رسید، مطمئن شو مبلغ درست و کامل واریز شده — "
    "رسید با مبلغ اشتباه رد می‌شه.\n\n"
    "5️⃣ لغو اشتراک به‌خاطر نقض قوانین، غیرقابل اعتراضه.\n\n"
    "━━━━━━━━━━━━━━━━\n"
    "با زدن دکمه‌ی زیر، یعنی این قوانین رو خوندی و قبول داری ✅"
)


async def _show_rules(query, plan_id: str):
    keyboard = [
        [InlineKeyboardButton("✅ خوندم و قبول دارم، برو مرحله‌ی بعد", callback_data=f'sub:agree:{plan_id}')],
        [InlineKeyboardButton("🔙 بازگشت به پلن‌ها", callback_data='sub:back')],
    ]
    await query.edit_message_text(RULES_TEXT, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_payment_details(query, context, plan_id: str):
    plan = await db.sub_plan_get(plan_id)
    if not plan or not plan.get('active'):
        await query.answer("❌ این پلن دیگه در دسترس نیست.", show_alert=True)
        return

    price = plan['price']
    discount_code = context.user_data.get('sub_discount_code')
    final_price = context.user_data.get('sub_final_price', price)

    # FIX جدید: کد تخفیف ۱۰۰٪ = رایگان کامل — نیازی به رسید/اسکرین‌شات
    # نیست، همون لحظه فعال می‌شه (منطقاً چیزی برای پرداخت نمانده که
    # عکسش گرفته شود).
    if final_price <= 0:
        await _activate_free_via_discount(query, context, plan, discount_code)
        return

    discount_line = ''
    if discount_code:
        discount_line = f"🎟 کد <code>{discount_code}</code> اعمال شد\n"

    card_num   = await db.get_setting('subscription_card_number', '—')
    card_owner = await db.get_setting('subscription_card_owner', '—')

    price_line = (f"<s>{_fmt_price(price)}</s> ➜ <b>{_fmt_price(final_price)}</b>"
                  if discount_code else f"<b>{_fmt_price(price)}</b>")

    text = (
        f"💳 <b>{plan['name']}</b> — {plan['days']} روزه\n\n"
        f"{discount_line}"
        f"💰 مبلغ: {price_line}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📇 شماره کارت:\n<code>{card_num}</code>\n"
        f"👤 به نام: {card_owner}\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"بعد از واریز، <b>فقط عکس رسید/اسکرین‌شات</b> رو همینجا بفرست.\n"
        f"بعد از تأیید ادمین، اشتراکت فوراً فعال می‌شه ✅\n\n"
        f"<i>یادت باشه: قوانین ذکرشده در مرحله‌ی قبل رو قبول کردی 📜</i>"
    )
    keyboard = [
        [InlineKeyboardButton("🔙 بازگشت به پلن‌ها", callback_data='sub:back')],
    ]
    context.user_data['sub_mode'] = 'awaiting_screenshot'
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _activate_free_via_discount(query, context, plan: dict, discount_code: str):
    """FIX جدید: مسیر کد تخفیف ۱۰۰٪ — بدون رسید، بدون بررسی ادمین، فعال‌سازی آنی"""
    uid = query.from_user.id
    for k in ('sub_mode', 'sub_plan_id', 'sub_final_price', 'sub_discount_code'):
        context.user_data.pop(k, None)

    await db.sub_activate(uid, plan['days'], plan['name'], source='payment',
                           granted_by=0, extend=True)
    if discount_code:
        await db.discount_consume(discount_code)
        # ثبت به‌عنوان یک تراکنش approved با مبلغ صفر — برای آمار و تاریخچه
        pid = await db.sub_payment_create(
            user_id=uid, plan_id=str(plan['_id']), plan_name=plan['name'],
            price=plan['price'], final_price=0, screenshot_file_id='',
            discount_code=discount_code,
        )
        await db.sub_payment_decide(pid, approved=True, admin_id=0, note='کد تخفیف ۱۰۰٪ — خودکار')

    days_left = await db.sub_days_left(uid)
    text = (
        f"🎉 <b>اشتراکت با کد تخفیف رایگان فعال شد!</b>\n\n"
        f"📦 پلن: {plan['name']}\n"
        f"⏳ {days_left} روز اعتبار داری\n\n"
        f"از بخش «👤 پروفایل» هر وقت خواستی می‌تونی باقیمونده رو چک کنی."
    )
    await query.edit_message_text(text, parse_mode='HTML')


# ══════════════════════════════════════════════════
#  کد تخفیف
# ══════════════════════════════════════════════════

async def _prompt_discount(query, context):
    context.user_data['sub_mode'] = 'awaiting_discount'
    await query.edit_message_text(
        "🎟 <b>کد تخفیف</b>\n\nکد رو تایپ کن و بفرست:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data='sub:back')]])
    )


async def discount_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip().upper()
    v = await db.discount_validate(code)
    if not v['ok']:
        await update.message.reply_text(f"❌ {v['reason']}\n\nدوباره امتحان کن یا /cancel بزن.")
        return
    context.user_data['sub_discount_code'] = code
    context.user_data.pop('sub_mode', None)
    await update.message.reply_text(
        f"✅ کد <code>{code}</code> با {v['percent']}٪ تخفیف ثبت شد.\n"
        f"حالا یکی از پلن‌ها رو انتخاب کن:", parse_mode='HTML'
    )
    await show_paywall(update.message, update.effective_user.id)


# ══════════════════════════════════════════════════
#  دریافت اسکرین‌شات از دانشجو
# ══════════════════════════════════════════════════

async def screenshot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # FIX جدید: جلوگیری از اسپم — تا رسید قبلی بررسی نشده، رسید جدید قبول نمی‌شه
    if await db.sub_payment_has_pending(uid):
        await update.message.reply_text(
            "⏳ یه رسید قبلی ازت در انتظار بررسیه.\n"
            "لطفاً صبر کن تا همون بررسی بشه، بعد اگه لازم بود رسید جدید بفرست."
        )
        for k in ('sub_mode', 'sub_plan_id', 'sub_final_price', 'sub_discount_code'):
            context.user_data.pop(k, None)
        return

    plan_id = context.user_data.get('sub_plan_id')
    plan = await db.sub_plan_get(plan_id) if plan_id else None
    if not plan:
        await update.message.reply_text("❌ اول باید یه پلن انتخاب کنی. /cancel بزن و دوباره امتحان کن.")
        return

    final_price = context.user_data.get('sub_final_price', plan['price'])
    discount_code = context.user_data.get('sub_discount_code')
    photo = update.message.photo[-1]

    pid = await db.sub_payment_create(
        user_id=uid, plan_id=str(plan['_id']), plan_name=plan['name'],
        price=plan['price'], final_price=final_price,
        screenshot_file_id=photo.file_id, discount_code=discount_code,
    )

    for k in ('sub_mode', 'sub_plan_id', 'sub_final_price', 'sub_discount_code'):
        context.user_data.pop(k, None)

    user = await db.get_user(uid)
    uname = f"@{user.get('username')}" if user and user.get('username') else '—'
    name  = user.get('name', update.effective_user.full_name) if user else update.effective_user.full_name
    reject_count = await db.sub_payment_reject_count(uid)
    warn_line = f"\n⚠️ این کاربر قبلاً {reject_count} بار رد شده\n" if reject_count > 0 else ""

    caption = (
        f"💳 <b>رسید پرداخت اشتراک جدید</b>\n\n"
        f"👤 {name} | {uname}\n"
        f"🆔 <code>{uid}</code>\n"
        f"📦 پلن: {plan['name']} ({plan['days']} روز)\n"
        f"💰 مبلغ: {_fmt_price(final_price)}"
        + (f" (کد {discount_code})" if discount_code else "") + "\n"
        + warn_line
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأیید", callback_data=f"sub:appr:{pid}"),
        InlineKeyboardButton("❌ رد", callback_data=f"sub:rej:{pid}"),
    ]])
    try:
        sent = await context.bot.send_photo(
            ADMIN_ID, photo.file_id, caption=caption, parse_mode='HTML', reply_markup=kb
        )
        await db.sub_payment_set_admin_msg(pid, sent.message_id)
    except Exception as e:
        logger.error(f"sub_payment admin notify failed: {e}")

    await update.message.reply_text(
        "⏳ رسیدت برای ادمین ارسال شد.\nبه‌محض بررسی، نتیجه رو بهت اطلاع می‌دیم."
    )


# ══════════════════════════════════════════════════
#  callback اصلی — دکمه‌های sub:
# ══════════════════════════════════════════════════

async def subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid   = update.effective_user.id
    parts = query.data.split(':')
    action = parts[1] if len(parts) > 1 else ''

    if action == 'plan':
        await _show_plan_detail(query, context, parts[2], uid)

    elif action == 'agree':
        await _show_payment_details(query, context, parts[2])

    elif action == 'discount':
        await _prompt_discount(query, context)

    elif action == 'back':
        context.user_data.pop('sub_mode', None)
        await show_paywall(query.message, uid, edit=True)

    elif action == 'my_status':
        await _show_my_status(query, uid)

    elif action == 'my_history':
        await _show_my_history(query, uid)

    elif action == 'appr' and uid == ADMIN_ID:
        await _admin_approve(query, context, parts[2])

    elif action == 'rej' and uid == ADMIN_ID:
        context.user_data['sub_reject_pid'] = parts[2]
        context.user_data['mode'] = 'sub_reject_reason'
        await query.message.reply_text(
            "✍️ دلیل رد رو بنویس (برای دانشجو ارسال می‌شه):"
        )


async def _admin_approve(query, context, pid: str):
    payment = await db.sub_payment_get(pid)
    if not payment or payment.get('status') != 'pending':
        await query.answer("این رسید قبلاً بررسی شده.", show_alert=True)
        return
    plan = await db.sub_plan_get(payment['plan_id'])
    days = plan['days'] if plan else 30

    await db.sub_payment_decide(pid, approved=True, admin_id=ADMIN_ID)
    end_date = await db.sub_activate(
        payment['user_id'], days, payment['plan_name'],
        source='payment', granted_by=ADMIN_ID, extend=True
    )
    if payment.get('discount_code'):
        await db.discount_consume(payment['discount_code'])

    days_left = await db.sub_days_left(payment['user_id'])
    await safe_send(
        context.bot, payment['user_id'],
        f"✅ <b>اشتراکت فعال شد!</b>\n\n"
        f"📦 پلن: {payment['plan_name']}\n"
        f"⏳ {days_left} روز اعتبار داری\n\n"
        f"از بخش «👤 پروفایل» هر وقت خواستی می‌تونی باقیمونده رو چک کنی.",
        parse_mode='HTML'
    )
    try:
        await query.edit_message_caption(
            caption=query.message.caption + "\n\n✅ <b>تأیید شد</b>",
            parse_mode='HTML'
        )
    except Exception:
        pass


async def admin_reject_reason_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pid = context.user_data.pop('sub_reject_pid', None)
    context.user_data.pop('mode', None)
    note = update.message.text.strip()
    if not pid:
        return
    payment = await db.sub_payment_get(pid)
    if not payment or payment.get('status') != 'pending':
        await update.message.reply_text("این رسید قبلاً بررسی شده.")
        return
    await db.sub_payment_decide(pid, approved=False, admin_id=update.effective_user.id, note=note)
    await safe_send(
        context.bot, payment['user_id'],
        f"❌ <b>رسیدت تأیید نشد</b>\n\n📝 دلیل: {note}\n\n"
        f"می‌تونی دوباره از بخش «📚 منابع» یا «🧪 بانک سوال» اقدام کنی و رسید جدید بفرستی.",
        parse_mode='HTML'
    )
    await update.message.reply_text("❌ رد شد و به دانشجو اطلاع داده شد.")


# ══════════════════════════════════════════════════
#  🧾 وضعیت کامل اشتراک من (صفحه‌ی اختصاصی، جزئیات کامل)
# ══════════════════════════════════════════════════

_SOURCE_LABELS = {
    'payment':      '💳 خریداری‌شده',
    'admin_manual': '🛠 فعال‌سازی دستی ادمین',
    'free_grant':   '🎁 اشتراک رایگان هدیه‌ای',
}


async def _build_my_status(uid: int):
    from utils import fmt_jalali_dt, progress_bar
    s = await db.sub_get(uid)
    keyboard = []

    if not s or s.get('status') not in ('active', 'expired', 'revoked'):
        text = "💎 <b>اشتراک ویژه من</b>\n\n⚠️ فعلاً هیچ اشتراکی نداری."
        keyboard.append([InlineKeyboardButton("💳 خرید اشتراک", callback_data='sub:back')])

    elif s.get('status') == 'active' and await db.sub_is_active(uid):
        days_left  = await db.sub_days_left(uid)
        total_days = max(1, s.get('last_plan_days', days_left) or 1)
        pct        = min(100, round(days_left / total_days * 100))
        bar        = progress_bar(pct)
        source     = _SOURCE_LABELS.get(s.get('source', ''), '—')

        # FIX جدید: تاریخ تأیید (اگه از مسیر پرداخت با رسید فعال شده) هم نشون داده بشه
        approved_line = ''
        history = await db.sub_payment_history(uid)
        approved = next((p for p in history if p['status'] == 'approved'), None)
        if approved and approved.get('reviewed_at'):
            approved_line = f"✅ تاریخ تأیید: {fmt_jalali_dt(approved['reviewed_at'])}\n"

        text = (
            "💎 <b>اشتراک ویژه من</b>\n"
            "━━━━━━━━━━━━━━━━\n"
            f"📦 پلن: <b>{s.get('plan_name','—')}</b>\n"
            f"🎫 منبع: {source}\n"
            f"📅 تاریخ خرید: {fmt_jalali_dt(s.get('start_date',''), with_time=False)}\n"
            f"{approved_line}"
            f"📅 تاریخ انقضا: <b>{fmt_jalali_dt(s.get('end_date',''), with_time=False)}</b>\n\n"
            f"⏳ <b>{days_left} روز</b> باقی‌مانده\n"
            f"<code>[{bar}]</code> {pct}٪"
        )
        keyboard.append([InlineKeyboardButton("🔄 تمدید زودتر", callback_data='sub:back')])

    elif s.get('status') == 'revoked':
        text = (
            "💎 <b>اشتراک ویژه من</b>\n\n"
            "🚫 اشتراکت لغو شده.\n"
            f"📝 دلیل: {s.get('revoke_reason','—')}\n\n"
            "اگه فکر می‌کنی اشتباهیه، از «🎫 پشتیبانی» با ادمین در تماس باش."
        )
    else:  # expired
        text = (
            "💎 <b>اشتراک ویژه من</b>\n\n"
            "⌛ آخرین اشتراکت تموم شده.\n"
            f"📦 پلن قبلی: {s.get('plan_name','—')}\n"
            f"📅 تا: {fmt_jalali_dt(s.get('end_date',''), with_time=False)}"
        )
        keyboard.append([InlineKeyboardButton("🔄 تمدید کن", callback_data='sub:back')])

    keyboard.append([InlineKeyboardButton("🧾 تاریخچه‌ی پرداخت‌ها", callback_data='sub:my_history')])
    return text, keyboard


async def _show_my_status(query, uid: int):
    text, keyboard = await _build_my_status(uid)
    try:
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        await query.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def show_my_status_msg(update):
    """FIX جدید: نسخه‌ی پیامی (نه callback) — برای دکمه‌ی «💎 اشتراک ویژه» توی منوی اصلی"""
    uid = update.effective_user.id
    text, keyboard = await _build_my_status(uid)
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_my_history(query, uid: int):
    from utils import fmt_jalali_dt
    history = await db.sub_payment_history(uid)
    status_icons = {'pending': '⏳', 'approved': '✅', 'rejected': '❌'}
    if not history:
        text = "🧾 <b>تاریخچه‌ی پرداخت‌ها</b>\n\nهنوز رسیدی ثبت نکردی."
    else:
        lines = ["🧾 <b>تاریخچه‌ی پرداخت‌ها</b>\n━━━━━━━━━━━━━━━━"]
        for p in history[:15]:
            icon = status_icons.get(p['status'], '•')
            date = fmt_jalali_dt(p.get('submitted_at', ''))
            lines.append(f"{icon} {p['plan_name']} — {_fmt_price(p['final_price'])} — {date}")
            if p['status'] == 'rejected' and p.get('review_note'):
                lines.append(f"   ↳ دلیل رد: {p['review_note']}")
        text = "\n".join(lines)
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data='sub:my_status')]]
    try:
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        await query.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════════
#  خط وضعیت برای پروفایل (نمای فشرده)
# ══════════════════════════════════════════════════

async def sub_status_line(uid: int) -> str:
    enforced = await db.get_setting('subscription_enforced', False)
    s = await db.sub_get(uid)
    if not enforced and (not s or s.get('status') != 'active'):
        return ""  # وقتی اجباری نیست و اشتراکی هم نداره، اصلاً خط اشتراک نشون نده
    if s and s.get('status') == 'active' and await db.sub_is_active(uid):
        days = await db.sub_days_left(uid)
        return f"💳 اشتراک: ✅ فعال — {days} روز باقی‌مانده\n"
    if s and s.get('status') == 'revoked':
        return "💳 اشتراک: ❌ لغوشده\n"
    return "💳 اشتراک: ⚠️ نداری — از «📚 منابع» می‌تونی فعالش کنی\n"

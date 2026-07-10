"""
🎫 تیکت پشتیبانی — نسخه پیشرفته
  ✅ پیش‌نمایش تیکت قبل از ارسال
  ✅ گفتگوی دوطرفه — دانشجو میتونه ادامه بده
  ✅ مدیریت پیشرفته برای ادمین: فیلتر، جستجو، ورودی
  ✅ اطلاعات کامل کاربری در پیام ادمین (ورودی، گروه)
  ✅ تیکت باز = کانال گفتگو، نه یک پیام
"""
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes
from database import db
from utils import fmt_jalali, send_audit_log

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

TICKET_WAITING       = 60
TICKET_REPLY_WAITING = 61

SUBJECTS = [
    "🔬 مشکل در بخش علوم پایه",
    "📚 مشکل در بخش رفرنس‌ها",
    "🧪 مشکل در بانک سوال",
    "📅 مشکل در برنامه/امتحانات",
    "👤 مشکل حساب کاربری",
    "⚙️ مشکل فنی",
    "💡 پیشنهاد بهبود",
    "❓ سوال دیگر",
]


# ══════════════════════════════════════════════════
#  Callback اصلی
# ══════════════════════════════════════════════════

USER_TICKET_ACTIONS = {
    'main', 'new', 'subject', 'preview_confirm', 'preview_cancel',
    'list', 'view', 'reply_user',
}


async def ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    uid    = update.effective_user.id
    parts  = query.data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    # FIX جدید (باگ اسپم تیکت): کاربر حذف‌شده/بلاک‌شده ممکن است هنوز
    # دکمه‌ی شیشه‌ای قدیمی «تیکت جدید» یا «مشاهده‌ی تیکت» را در چت
    # قبلی‌اش داشته باشد. بدون این چک می‌توانست با لمس همان دکمه،
    # بدون هیچ رکوردی در دیتابیس، تیکت خالی/اسپم بسازد.
    if action in USER_TICKET_ACTIONS and uid != ADMIN_ID:
        u = await db.get_user(uid)
        if not u or not u.get('approved'):
            await query.answer(
                "⚠️ حساب شما یافت نشد یا هنوز تأیید نشده. لطفاً با /start ثبت‌نام کنید.",
                show_alert=True
            )
            return

    await query.answer()

    if action == 'main':
        await _ticket_main(query, uid)

    elif action == 'new':
        keyboard = [
            [InlineKeyboardButton(s, callback_data=f'ticket:subject:{i}')]
            for i, s in enumerate(SUBJECTS)
        ]
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='ticket:main')])
        await query.edit_message_text(
            "🎫 <b>تیکت جدید</b>\n\nموضوع مشکل را انتخاب کنید:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'subject':
        subject = SUBJECTS[int(parts[2])]
        context.user_data['ticket_subject'] = subject
        context.user_data['ticket_mode']    = 'waiting_message'
        await query.edit_message_text(
            f"🎫 <b>{subject}</b>\n\n"
            "✍️ توضیح کامل مشکل خود را بنویسید:\n"
            "<i>هرچه دقیق‌تر بنویسید، سریع‌تر پاسخ می‌گیرید.</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='ticket:main')
            ]])
        )
        return TICKET_WAITING

    elif action == 'preview_confirm':
        # تأیید پیش‌نمایش — ارسال واقعی
        await _do_create_ticket(update, context, confirmed=True)

    elif action == 'preview_cancel':
        # ویرایش — برگشت به نوشتن
        context.user_data['ticket_mode'] = 'waiting_message'
        subject = context.user_data.get('ticket_subject', '')
        await query.edit_message_text(
            f"🎫 <b>{subject}</b>\n\n"
            "✍️ پیام جدید خود را بنویسید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو کامل", callback_data='ticket:main')
            ]])
        )
        return TICKET_WAITING

    elif action == 'list':
        await _ticket_list(query, uid)

    elif action == 'view':
        tid    = int(parts[2])
        ticket = await db.ticket_get(tid)
        if not ticket or ticket['user_id'] != uid:
            await query.answer("❌ تیکت پیدا نشد!", show_alert=True)
            return
        await _show_ticket_detail(query, ticket, is_admin=False)

    # ── ادامه مکالمه توسط دانشجو ──
    elif action == 'reply_user':
        tid    = int(parts[2])
        ticket = await db.ticket_get(tid)
        if not ticket or ticket['user_id'] != uid:
            await query.answer("❌ دسترسی ندارید!", show_alert=True)
            return
        if ticket.get('status') == 'closed':
            await query.answer("❌ این تیکت بسته شده. تیکت جدید باز کنید.", show_alert=True)
            return
        context.user_data['user_replying_ticket'] = tid
        context.user_data['ticket_mode']          = 'user_reply'
        await query.edit_message_text(
            f"💬 <b>ادامه تیکت #{tid}</b>\n\n"
            "پیام جدید خود را بنویسید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data=f'ticket:view:{tid}')
            ]])
        )
        return TICKET_WAITING

    # ══════════════════════════════════════════════
    # بخش ادمین — مدیریت پیشرفته
    # ══════════════════════════════════════════════

    elif action == 'manage' and uid == ADMIN_ID:
        await _admin_manage(query, context)

    elif action == 'admin_filter' and uid == ADMIN_ID:
        ftype = parts[2] if len(parts) > 2 else 'status'
        fval  = parts[3] if len(parts) > 3 else 'all'
        context.user_data[f'tkt_f_{ftype}'] = fval
        await _admin_manage(query, context)

    elif action == 'admin_search' and uid == ADMIN_ID:
        context.user_data['ticket_mode']   = 'admin_search'
        context.user_data['mode']          = 'ticket_search'
        await query.edit_message_text(
            "🔍 <b>جستجوی تیکت</b>\n\n"
            "شماره تیکت یا نام کاربر را وارد کنید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='ticket:manage')
            ]])
        )

    elif action == 'admin_view' and uid == ADMIN_ID:
        tid    = int(parts[2])
        ticket = await db.ticket_get(tid)
        if not ticket:
            await query.answer("❌ پیدا نشد!", show_alert=True)
            return
        await _show_ticket_detail(query, ticket, is_admin=True)

    elif action == 'admin_reply' and uid == ADMIN_ID:
        tid = int(parts[2])
        context.user_data['replying_ticket'] = tid
        context.user_data['ticket_mode']     = 'admin_reply'
        ticket  = await db.ticket_get(tid)
        rc      = len(ticket.get('replies', [])) if ticket else 0
        await query.edit_message_text(
            f"✏️ <b>پاسخ به تیکت #{tid}</b>\n"
            f"پاسخ‌های قبلی: {rc}\n\n"
            "پاسخ جدید خود را بنویسید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data=f'ticket:admin_view:{tid}')
            ]])
        )
        return TICKET_REPLY_WAITING

    elif action == 'admin_close' and uid == ADMIN_ID:
        tid = int(parts[2])
        await query.edit_message_text(
            f"🔒 <b>بستن تیکت #{tid}</b>\n\n"
            "آیا مطمئنید که مشکل حل شده؟",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ بله، ببند", callback_data=f'ticket:admin_close_confirm:{tid}')],
                [InlineKeyboardButton("❌ برگشت",     callback_data=f'ticket:admin_view:{tid}')],
            ])
        )

    elif action == 'admin_close_confirm' and uid == ADMIN_ID:
        tid    = int(parts[2])
        ticket = await db.ticket_get(tid)
        await db.ticket_close(tid)
        # FIX طبق سند: بستن تیکت = HIGH (تصمیم نهایی پشتیبانی)،
        # و target_label موضوع/کاربر تیکت را نشان می‌دهد، نه فقط شماره
        admin_user = await db.get_user(uid)
        actor_name = admin_user.get('name', 'ادمین') if admin_user else 'ادمین'
        actor_role = await db.get_actor_role_label(uid)
        ticket_label = f"{ticket.get('subject','')} — {ticket.get('user_name','')}" if ticket else f"تیکت #{tid}"
        await send_audit_log(
            context.bot, 'admin', actor_name, uid,
            "بستن تیکت", module='Tickets', severity='HIGH',
            actor_role=actor_role,
            target_id=str(tid), target_type='ticket', target_label=ticket_label,
            tags=['بستن_تیکت']
        )
        if ticket:
            try:
                await context.bot.send_message(
                    ticket['user_id'],
                    f"✅ <b>تیکت #{tid} بسته شد</b>\n\n"
                    f"📋 {ticket.get('subject','')}\n\n"
                    "مشکل شما حل‌شده تلقی شد.\n"
                    "اگر سوال جدیدی دارید، تیکت جدید ثبت کنید.",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🎫 تیکت جدید", callback_data='ticket:new')
                    ]])
                )
            except Exception:
                pass
        await query.edit_message_text(
            f"✅ تیکت #{tid} بسته شد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 مدیریت تیکت‌ها", callback_data='ticket:manage')
            ]])
        )

    elif action == 'admin_reopen' and uid == ADMIN_ID:
        # FIX جدید طبق سند: بازگشایی تیکت — قابلیت کاملاً جدید
        tid    = int(parts[2])
        ticket = await db.ticket_get(tid)
        await db.ticket_reopen(tid)
        admin_user = await db.get_user(uid)
        actor_name = admin_user.get('name', 'ادمین') if admin_user else 'ادمین'
        actor_role = await db.get_actor_role_label(uid)
        ticket_label = f"{ticket.get('subject','')} — {ticket.get('user_name','')}" if ticket else f"تیکت #{tid}"
        await send_audit_log(
            context.bot, 'admin', actor_name, uid,
            "بازگشایی تیکت", module='Tickets', severity='WARNING',
            actor_role=actor_role,
            target_id=str(tid), target_type='ticket', target_label=ticket_label,
            before={'وضعیت': 'بسته شده'}, after={'وضعیت': 'باز'},
            tags=['بازگشایی_تیکت']
        )
        if ticket:
            try:
                await context.bot.send_message(
                    ticket['user_id'],
                    f"🔓 <b>تیکت #{tid} مجدداً باز شد</b>\n\n"
                    f"📋 {ticket.get('subject','')}\n\n"
                    "می‌توانید ادامه گفتگو را ارسال کنید.",
                    parse_mode='HTML'
                )
            except Exception:
                pass
        await query.edit_message_text(
            f"🔓 تیکت #{tid} بازگشایی شد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 مدیریت تیکت‌ها", callback_data='ticket:manage')
            ]])
        )

    # سازگاری با callback های قدیمی
    elif action == 'admin_list' and uid == ADMIN_ID:
        await _admin_manage(query, context)

    elif action == 'admin_all' and uid == ADMIN_ID:
        context.user_data['tkt_f_status'] = 'all'
        await _admin_manage(query, context)


# ══════════════════════════════════════════════════
#  هندلر پیام
# ══════════════════════════════════════════════════

async def ticket_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    user = await db.get_user(uid)
    mode = context.user_data.get('ticket_mode', '')
    text = update.message.text.strip()

    # ── دانشجو: پیام اولیه تیکت — نمایش پیش‌نمایش ──
    if mode == 'waiting_message':
        subject = context.user_data.get('ticket_subject', 'سوال')
        context.user_data['ticket_draft'] = text
        context.user_data['ticket_mode']  = 'awaiting_confirm'

        await update.message.reply_text(
            f"👁 <b>پیش‌نمایش تیکت</b>\n\n"
            f"📋 موضوع: <b>{subject}</b>\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"💬 {text}\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            "آیا این تیکت را ارسال می‌کنید؟",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ بله، ارسال کن", callback_data='ticket:preview_confirm'),
                    InlineKeyboardButton("✏️ ویرایش",        callback_data='ticket:preview_cancel'),
                ],
                [InlineKeyboardButton("❌ لغو کامل", callback_data='ticket:main')],
            ])
        )
        return TICKET_WAITING

    # ── دانشجو: تأیید شده — ارسال واقعی ──
    elif mode == 'awaiting_confirm':
        # این حالت از callback handle میشه، نه از پیام
        pass

    # ── دانشجو: ادامه مکالمه در تیکت باز ──
    elif mode == 'user_reply':
        tid = context.user_data.get('user_replying_ticket')
        if not tid:
            return
        ticket = await db.ticket_get(tid)
        if not ticket or ticket.get('status') == 'closed':
            await update.message.reply_text("❌ این تیکت بسته شده.")
            context.user_data.pop('ticket_mode', None)
            return

        # اضافه کردن پیام به replies با تگ [دانشجو]
        reply_text = f"[دانشجو] {text}"
        await db.ticket_add_reply(tid, reply_text)
        context.user_data.pop('ticket_mode', None)
        context.user_data.pop('user_replying_ticket', None)

        name = user.get('name', '') if user else ''
        # اطلاع به ادمین
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"💬 <b>پیام جدید در تیکت #{tid}</b>\n"
                f"👤 {name}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"{text}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(f"✏️ پاسخ تیکت #{tid}", callback_data=f'ticket:admin_view:{tid}')
                ]])
            )
        except Exception:
            pass

        await update.message.reply_text(
            f"✅ پیام شما به تیکت #{tid} اضافه شد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"📋 مشاهده تیکت #{tid}", callback_data=f'ticket:view:{tid}')
            ]])
        )

    # ── جستجوی تیکت توسط ادمین ──
    elif mode == 'admin_search' and uid == ADMIN_ID:
        context.user_data.pop('ticket_mode', None)
        context.user_data.pop('mode', None)
        await _search_tickets(update, text)

    # ── پاسخ ادمین به تیکت ──
    elif mode == 'admin_reply' and uid == ADMIN_ID:
        tid = context.user_data.pop('replying_ticket', None)
        if not tid:
            return
        context.user_data['ticket_mode'] = ''
        ticket = await db.ticket_get(tid)
        await db.ticket_add_reply(tid, text)

        if ticket:
            try:
                await context.bot.send_message(
                    ticket['user_id'],
                    f"📨 <b>پاسخ به تیکت #{tid}</b>\n"
                    f"📋 {ticket.get('subject','')}\n"
                    f"━━━━━━━━━━━━━━━━\n\n"
                    f"💬 {text}\n\n"
                    "<i>برای ادامه گفتگو می‌توانید پاسخ دهید.</i>",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(f"💬 ادامه گفتگو", callback_data=f'ticket:reply_user:{tid}'),
                        InlineKeyboardButton(f"📋 مشاهده تیکت", callback_data=f'ticket:view:{tid}'),
                    ]])
                )
            except Exception:
                pass

        await update.message.reply_text(
            f"✅ پاسخ به تیکت #{tid} ارسال شد!",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"📋 تیکت #{tid}", callback_data=f'ticket:admin_view:{tid}'),
                    InlineKeyboardButton("🔒 بستن",          callback_data=f'ticket:admin_close:{tid}'),
                ],
                [InlineKeyboardButton("🔙 مدیریت تیکت‌ها", callback_data='ticket:manage')],
            ])
        )


async def _do_create_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE, confirmed: bool = False):
    """ارسال واقعی تیکت بعد از تأیید پیش‌نمایش"""
    query   = update.callback_query
    uid     = update.effective_user.id
    user    = await db.get_user(uid)

    # FIX جدید: لایه‌ی دوم دفاعی — حتی اگر مسیر دیگری (context.user_data
    # آویزون) به این تابع برسد، بدون رکورد معتبر کاربر هیچ تیکتی ساخته
    # نمی‌شود.
    if not user or not user.get('approved'):
        context.user_data.clear()
        await query.answer("⚠️ حساب شما یافت نشد. لطفاً با /start ثبت‌نام کنید.", show_alert=True)
        return

    subject = context.user_data.get('ticket_subject', 'سوال')
    text    = context.user_data.get('ticket_draft', '')

    if not text:
        await query.answer("❌ پیامی برای ارسال وجود ندارد!", show_alert=True)
        return

    name    = user.get('name', '')      if user else ''
    sid     = user.get('student_id','') if user else ''
    group   = user.get('group', '')     if user else ''
    intake  = user.get('intake', '')    if user else ''
    uname   = f"@{user.get('username','')}" if user and user.get('username') else 'ندارد'

    tid = await db.ticket_create(uid, name, subject, text)
    context.user_data.pop('ticket_mode', None)
    context.user_data.pop('ticket_draft', None)
    context.user_data.pop('ticket_subject', None)

    # اطلاع کامل به ادمین با ورودی
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"🔔 <b>تیکت جدید #{tid}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 <b>نام:</b> {name}\n"
            f"🎓 <b>شماره دانشجویی:</b> {sid or '—'}\n"
            f"📅 <b>ورودی:</b> {intake or '—'}\n"
            f"👥 <b>گروه:</b> {group or '—'}\n"
            f"📱 <b>یوزرنیم:</b> {uname}\n"
            f"🆔 <b>آیدی:</b> <code>{uid}</code>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📋 <b>موضوع:</b> {subject}\n\n"
            f"💬 <b>متن تیکت:</b>\n{text}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"✏️ پاسخ به تیکت #{tid}", callback_data=f'ticket:admin_view:{tid}')
            ]])
        )
    except Exception:
        pass

    await query.edit_message_text(
        f"✅ <b>تیکت #{tid} با موفقیت ثبت شد!</b>\n\n"
        "📬 به زودی پاسخ داده خواهد شد.\n"
        "تا زمانی که تیکت باز است، می‌توانید پیام جدید اضافه کنید. 🙏",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📋 مشاهده تیکت #{tid}", callback_data=f'ticket:view:{tid}')],
            [InlineKeyboardButton("🔙 بازگشت به پشتیبانی",  callback_data='ticket:main')],
        ])
    )


# ══════════════════════════════════════════════════
#  مدیریت تیکت‌ها — ادمین پیشرفته
# ══════════════════════════════════════════════════

async def _admin_manage(query, context):
    """پنل مدیریت تیکت‌ها با فیلتر پیشرفته"""
    f_status = context.user_data.get('tkt_f_status', 'open')
    f_intake = context.user_data.get('tkt_f_intake', 'all')

    # دریافت تیکت‌ها
    if f_status == 'all':
        tickets = await db.ticket_get_all()
    else:
        tickets = await db.ticket_get_all(f_status)

    # فیلتر ورودی
    if f_intake != 'all':
        user_ids_in_intake = set()
        intake_users = await db.get_users_by_intake(f_intake)
        user_ids_in_intake = {u['user_id'] for u in intake_users}
        tickets = [t for t in tickets if t.get('user_id') in user_ids_in_intake]

    total  = len(tickets)
    open_c = sum(1 for t in tickets if t.get('status') == 'open')
    closed_c = total - open_c

    # دکمه‌های فیلتر وضعیت
    s_btns = [
        InlineKeyboardButton(
            f"{'✅' if f_status=='open' else '⬜'} 🟡 باز ({open_c})",
            callback_data='ticket:admin_filter:status:open'
        ),
        InlineKeyboardButton(
            f"{'✅' if f_status=='closed' else '⬜'} 🟢 بسته ({closed_c})",
            callback_data='ticket:admin_filter:status:closed'
        ),
        InlineKeyboardButton(
            f"{'✅' if f_status=='all' else '⬜'} 📂 همه ({total})",
            callback_data='ticket:admin_filter:status:all'
        ),
    ]

    # دکمه‌های فیلتر ورودی
    intakes = await db.get_all_intakes()
    i_btns  = [InlineKeyboardButton(
        f"{'✅' if f_intake=='all' else '⬜'} همه ورودی‌ها",
        callback_data='ticket:admin_filter:intake:all'
    )]
    for i in intakes:
        i_btns.append(InlineKeyboardButton(
            f"{'✅' if f_intake==i['code'] else '⬜'} {i['label']}",
            callback_data=f'ticket:admin_filter:intake:{i["code"]}'
        ))

    keyboard = [s_btns]
    # اگه ورودی‌ها زیاد بود، دو تا در هر ردیف
    for idx in range(0, len(i_btns), 2):
        keyboard.append(i_btns[idx:idx+2])

    # لیست تیکت‌ها
    for t in tickets[:12]:
        icon = "🟢" if t['status'] == 'closed' else "🟡"
        rc   = len(t.get('replies', []))
        keyboard.append([InlineKeyboardButton(
            f"{icon} #{t['ticket_id']} | {t.get('user_name','')[:8]} | {t.get('subject','')[:16]} | {rc}💬",
            callback_data=f"ticket:admin_view:{t['ticket_id']}"
        )])

    keyboard.append([InlineKeyboardButton("🔍 جستجوی تیکت", callback_data='ticket:admin_search')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:cat_comm')])

    await query.edit_message_text(
        f"🎫 <b>مدیریت تیکت‌ها</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🟡 باز: <b>{open_c}</b>  |  🟢 بسته: <b>{closed_c}</b>  |  📂 کل: <b>{total}</b>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _search_tickets(update: Update, query_text: str):
    """جستجوی تیکت با شماره یا نام کاربر"""
    results = []

    # جستجو با شماره تیکت
    if query_text.isdigit():
        t = await db.ticket_get(int(query_text))
        if t:
            results = [t]
    else:
        # جستجو با نام
        all_tickets = await db.ticket_get_all()
        results = [
            t for t in all_tickets
            if query_text.lower() in t.get('user_name', '').lower()
        ]

    if not results:
        await update.message.reply_text(
            f"❌ نتیجه‌ای برای «{query_text}» پیدا نشد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 مدیریت تیکت‌ها", callback_data='ticket:manage')
            ]])
        )
        return

    keyboard = []
    for t in results[:10]:
        icon = "🟢" if t['status'] == 'closed' else "🟡"
        keyboard.append([InlineKeyboardButton(
            f"{icon} #{t['ticket_id']} | {t.get('user_name','')} | {t.get('subject','')[:20]}",
            callback_data=f"ticket:admin_view:{t['ticket_id']}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='ticket:manage')])

    await update.message.reply_text(
        f"🔍 <b>{len(results)} نتیجه برای «{query_text}»:</b>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ══════════════════════════════════════════════════
#  نمایش‌دهنده‌ها
# ══════════════════════════════════════════════════

async def _show_ticket_detail(query, ticket: dict, is_admin: bool):
    tid         = ticket['ticket_id']
    status      = ticket.get('status', 'open')
    status_icon = "🟢 بسته شده" if status == 'closed' else "🟡 در جریان"
    replies     = ticket.get('replies', [])

    if is_admin:
        # اطلاعات کامل کاربری برای ادمین
        uid_t = ticket.get('user_id', '')
        user  = await db.get_user(uid_t) if uid_t else None
        intake = user.get('intake', '') if user else ''
        group  = user.get('group', '')  if user else ''
        sid    = user.get('student_id', '') if user else ''

        text = (
            f"🎫 <b>تیکت #{tid}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 نام: <b>{ticket.get('user_name','')}</b>\n"
            f"🆔 آیدی: <code>{uid_t}</code>\n"
            f"🎓 شماره: {sid or '—'}\n"
            f"📅 ورودی: {intake or '—'}\n"
            f"👥 گروه: {group or '—'}\n"
            f"📋 موضوع: {ticket.get('subject','')}\n"
            f"🔘 وضعیت: {status_icon}\n"
            f"📅 تاریخ ثبت: {ticket['created_at'][:10]}\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"💬 <b>پیام اولیه:</b>\n{ticket['message']}\n"
        )
    else:
        text = (
            f"🎫 <b>تیکت #{tid}</b>\n"
            f"📋 {ticket.get('subject','')}\n"
            f"🔘 {status_icon}\n"
            f"📅 {ticket['created_at'][:10]}\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"💬 <b>پیام شما:</b>\n{ticket['message']}\n"
        )

    # نمایش همه پاسخ‌ها
    if replies:
        text += f"\n━━━━━━━━━━━━━━━━\n💬 <b>ادامه گفتگو ({len(replies)}):</b>\n"
        for i, r in enumerate(replies, 1):
            at_str  = r.get('at', '')[:10] if r.get('at') else ''
            msg_txt = r.get('text', '')
            # تشخیص فرستنده
            if msg_txt.startswith('[دانشجو]'):
                sender = "🧑‍🎓"
                msg_txt = msg_txt[8:].strip()
            else:
                sender = "🎓 پشتیبانی"
            text += f"\n{sender}  <i>{at_str}</i>\n{msg_txt}\n"

    keyboard = []
    if is_admin:
        if status == 'open':
            keyboard.append([InlineKeyboardButton("✏️ پاسخ جدید", callback_data=f'ticket:admin_reply:{tid}')])
            keyboard.append([InlineKeyboardButton("🔒 بستن تیکت",  callback_data=f'ticket:admin_close:{tid}')])
        else:
            # FIX جدید طبق سند: بازگشایی تیکت بسته‌شده
            keyboard.append([InlineKeyboardButton("🔓 بازگشایی تیکت", callback_data=f'ticket:admin_reopen:{tid}')])
        keyboard.append([InlineKeyboardButton("🔙 مدیریت تیکت‌ها", callback_data='ticket:manage')])
    else:
        if status == 'open':
            keyboard.append([InlineKeyboardButton("💬 ادامه گفتگو", callback_data=f'ticket:reply_user:{tid}')])
        keyboard.append([InlineKeyboardButton("🔙 تیکت‌های من", callback_data='ticket:list')])

    try:
        await query.edit_message_text(
            text[:4090], parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        pass


async def _ticket_main(query, uid: int):
    tickets    = await db.ticket_get_user(uid)
    open_count = sum(1 for t in tickets if t['status'] == 'open')
    done_count = len(tickets) - open_count
    keyboard   = [
        [InlineKeyboardButton("🎫 ارسال تیکت جدید",            callback_data='ticket:new')],
        [InlineKeyboardButton(f"📋 تیکت‌های من ({len(tickets)})", callback_data='ticket:list')],
    ]
    if uid == ADMIN_ID:
        open_t = await db.ticket_get_all('open')
        all_t  = await db.ticket_get_all()
        keyboard.append([InlineKeyboardButton(
            f"🎫 مدیریت تیکت‌ها ({len(open_t)} باز / {len(all_t)} کل)",
            callback_data='ticket:manage'
        )])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='dashboard:refresh')])
    await query.edit_message_text(
        f"🎫 <b>پشتیبانی</b>\n\n"
        f"🟡 باز: {open_count}  |  🟢 بسته‌شده: {done_count}\n\n"
        "برای ارسال مشکل یا سوال، تیکت جدید بزنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _ticket_list(query, uid: int):
    tickets = await db.ticket_get_user(uid)
    if not tickets:
        await query.edit_message_text(
            "📋 هیچ تیکتی ندارید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎫 تیکت جدید", callback_data='ticket:new')],
                [InlineKeyboardButton("🔙 بازگشت",    callback_data='ticket:main')],
            ])
        )
        return
    keyboard = []
    for t in tickets[:12]:
        icon = "🟢" if t['status'] == 'closed' else "🟡"
        rc   = len(t.get('replies', []))
        status_str = "بسته" if t['status'] == 'closed' else "در جریان"
        keyboard.append([InlineKeyboardButton(
            f"{icon} #{t['ticket_id']} | {t.get('subject','')[:20]} | {status_str} | {rc} پیام",
            callback_data=f"ticket:view:{t['ticket_id']}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='ticket:main')])
    await query.edit_message_text(
        "📋 <b>تیکت‌های من</b>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_ticket_main(message: Message, uid: int):
    tickets    = await db.ticket_get_user(uid)
    open_count = sum(1 for t in tickets if t['status'] == 'open')
    done_count = len(tickets) - open_count
    keyboard   = [
        [InlineKeyboardButton("🎫 ارسال تیکت جدید",              callback_data='ticket:new')],
        [InlineKeyboardButton(f"📋 تیکت‌های من ({len(tickets)})", callback_data='ticket:list')],
    ]
    if uid == ADMIN_ID:
        open_t = await db.ticket_get_all('open')
        all_t  = await db.ticket_get_all()
        keyboard.append([InlineKeyboardButton(
            f"🎫 مدیریت تیکت‌ها ({len(open_t)} باز / {len(all_t)} کل)",
            callback_data='ticket:manage'
        )])
    await message.reply_text(
        f"🎫 <b>پشتیبانی</b>\n\n"
        f"🟡 باز: {open_count}  |  🟢 بسته‌شده: {done_count}\n\n"
        "برای ارسال مشکل یا سوال، تیکت جدید بزنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )

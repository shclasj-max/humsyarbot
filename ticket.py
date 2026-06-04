"""تیکت پشتیبانی — چند پاسخ، بستن دستی توسط ادمین"""
import os, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from utils import fmt_jalali

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


async def ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    uid    = update.effective_user.id
    data   = query.data
    parts  = data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    if action == 'main':
        await _ticket_main(query, uid)

    elif action == 'new':
        keyboard = [[InlineKeyboardButton(s, callback_data=f'ticket:subject:{i}')] for i, s in enumerate(SUBJECTS)]
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='ticket:main')])
        await query.edit_message_text(
            "🎫 <b>تیکت جدید</b>\n\nموضوع مشکل را انتخاب کنید:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'subject':
        idx     = int(parts[2])
        subject = SUBJECTS[idx]
        context.user_data['ticket_subject'] = subject
        context.user_data['ticket_mode']    = 'waiting_message'
        await query.edit_message_text(
            f"🎫 <b>{subject}</b>\n\n"
            "✍️ توضیح کامل مشکل خود را بنویسید:\n"
            "<i>هرچه دقیق‌تر بنویسید، سریع‌تر پاسخ می‌گیرید.</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='ticket:main')]])
        )
        return TICKET_WAITING

    elif action == 'list':
        await _ticket_list(query, uid)

    elif action == 'view':
        tid    = int(parts[2])
        ticket = await db.ticket_get(tid)
        if not ticket or ticket['user_id'] != uid:
            await query.answer("❌ تیکت پیدا نشد!", show_alert=True); return
        await _show_ticket_detail(query, ticket, is_admin=False)

    # ── ادمین ──
    elif action == 'admin_list':
        if uid != ADMIN_ID: return
        await _admin_ticket_list(query, status_filter='open')

    elif action == 'admin_all':
        if uid != ADMIN_ID: return
        await _admin_ticket_list(query, status_filter=None)

    elif action == 'admin_view':
        if uid != ADMIN_ID: return
        tid    = int(parts[2])
        ticket = await db.ticket_get(tid)
        if not ticket:
            await query.answer("❌ پیدا نشد!", show_alert=True); return
        await _show_ticket_detail(query, ticket, is_admin=True)

    elif action == 'admin_reply':
        if uid != ADMIN_ID: return
        tid = int(parts[2])
        context.user_data['replying_ticket'] = tid
        context.user_data['ticket_mode']     = 'admin_reply'
        ticket = await db.ticket_get(tid)
        replies_count = len(ticket.get('replies', [])) if ticket else 0
        await query.edit_message_text(
            f"✏️ <b>پاسخ به تیکت #{tid}</b>\n"
            f"تعداد پاسخ‌های قبلی: {replies_count}\n\n"
            "پاسخ جدید خود را بنویسید:\n"
            "<i>تیکت باز می‌ماند تا زمانی که شما آن را ببندید.</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data=f'ticket:admin_view:{tid}')
            ]])
        )
        return TICKET_REPLY_WAITING

    elif action == 'admin_close':
        if uid != ADMIN_ID: return
        tid    = int(parts[2])
        ticket = await db.ticket_get(tid)
        # تأییدیه بستن
        await query.edit_message_text(
            f"🔒 <b>بستن تیکت #{tid}</b>\n\n"
            "آیا مطمئنید که مشکل حل شده و می‌خواهید تیکت را ببندید؟",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ بله، تیکت را ببند", callback_data=f'ticket:admin_close_confirm:{tid}')],
                [InlineKeyboardButton("❌ خیر، برگشت",       callback_data=f'ticket:admin_view:{tid}')],
            ])
        )

    elif action == 'admin_close_confirm':
        if uid != ADMIN_ID: return
        tid    = int(parts[2])
        ticket = await db.ticket_get(tid)
        await db.ticket_close(tid)
        # اطلاع به کاربر
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
            except: pass
        await query.edit_message_text(
            f"✅ تیکت #{tid} با موفقیت بسته شد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت به تیکت‌های باز", callback_data='ticket:admin_list')
            ]])
        )


async def _show_ticket_detail(query, ticket, is_admin: bool):
    tid     = ticket['ticket_id']
    status  = ticket.get('status', 'open')
    status_icon = "🟢 بسته شده" if status == 'closed' else "🟡 در انتظار / در جریان"

    # پاسخ‌ها (سازگار با فیلد reply قدیمی)
    replies = ticket.get('replies', [])
    if not replies and ticket.get('reply'):
        replies = [{'text': ticket['reply'], 'at': ticket.get('replied_at', '')}]

    if is_admin:
        # نمایش کامل اطلاعات دانشجو برای ادمین
        text = (
            f"🎫 <b>تیکت #{tid}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 <b>نام:</b> {ticket.get('user_name','')}\n"
            f"🆔 <b>آیدی:</b> <code>{ticket['user_id']}</code>\n"
            f"📋 <b>موضوع:</b> {ticket.get('subject','')}\n"
            f"🔘 <b>وضعیت:</b> {status_icon}\n"
            f"📅 <b>تاریخ ثبت:</b> {fmt_jalali(ticket['created_at'][:10])}\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"💬 <b>پیام دانشجو:</b>\n{ticket['message']}\n"
        )
    else:
        text = (
            f"🎫 <b>تیکت #{tid}</b>\n"
            f"📋 {ticket.get('subject','')}\n"
            f"🔘 وضعیت: {status_icon}\n"
            f"📅 {fmt_jalali(ticket['created_at'][:10])}\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"💬 <b>پیام شما:</b>\n{ticket['message']}\n"
        )

    if replies:
        text += f"\n━━━━━━━━━━━━━━━━\n📨 <b>پاسخ‌های پشتیبانی ({len(replies)}):</b>\n"
        for i, r in enumerate(replies, 1):
            at_str = fmt_jalali(r.get('at', '')[:10]) if r.get('at') else ''
            text += f"\n<b>پاسخ {i}</b>  <i>{at_str}</i>\n{r.get('text','')}\n"

    keyboard = []
    if is_admin:
        if status == 'open':
            keyboard.append([InlineKeyboardButton("✏️ ارسال پاسخ جدید", callback_data=f'ticket:admin_reply:{tid}')])
            keyboard.append([InlineKeyboardButton("🔒 بستن تیکت",        callback_data=f'ticket:admin_close:{tid}')])
        else:
            keyboard.append([InlineKeyboardButton("📋 تیکت بسته است",    callback_data=f'ticket:admin_view:{tid}')])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به لیست",   callback_data='ticket:admin_list')])
    else:
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به تیکت‌ها", callback_data='ticket:list')])

    try:
        await query.edit_message_text(text[:4090], parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        # اگر متن طولانی بود
        await query.edit_message_text(text[:4090], parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _ticket_main(query, uid):
    tickets    = await db.ticket_get_user(uid)
    open_count = sum(1 for t in tickets if t['status'] == 'open')
    done_count = sum(1 for t in tickets if t['status'] == 'closed')
    keyboard   = [
        [InlineKeyboardButton("🎫 ارسال تیکت جدید",           callback_data='ticket:new')],
        [InlineKeyboardButton(f"📋 تیکت‌های من ({len(tickets)})", callback_data='ticket:list')],
    ]
    if uid == ADMIN_ID:
        open_t = await db.ticket_get_all('open')
        all_t  = await db.ticket_get_all()
        keyboard.append([InlineKeyboardButton(f"🟡 تیکت‌های باز ({len(open_t)})",  callback_data='ticket:admin_list')])
        keyboard.append([InlineKeyboardButton(f"📂 همه تیکت‌ها ({len(all_t)})",   callback_data='ticket:admin_all')])
    await query.edit_message_text(
        f"🎫 <b>پشتیبانی</b>\n\n"
        f"🟡 تیکت‌های باز: {open_count}  |  🟢 بسته‌شده: {done_count}\n\n"
        "برای ارسال مشکل یا سوال، تیکت جدید بزنید:",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _ticket_list(query, uid):
    tickets = await db.ticket_get_user(uid)
    if not tickets:
        await query.edit_message_text(
            "📋 هیچ تیکتی ندارید.\n\nبرای ارسال مشکل، تیکت جدید بزنید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎫 تیکت جدید", callback_data='ticket:new')],
                [InlineKeyboardButton("🔙 بازگشت",    callback_data='ticket:main')]
            ])
        ); return
    keyboard = []
    for t in tickets[:12]:
        icon   = "🟢" if t['status'] == 'closed' else "🟡"
        rc     = len(t.get('replies', []))
        if not rc and t.get('reply'): rc = 1
        r_txt  = f" | {rc} پاسخ" if rc else ' | بدون پاسخ'
        keyboard.append([InlineKeyboardButton(
            f"{icon} #{t['ticket_id']} — {t.get('subject','')[:22]}{r_txt}",
            callback_data=f'ticket:view:{t["ticket_id"]}'
        )])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='ticket:main')])
    await query.edit_message_text("📋 <b>تیکت‌های من</b>", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _admin_ticket_list(query, status_filter='open'):
    tickets = await db.ticket_get_all(status_filter)
    title   = "🟡 تیکت‌های باز" if status_filter == 'open' else "📂 همه تیکت‌ها"
    if not tickets:
        await query.edit_message_text(
            f"✅ {title}\n\nهیچ تیکتی وجود ندارد!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')]]))
        return
    keyboard = []
    for t in tickets[:15]:
        icon  = "🟢" if t['status'] == 'closed' else "🟡"
        rc    = len(t.get('replies', []))
        if not rc and t.get('reply'): rc = 1
        keyboard.append([InlineKeyboardButton(
            f"{icon} #{t['ticket_id']} | {t.get('user_name','')[:8]} | {t.get('subject','')[:18]} | {rc}💬",
            callback_data=f'ticket:admin_view:{t["ticket_id"]}'
        )])
    nav = []
    if status_filter == 'open':
        nav.append(InlineKeyboardButton("📂 همه تیکت‌ها", callback_data='ticket:admin_all'))
    else:
        nav.append(InlineKeyboardButton("🟡 فقط باز", callback_data='ticket:admin_list'))
    keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')])
    await query.edit_message_text(
        f"🎫 <b>{title}</b> — {len(tickets)} تیکت",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def ticket_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    user = await db.get_user(uid)
    mode = context.user_data.get('ticket_mode', '')
    text = update.message.text.strip()

    if mode == 'waiting_message':
        subject = context.user_data.get('ticket_subject', 'سوال')
        name    = user.get('name', '') if user else ''
        sid     = user.get('student_id', '') if user else ''
        group   = user.get('group', '') if user else ''
        uname   = f"@{user.get('username','')}" if user and user.get('username') else 'ندارد'
        tid     = await db.ticket_create(uid, name, subject, text)
        context.user_data['ticket_mode'] = ''

        # اطلاع کامل به ادمین
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"🔔 <b>تیکت جدید #{tid}</b>\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"👤 <b>نام:</b> {name}\n"
                f"🎓 <b>شماره دانشجویی:</b> {sid}\n"
                f"👥 <b>گروه:</b> {group}\n"
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
        except: pass

        await update.message.reply_text(
            f"✅ <b>تیکت #{tid} ثبت شد!</b>\n\n"
            "📬 به زودی پاسخ داده خواهد شد.\n"
            "وضعیت تیکت را از بخش پشتیبانی پیگیری کنید. 🙏",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 مشاهده تیکت‌هایم", callback_data='ticket:list')
            ]])
        )

    elif mode == 'admin_reply' and uid == ADMIN_ID:
        tid = context.user_data.get('replying_ticket')
        if not tid: return
        ticket = await db.ticket_get(tid)
        await db.ticket_add_reply(tid, text)
        context.user_data['ticket_mode'] = ''

        # پاسخ به کاربر
        if ticket:
            try:
                rcount = len(ticket.get('replies', [])) + 1
                await context.bot.send_message(
                    ticket['user_id'],
                    f"📨 <b>پاسخ به تیکت #{tid}</b>\n"
                    f"📋 {ticket.get('subject','')}\n"
                    f"━━━━━━━━━━━━━━━━\n\n"
                    f"💬 {text}\n\n"
                    "<i>اگر سوال دارید، از بخش پشتیبانی ادامه دهید.</i>",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(f"📋 مشاهده تیکت #{tid}", callback_data=f'ticket:view:{tid}')
                    ]])
                )
            except: pass

        await update.message.reply_text(
            f"✅ پاسخ به تیکت #{tid} ارسال شد!\n"
            "تیکت همچنان باز است. هر وقت مشکل حل شد، آن را ببندید.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"📋 مشاهده تیکت #{tid}", callback_data=f'ticket:admin_view:{tid}'),
                InlineKeyboardButton("🔒 بستن تیکت", callback_data=f'ticket:admin_close:{tid}')
            ]])
        )


async def show_ticket_main(message, uid: int):
    """فراخوانی از message_router — دکمه 🎫 پشتیبانی"""
    tickets    = await db.ticket_get_user(uid)
    open_count = sum(1 for t in tickets if t['status'] == 'open')
    done_count = sum(1 for t in tickets if t['status'] == 'closed')
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = [
        [InlineKeyboardButton("🎫 ارسال تیکت جدید",              callback_data='ticket:new')],
        [InlineKeyboardButton(f"📋 تیکت‌های من ({len(tickets)})", callback_data='ticket:list')],
    ]
    if uid == ADMIN_ID:
        open_t = await db.ticket_get_all('open')
        all_t  = await db.ticket_get_all()
        keyboard.append([InlineKeyboardButton(f"🟡 تیکت‌های باز ({len(open_t)})", callback_data='ticket:admin_list')])
        keyboard.append([InlineKeyboardButton(f"📂 همه تیکت‌ها ({len(all_t)})",   callback_data='ticket:admin_all')])
    await message.reply_text(
        f"🎫 <b>پشتیبانی</b>\n\n"
        f"🟡 تیکت‌های باز: {open_count}  |  🟢 بسته‌شده: {done_count}\n\n"
        "برای ارسال مشکل یا سوال، تیکت جدید بزنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

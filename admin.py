"""
👨‍⚕️ پنل ادمین — یکپارچه و کامل
  ✅ فیکس باگ سرچ کاربران (mode صحیح)
  ✅ فیکس دکمه بکاپ در همه حالت‌های بازگشت
  ✅ پیجینیشن صحیح کاربران
  ✅ دکمه بازگشت در همه منوها
"""
import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from utils import main_keyboard, content_admin_keyboard, admin_keyboard, safe_send

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
BROADCAST = 5


# ══════════════════════════════════════════════════
#  منوی اصلی ادمین — با دکمه بکاپ ثابت
# ══════════════════════════════════════════════════

async def _admin_menu(query_or_msg, edit: bool = True):
    s        = await db.global_stats()
    keyboard = [
        [InlineKeyboardButton(
            f"📊 آمار  ({s['users']} کاربر | {s.get('open_tickets', 0)} تیکت باز)",
            callback_data='admin:stats'
        )],
        [
            InlineKeyboardButton("👥 مدیریت کاربران",  callback_data='admin:users:0'),
            InlineKeyboardButton("⏳ تأیید کاربران",   callback_data='admin:pending'),
        ],
        [InlineKeyboardButton("📅 مدیریت ورودی‌ها",  callback_data='admin:intakes')],
        [InlineKeyboardButton("🔍 جستجوی کاربر",      callback_data='admin:search_user')],
        [InlineKeyboardButton("🎓 ادمین‌های محتوا",    callback_data='admin:content_admins')],
        [
            InlineKeyboardButton("📘 علوم پایه",       callback_data='ca:terms_admin'),
            InlineKeyboardButton("📚 رفرنس‌ها",         callback_data='ca:refs_admin'),
        ],
        [InlineKeyboardButton("❓ مدیریت FAQ",          callback_data='ca:faq')],
        [
            InlineKeyboardButton("🧪 بانک سوال",       callback_data='admin:qbank_manage'),
            InlineKeyboardButton("✅ تأیید سوالات",    callback_data='admin:pending_q'),
        ],
        [
            InlineKeyboardButton("📅 برنامه جدید",     callback_data='schedule:add_type'),
            InlineKeyboardButton("🗑 حذف برنامه",      callback_data='schedule:del_list'),
        ],
        [InlineKeyboardButton("🎫 تیکت‌های باز",       callback_data='ticket:admin_list')],
        [InlineKeyboardButton("📢 ارسال همگانی",        callback_data='admin:broadcast')],
        [InlineKeyboardButton("💾 پشتیبان‌گیری",        callback_data='backup:menu')],
    ]
    text   = "👨‍⚕️ <b>پنل مدیریت</b>\n━━━━━━━━━━━━━━━━"
    markup = InlineKeyboardMarkup(keyboard)
    if edit and hasattr(query_or_msg, 'edit_message_text'):
        await query_or_msg.edit_message_text(text, parse_mode='HTML', reply_markup=markup)
    else:
        msg = query_or_msg if hasattr(query_or_msg, 'reply_text') else query_or_msg.message
        await msg.reply_text(text, parse_mode='HTML', reply_markup=markup)


async def show_admin_main(message):
    """فراخوانی از message_router"""
    await _admin_menu(message, edit=False)


# ══════════════════════════════════════════════════
#  Callback اصلی
# ══════════════════════════════════════════════════

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = update.effective_user.id

    if uid != ADMIN_ID:
        await query.answer("❌ دسترسی ندارید!", show_alert=True)
        return

    await query.answer()
    parts  = query.data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    # ── منوی اصلی ──
    if action == 'main':
        await _admin_menu(query)

    # ── آمار ──
    elif action == 'stats':
        s    = await db.global_stats()
        text = (
            "📊 <b>آمار سیستم</b>\n━━━━━━━━━━━━━━━━\n\n"
            f"👥 کاربران تأیید: <b>{s['users']}</b>  |  ⏳ منتظر: <b>{s['pending']}</b>\n"
            f"🆕 کاربر جدید این هفته: <b>{s.get('new_users_week', 0)}</b>\n"
            f"🎓 ادمین محتوا: <b>{s.get('content_admins', 0)}</b>\n\n"
            f"🔬 <b>علوم پایه:</b>\n"
            f"  📖 درس: <b>{s.get('bs_lessons', 0)}</b>  "
            f"📌 جلسه: <b>{s.get('bs_sessions', 0)}</b>  "
            f"📁 فایل: <b>{s.get('bs_content', 0)}</b>\n\n"
            f"📚 <b>رفرنس‌ها:</b>\n"
            f"  📖 درس: <b>{s.get('ref_subjects', 0)}</b>  "
            f"📘 کتاب: <b>{s.get('ref_books', 0)}</b>\n\n"
            f"🧪 بانک سوال: <b>{s['questions']}</b>  "
            f"📁 فایل: <b>{s.get('qbank_files', 0)}</b>\n"
            f"🎫 تیکت‌های باز: <b>{s.get('open_tickets', 0)}</b>"
        )
        await query.edit_message_text(text, parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 بروزرسانی", callback_data='admin:stats')],
                [InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')],
            ]))

    # ── لیست کاربران با pagination ──
    elif action == 'users':
        page = int(parts[2]) if len(parts) > 2 else 0
        await _show_users_list(query, page)

    # ── جزئیات کاربر ──
    elif action == 'user_detail':
        target_uid = int(parts[2])
        await _show_user_detail(query, context, target_uid)

    # ── ویرایش کاربر ──
    elif action in ('edit_name', 'edit_group', 'edit_sid'):
        target_uid = int(parts[2])
        field_map  = {
            'edit_name':  ('name', 'نام'),
            'edit_group': ('group', 'گروه'),
            'edit_sid':   ('student_id', 'شماره دانشجویی'),
        }
        field, label = field_map[action]
        context.user_data['edit_user'] = {
            'uid':   target_uid,
            'field': field,
            'label': label,
        }
        context.user_data['mode'] = 'edit_user'
        await query.edit_message_text(
            f"✏️ <b>ویرایش {label}</b>\n\nمقدار جدید را وارد کنید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data=f'admin:user_detail:{target_uid}')
            ]])
        )

    # ── تعلیق ──
    elif action == 'suspend':
        target_uid = int(parts[2])
        await db.update_user(target_uid, {'approved': False})
        await safe_send(context.bot, target_uid, "⚠️ دسترسی شما موقتاً تعلیق شد.")
        await query.answer("🚫 تعلیق شد!", show_alert=True)
        await _show_users_list(query, 0)

    # ── تأیید/رد کاربر ──
    elif action == 'approve':
        target_uid = int(parts[2])
        await db.update_user(target_uid, {'approved': True})
        user = await db.get_user(target_uid)
        kb   = get_keyboard_for_uid(user, target_uid)
        await safe_send(
            context.bot, target_uid,
            "✅ <b>دسترسی شما تأیید شد!</b>\nمی‌توانید از ربات استفاده کنید.",
            parse_mode='HTML', reply_markup=kb
        )
        await query.answer("✅ تأیید شد!", show_alert=True)
        await _show_pending(query)

    elif action == 'reject':
        target_uid = int(parts[2])
        await db.delete_user(target_uid)
        await safe_send(context.bot, target_uid, "❌ درخواست شما رد شد.")
        await query.answer("❌ رد شد.", show_alert=True)
        await _show_pending(query)

    # ── حذف کاربر ──
    elif action == 'confirm_delete_user':
        target_uid = int(parts[2])
        user       = await db.get_user(target_uid)
        name       = user.get('name', '') if user else ''
        await query.edit_message_text(
            f"⚠️ <b>حذف کاربر</b>\n\nمطمئنی می‌خواهی <b>{name}</b> را حذف کنی؟",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⚠️ بله، حذف",  callback_data=f'admin:delete_user:{target_uid}'),
                    InlineKeyboardButton("❌ لغو",         callback_data=f'admin:user_detail:{target_uid}'),
                ]
            ])
        )

    elif action == 'delete_user':
        target_uid = int(parts[2])
        user       = await db.get_user(target_uid)
        name       = user.get('name', '') if user else ''
        await db.delete_user(target_uid)
        await safe_send(context.bot, target_uid, "❌ حساب شما حذف شد.")
        await query.answer(f"🗑 {name} حذف شد!", show_alert=True)
        await _show_users_list(query, 0)

    # ── تأیید کاربران منتظر ──
    elif action == 'pending':
        await _show_pending(query)

    # ── جستجوی کاربر — FIX: mode صحیح ──
    elif action == 'search_user':
        context.user_data['mode']            = 'search_user'
        context.user_data['awaiting_search'] = False   # غیرفعال کردن resource search
        await query.edit_message_text(
            "🔍 <b>جستجوی کاربر</b>\n\n"
            "نام، شماره دانشجویی یا یوزرنیم را وارد کنید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='admin:main')
            ]])
        )

    # ── ادمین محتوا ──
    elif action == 'intakes':
        await _show_intakes(query)

    elif action == 'intake_add':
        context.user_data['mode'] = 'add_intake'
        await query.edit_message_text(
            "📅 <b>افزودن ورودی جدید</b>\n\n"
            "فرمت: <code>کد, برچسب</code>\n"
            "مثال: <code>bahman_1404, بهمن ۱۴۰۴</code>\n\n"
            "کد باید انگلیسی و بدون فاصله باشد.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='admin:intakes')
            ]])
        )

    elif action == 'intake_toggle':
        code = parts[2]
        new_state = await db.toggle_intake(code)
        state_txt = "✅ فعال" if new_state else "❌ غیرفعال"
        await query.answer(f"ورودی {state_txt} شد", show_alert=True)
        await _show_intakes(query)

    elif action == 'intake_del':
        code = parts[2]
        await db.delete_intake(code)
        await query.answer("🗑 ورودی حذف شد!", show_alert=True)
        await _show_intakes(query)

    elif action == 'intake_view':
        code   = parts[2]
        stats  = await db.intake_stats(code)
        intakes = await db.get_all_intakes()
        intake  = next((i for i in intakes if i['code'] == code), {})
        label   = intake.get('label', code)
        groups  = stats.get('groups', {})
        g_text  = '\n'.join(f"  گروه {g}: {c} نفر" for g, c in groups.items()) or "  داده‌ای نیست"
        await query.edit_message_text(
            f"📅 <b>ورودی: {label}</b>\n"
            f"🔑 کد: <code>{code}</code>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👥 مجموع دانشجو: <b>{stats['total']}</b>\n\n"
            f"<b>تفکیک گروه:</b>\n{g_text}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت به ورودی‌ها", callback_data='admin:intakes')]
            ])
        )

    elif action == 'content_admins':
        admins   = await db.get_content_admins()
        keyboard = []
        for a in admins:
            aid  = a['user_id']
            name = a.get('name', '')
            keyboard.append([
                InlineKeyboardButton(f"🎓 {name}", callback_data=f'admin:user_detail:{aid}'),
                InlineKeyboardButton("🗑 لغو",      callback_data=f'admin:ca_remove:{aid}'),
            ])
        keyboard.append([InlineKeyboardButton("➕ دادن دسترسی", callback_data='admin:ca_grant')])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت",       callback_data='admin:main')])
        await query.edit_message_text(
            f"🎓 <b>ادمین‌های محتوا</b> — {len(admins)} نفر",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'ca_grant':
        users    = await db.all_users(approved_only=True)
        students = [u for u in users if u.get('role', 'student') == 'student'][:20]
        keyboard = [
            [InlineKeyboardButton(
                f"👤 {u.get('name', '')} | گروه {u.get('group', '')}",
                callback_data=f'admin:ca_set:{u["user_id"]}'
            )]
            for u in students
        ]
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:content_admins')])
        await query.edit_message_text(
            "➕ کاربر مورد نظر را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'ca_set':
        target_uid = int(parts[2])
        await db.update_user(target_uid, {'role': 'content_admin'})
        await safe_send(
            context.bot, target_uid,
            "🎓 <b>دسترسی ادمین محتوا به شما داده شد!</b>\n"
            "دکمه 🎓 پنل محتوا در کیبورد شما ظاهر می‌شود.",
            parse_mode='HTML', reply_markup=content_admin_keyboard()
        )
        await query.answer("✅ دسترسی داده شد!", show_alert=True)
        await _admin_menu(query)

    elif action == 'ca_remove':
        target_uid = int(parts[2])
        await db.update_user(target_uid, {'role': 'student'})
        await safe_send(
            context.bot, target_uid,
            "⚠️ دسترسی ادمین محتوای شما لغو شد.",
            reply_markup=main_keyboard()
        )
        await query.answer("↩️ دسترسی لغو شد!", show_alert=True)
        await _admin_menu(query)

    # ── بانک سوال ──
    elif action == 'qbank_manage':
        keyboard = [
            [InlineKeyboardButton("📁 مشاهده فایل‌ها",  callback_data='admin:qbank_list')],
            [InlineKeyboardButton("📤 آپلود فایل جدید", callback_data='admin:qbank_upload')],
            [InlineKeyboardButton("🔙 بازگشت به پنل",   callback_data='admin:main')],
        ]
        await query.edit_message_text(
            "🧪 <b>مدیریت بانک سوال</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'qbank_upload':
        lessons = await db.get_lessons()
        if not lessons:
            await query.edit_message_text(
                "❌ هنوز درسی تعریف نشده.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت", callback_data='admin:qbank_manage')
                ]])
            )
            return
        context.user_data['_lessons'] = lessons
        keyboard = [
            [InlineKeyboardButton(l, callback_data=f'admin:qbank_lesson:{i}')]
            for i, l in enumerate(lessons)
        ]
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:qbank_manage')])
        await query.edit_message_text(
            "📤 <b>آپلود بانک سوال</b>\n\nدرس را انتخاب کنید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == 'qbank_lesson':
        idx     = int(parts[2])
        lessons = context.user_data.get('_lessons', [])
        if idx < len(lessons):
            lesson = lessons[idx]
            context.user_data['qbank_lesson'] = lesson
            topics = await db.get_topics(lesson)
            context.user_data['_topics'] = topics
            keyboard = [
                [InlineKeyboardButton(t, callback_data=f'admin:qbank_topic:{i}')]
                for i, t in enumerate(topics)
            ]
            keyboard.append([InlineKeyboardButton("📂 همه مباحث", callback_data='admin:qbank_topic:all')])
            keyboard.append([InlineKeyboardButton("🔙 بازگشت",    callback_data='admin:qbank_upload')])
            await query.edit_message_text(
                f"📚 {lesson}\n\nمبحث را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    elif action == 'qbank_topic':
        topics = context.user_data.get('_topics', [])
        topic  = '' if parts[2] == 'all' else (
            topics[int(parts[2])] if int(parts[2]) < len(topics) else ''
        )
        context.user_data['qbank_topic'] = topic
        context.user_data['mode']        = 'qbank_awaiting_file'
        await query.edit_message_text(
            "📤 فایل PDF یا عکس بانک سوال را ارسال کنید:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='admin:qbank_manage')
            ]])
        )

    elif action == 'qbank_list':
        await _show_qbank_list(query)

    elif action == 'qbank_del':
        fid = parts[2]
        await db.delete_qbank_file(fid)
        await query.answer("🗑 حذف شد!", show_alert=True)
        await _show_qbank_list(query)

    # ── سوالات در انتظار ──
    elif action == 'pending_q':
        await _pending_questions(query)

    elif action == 'approve_q':
        await db.approve_question(parts[2])
        await query.answer("✅ تأیید شد!")
        await _pending_questions(query)

    elif action == 'reject_q':
        await db.delete_question(parts[2])
        await query.answer("🗑 رد شد!")
        await _pending_questions(query)

    # ── ارسال همگانی ──
    elif action == 'broadcast':
        context.user_data['mode'] = 'broadcast'
        await query.edit_message_text(
            "📢 <b>ارسال همگانی</b>\n\n"
            "پیام خود را بنویسید (متن، عکس، فیلم):",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ لغو", callback_data='admin:main')
            ]])
        )
        return BROADCAST


# ══════════════════════════════════════════════════
#  توابع نمایش
# ══════════════════════════════════════════════════

async def _show_users_list(query, page: int = 0):
    all_users  = await db.all_users(approved_only=False)
    per_page   = 8
    total      = len(all_users)
    approved   = sum(1 for u in all_users if u.get('approved'))
    start      = page * per_page
    chunk      = all_users[start:start + per_page]

    text = (
        f"👥 <b>کاربران</b>\n"
        f"✅ تأیید: {approved} | ⏳ منتظر: {total - approved} | مجموع: {total}\n\n"
    )
    keyboard = []
    for u in chunk:
        icon  = "✅" if u.get('approved') else "⏳"
        role  = "🎓" if u.get('role') == 'content_admin' else ""
        label = (
            f"{icon}{role} {u.get('name', '')[:12]} | "
            f"{u.get('student_id', '') or u.get('username', '') or str(u['user_id'])[:6]} | "
            f"گروه {u.get('group', '')}"
        )
        keyboard.append([InlineKeyboardButton(
            label, callback_data=f'admin:user_detail:{u["user_id"]}'
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f'admin:users:{page - 1}'))
    if start + per_page < total:
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f'admin:users:{page + 1}'))
    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("🔍 جستجو",      callback_data='admin:search_user')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')])
    await query.edit_message_text(
        text, parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_user_detail(query, context, target_uid: int):
    user  = await db.get_user(target_uid)
    if not user:
        await query.answer("کاربر پیدا نشد!", show_alert=True)
        return
    stats   = await db.user_stats(target_uid)
    status  = "✅ تأیید شده" if user.get('approved') else "⏳ در انتظار"
    role_m  = {'student': '🧑‍🎓 دانشجو', 'content_admin': '🎓 ادمین محتوا'}
    role_t  = role_m.get(user.get('role', 'student'), user.get('role', ''))
    uname   = f"@{user['username']}" if user.get('username') else 'ندارد'
    tickets = await db.ticket_get_user(target_uid)
    open_t  = sum(1 for t in tickets if t['status'] == 'open')

    text = (
        f"👤 <b>پروفایل کاربر</b>\n━━━━━━━━━━━━━━━━\n\n"
        f"📛 نام: <b>{user.get('name', '')}</b>\n"
        f"🎓 شماره: <code>{user.get('student_id', '') or '—'}</code>\n"
        f"👥 گروه: <b>{user.get('group', '')}</b>\n"
        f"📱 یوزرنیم: {uname}\n"
        f"🆔 آیدی: <code>{target_uid}</code>\n"
        f"🔘 وضعیت: {status}  |  نقش: {role_t}\n"
        f"📅 ثبت‌نام: {user.get('registered_at', '')[:10]}\n\n"
        f"📊 <b>آمار:</b>\n"
        f"  📥 دانلود: {stats['downloads']}  "
        f"🧪 سوال: {stats['total_answers']}  "
        f"✅ صحیح: {stats['correct_answers']}\n"
        f"  📈 درصد: {stats['percentage']}%  "
        f"🔥 هفتگی: {stats['week_activity']}\n"
        f"  🎫 تیکت باز: {open_t}"
    )
    keyboard = [
        [
            InlineKeyboardButton("✏️ ویرایش نام",   callback_data=f'admin:edit_name:{target_uid}'),
            InlineKeyboardButton("✏️ ویرایش گروه",  callback_data=f'admin:edit_group:{target_uid}'),
        ],
    ]
    if user.get('role', 'student') == 'student':
        keyboard.append([InlineKeyboardButton(
            "🎓 دادن دسترسی محتوا", callback_data=f'admin:ca_set:{target_uid}'
        )])
    elif user.get('role') == 'content_admin':
        keyboard.append([InlineKeyboardButton(
            "↩️ لغو دسترسی محتوا", callback_data=f'admin:ca_remove:{target_uid}'
        )])

    if user.get('approved'):
        keyboard.append([InlineKeyboardButton(
            "🚫 تعلیق", callback_data=f'admin:suspend:{target_uid}'
        )])
    else:
        keyboard.append([
            InlineKeyboardButton("✅ تأیید", callback_data=f'admin:approve:{target_uid}'),
            InlineKeyboardButton("❌ رد",    callback_data=f'admin:reject:{target_uid}'),
        ])

    keyboard.append([InlineKeyboardButton(
        "🗑 حذف کامل", callback_data=f'admin:confirm_delete_user:{target_uid}'
    )])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به لیست", callback_data='admin:users:0')])

    await query.edit_message_text(
        text, parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_pending(query):
    pending  = await db.pending_users()
    if not pending:
        await query.edit_message_text(
            "✅ هیچ کاربر در انتظاری وجود ندارد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')
            ]])
        )
        return
    keyboard = []
    for u in pending:
        uid   = u['user_id']
        label = f"👤 {u.get('name', '')} | {u.get('student_id', '') or 'بدون شماره'} | گروه {u.get('group', '')}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f'admin:user_detail:{uid}')])
        keyboard.append([
            InlineKeyboardButton("✅ تأیید", callback_data=f'admin:approve:{uid}'),
            InlineKeyboardButton("❌ رد",    callback_data=f'admin:reject:{uid}'),
        ])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')])
    await query.edit_message_text(
        f"⏳ <b>کاربران در انتظار</b> — {len(pending)} نفر",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _pending_questions(query):
    questions = await db.pending_questions()
    if not questions:
        await query.edit_message_text(
            "✅ هیچ سوال در انتظاری وجود ندارد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')
            ]])
        )
        return
    keyboard = []
    for q in questions[:10]:
        qid   = str(q['_id'])
        label = q.get('question', '')[:40]
        keyboard.append([InlineKeyboardButton(f"❓ {label}", callback_data='admin:pending_q')])
        keyboard.append([
            InlineKeyboardButton("✅ تأیید", callback_data=f'admin:approve_q:{qid}'),
            InlineKeyboardButton("🗑 رد",    callback_data=f'admin:reject_q:{qid}'),
        ])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')])
    await query.edit_message_text(
        f"⏳ <b>سوالات در انتظار</b> — {len(questions)} سوال",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _show_qbank_list(query):
    files    = await db.get_qbank_files()
    keyboard = []
    for f in files[:15]:
        fid = str(f['_id'])
        keyboard.append([
            InlineKeyboardButton(
                f"📁 {f.get('lesson', '')} — {f.get('topic', '')[:15]}",
                callback_data='admin:qbank_list'
            ),
            InlineKeyboardButton("🗑", callback_data=f'admin:qbank_del:{fid}'),
        ])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:qbank_manage')])
    if not files:
        await query.edit_message_text(
            "❌ فایلی آپلود نشده.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.edit_message_text(
            f"📁 <b>فایل‌های بانک سوال</b> — {len(files)} فایل",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# ══════════════════════════════════════════════════
#  هندلرهای متن — FIX: search_user جداگانه چک میشه
# ══════════════════════════════════════════════════

async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    mode = context.user_data.get('mode', '')
    text = update.message.text.strip()

    # ── FIX: جستجوی کاربر با mode='search_user' ──
    if mode == 'search_user':
        users = await db.search_users(text)
        context.user_data['mode'] = ''
        if not users:
            await update.message.reply_text(
                f"❌ کاربری با «{text}» پیدا نشد.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔍 جستجوی مجدد", callback_data='admin:search_user'),
                    InlineKeyboardButton("🔙 پنل ادمین",    callback_data='admin:main'),
                ]])
            )
            return True
        keyboard = [
            [InlineKeyboardButton(
                f"{'✅' if u.get('approved') else '⏳'} "
                f"{u.get('name', '')} | {u.get('student_id', '') or u.get('username', 'N/A')}",
                callback_data=f'admin:user_detail:{u["user_id"]}'
            )]
            for u in users
        ]
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:main')])
        await update.message.reply_text(
            f"🔍 <b>{len(users)} نتیجه برای «{text}»:</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return True

    elif mode == 'edit_user':
        info  = context.user_data.get('edit_user', {})
        uid   = info.get('uid')
        field = info.get('field')
        label = info.get('label', '')
        if uid and field:
            await db.update_user(uid, {field: text})
            context.user_data['mode'] = ''
            await update.message.reply_text(
                f"✅ {label} ویرایش شد.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("👤 مشاهده کاربر", callback_data=f'admin:user_detail:{uid}')
                ]])
            )
            return True


    elif mode == 'add_intake':
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            pts = [p.strip() for p in text.split(',', 1)]
            if len(pts) < 2:
                raise ValueError("فرمت اشتباه")
            code, label = pts[0], pts[1]
            ok = await db.add_intake(code, label)
            context.user_data.pop('mode', None)
            if ok:
                await update.message.reply_text(
                    f"✅ ورودی <b>{label}</b> اضافه شد!",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📅 مدیریت ورودی‌ها", callback_data='admin:intakes')
                    ]])
                )
            else:
                await update.message.reply_text(
                    f"⚠️ ورودی با کد <code>{code}</code> قبلاً وجود دارد.", parse_mode='HTML'
                )
            return True
        except ValueError:
            await update.message.reply_text(
                "❌ فرمت اشتباه!\nمثال: <code>bahman_1404, بهمن ۱۴۰۴</code>",
                parse_mode='HTML'
            )
            return True

    return False


# ══════════════════════════════════════════════════
#  آپلود فایل بانک سوال
# ══════════════════════════════════════════════════

async def upload_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        return
    if context.user_data.get('mode') != 'qbank_awaiting_file':
        return

    doc = update.message.document or (
        update.message.photo[-1] if update.message.photo else None
    )
    if not doc:
        await update.message.reply_text("❌ فایل معتبر ارسال کنید.")
        return

    file_id   = doc.file_id
    file_type = 'photo' if update.message.photo else 'document'
    lesson    = context.user_data.get('qbank_lesson', '')
    topic     = context.user_data.get('qbank_topic', '')

    # توضیح اختیاری
    context.user_data.update({
        'qbank_file_id':   file_id,
        'qbank_file_type': file_type,
        'mode':            'qbank_awaiting_desc',
    })
    await update.message.reply_text(
        f"✅ فایل دریافت شد!\n📚 {lesson} — {topic}\n\n"
        "📝 توضیح کوتاه وارد کنید (یا <code>-</code> بزنید):",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ لغو", callback_data='admin:qbank_manage')
        ]])
    )


async def _show_intakes(query):
    """نمایش لیست ورودی‌ها در پنل ادمین"""
    intakes = await db.get_all_intakes()
    keyboard = []
    for i in intakes:
        code   = i['code']
        label  = i['label']
        active = i.get('active', True)
        icon   = "✅" if active else "❌"
        keyboard.append([
            InlineKeyboardButton(f"{icon} {label}", callback_data=f'admin:intake_view:{code}'),
            InlineKeyboardButton("🔄", callback_data=f'admin:intake_toggle:{code}'),
            InlineKeyboardButton("🗑", callback_data=f'admin:intake_del:{code}'),
        ])
    keyboard.append([InlineKeyboardButton("➕ افزودن ورودی جدید", callback_data='admin:intake_add')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل",    callback_data='admin:main')])
    await query.edit_message_text(
        "📅 <b>مدیریت ورودی‌های دانشجویی</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "✅ = فعال (نمایش در ثبت‌نام)  |  ❌ = غیرفعال\n"
        "🔄 = تغییر وضعیت  |  🗑 = حذف",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def admin_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        return
    if context.user_data.get('mode') != 'broadcast':
        return

    users  = await db.all_users(approved_only=True)
    sent   = 0
    failed = 0

    for u in users:
        try:
            if update.message.text:
                await context.bot.send_message(
                    u['user_id'], update.message.text, parse_mode='HTML'
                )
            elif update.message.photo:
                await context.bot.send_photo(
                    u['user_id'], update.message.photo[-1].file_id,
                    caption=update.message.caption or ''
                )
            elif update.message.video:
                await context.bot.send_video(
                    u['user_id'], update.message.video.file_id,
                    caption=update.message.caption or ''
                )
            elif update.message.document:
                await context.bot.send_document(
                    u['user_id'], update.message.document.file_id,
                    caption=update.message.caption or ''
                )
            sent += 1
        except Exception:
            failed += 1

    context.user_data['mode'] = ''
    await update.message.reply_text(
        f"✅ ارسال همگانی:\n"
        f"✅ موفق: {sent}\n"
        f"❌ ناموفق: {failed}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')
        ]])
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════
#  کمکی
# ══════════════════════════════════════════════════

def get_keyboard_for_uid(user, uid: int):
    if uid == ADMIN_ID:
        return admin_keyboard()
    role = user.get('role', 'student') if user else 'student'
    if role == 'content_admin':
        return content_admin_keyboard()
    return main_keyboard()

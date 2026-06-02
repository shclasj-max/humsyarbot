"""پنل ادمین — یک منوی واحد یکپارچه"""
import os, logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db
from utils import main_keyboard, content_admin_keyboard, admin_keyboard

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
BROADCAST = 5


# ══════════════════════════════════════════════════
#  منوی اصلی ادمین — تنها منو، یکپارچه
# ══════════════════════════════════════════════════
async def _admin_menu(query):
    s = await db.global_stats()
    keyboard = [
        [InlineKeyboardButton(
            f"📊 آمار سیستم  ({s['users']} کاربر | {s.get('open_tickets',0)} تیکت باز)",
            callback_data='admin:stats'
        )],
        [InlineKeyboardButton("👥 مدیریت کاربران",   callback_data='admin:users'),
         InlineKeyboardButton("⏳ تأیید کاربران",    callback_data='admin:pending')],
        [InlineKeyboardButton("🔍 جستجوی کاربر",     callback_data='admin:search_user')],
        [InlineKeyboardButton("🎓 ادمین‌های محتوا",  callback_data='admin:content_admins')],
        [InlineKeyboardButton("📘 علوم پایه",        callback_data='ca:terms_admin'),
         InlineKeyboardButton("📚 رفرنس‌ها",         callback_data='ca:refs_admin')],
        [InlineKeyboardButton("❓ مدیریت FAQ",        callback_data='ca:faq')],
        [InlineKeyboardButton("🧪 بانک سوال",        callback_data='admin:qbank_manage'),
         InlineKeyboardButton("✅ تأیید سوالات",     callback_data='admin:pending_q')],
        [InlineKeyboardButton("📅 برنامه جدید",      callback_data='admin:add_schedule'),
         InlineKeyboardButton("🗑 حذف برنامه",       callback_data='admin:del_schedule_list')],
        [InlineKeyboardButton("🎫 تیکت‌های باز",     callback_data='ticket:admin_list')],
        [InlineKeyboardButton("📢 ارسال همگانی",      callback_data='admin:broadcast')],
        [InlineKeyboardButton("💾 پشتیبان‌گیری و بازیابی", callback_data='backup:menu')],
    ]
    await query.edit_message_text(
        "👨‍⚕️ <b>پنل مدیریت</b>\n━━━━━━━━━━━━━━━━",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ══════════════════════════════════════════════════
#  callback اصلی
# ══════════════════════════════════════════════════
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    uid    = update.effective_user.id

    if uid != ADMIN_ID:
        await query.answer("❌ دسترسی ندارید!", show_alert=True); return

    await query.answer()
    data   = query.data
    parts  = data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    # ─ منوی اصلی ─
    if action == 'main':
        await _admin_menu(query)

    # ─ آمار ─
    elif action == 'stats':
        s = await db.global_stats()
        text = (
            "📊 <b>آمار سیستم</b>\n━━━━━━━━━━━━━━━━\n\n"
            f"👥 کاربران تأیید: <b>{s['users']}</b>  |  ⏳ منتظر: <b>{s['pending']}</b>\n"
            f"🆕 کاربر جدید این هفته: <b>{s.get('new_users_week',0)}</b>\n"
            f"🎓 ادمین محتوا: <b>{s.get('content_admins',0)}</b>\n\n"
            f"🔬 <b>علوم پایه:</b>\n"
            f"  📖 درس‌ها: <b>{s.get('bs_lessons',0)}</b>  "
            f"📌 جلسات: <b>{s.get('bs_sessions',0)}</b>  "
            f"📁 فایل: <b>{s.get('bs_content',0)}</b>\n\n"
            f"📚 <b>رفرنس‌ها:</b>\n"
            f"  📖 درس‌ها: <b>{s.get('ref_subjects',0)}</b>  "
            f"📘 کتاب: <b>{s.get('ref_books',0)}</b>\n\n"
            f"🧪 بانک سوال: <b>{s['questions']}</b>  "
            f"📁 فایل: <b>{s.get('qbank_files',0)}</b>\n"
            f"🎫 تیکت‌های باز: <b>{s.get('open_tickets',0)}</b>"
        )
        await query.edit_message_text(text, parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 بروزرسانی", callback_data='admin:stats')],
                [InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')]
            ]))

    # ─ لیست کاربران ─
    elif action == 'users':
        await _show_users_list(query, page=int(parts[2]) if len(parts) > 2 else 0)

    # ─ جزئیات کاربر ─
    elif action == 'user_detail':
        target_uid = int(parts[2])
        user = await db.get_user(target_uid)
        if not user:
            await query.answer("کاربر پیدا نشد!", show_alert=True); return
        stats     = await db.user_stats(target_uid)
        status    = "✅ تأیید شده" if user.get('approved') else "⏳ در انتظار"
        role_map  = {'student': '🧑‍🎓 دانشجو', 'content_admin': '🎓 ادمین محتوا', 'admin': '👑 ادمین'}
        role_txt  = role_map.get(user.get('role','student'), user.get('role',''))
        uname     = f"@{user['username']}" if user.get('username') else 'ندارد'
        tickets   = await db.ticket_get_user(target_uid)
        open_t    = sum(1 for t in tickets if t['status'] == 'open')
        text = (
            f"👤 <b>پروفایل کاربر</b>\n━━━━━━━━━━━━━━━━\n\n"
            f"📛 نام: <b>{user.get('name','')}</b>\n"
            f"🎓 شماره دانشجویی: <code>{user.get('student_id','')}</code>\n"
            f"👥 گروه: <b>{user.get('group','')}</b>\n"
            f"📱 یوزرنیم: {uname}\n"
            f"🆔 آیدی: <code>{target_uid}</code>\n"
            f"🔘 وضعیت: {status}  |  نقش: {role_txt}\n"
            f"📅 ثبت‌نام: {user.get('registered_at','')[:10]}\n\n"
            f"📊 <b>آمار فعالیت:</b>\n"
            f"  📥 دانلود: {stats['downloads']}  "
            f"🧪 سوال: {stats['total_answers']}  "
            f"✅ صحیح: {stats['correct_answers']}\n"
            f"  📈 درصد: {stats['percentage']}%  "
            f"🔥 هفتگی: {stats['week_activity']}\n"
            f"  🎫 تیکت باز: {open_t}"
        )
        keyboard = [
            [InlineKeyboardButton("✏️ ویرایش نام",    callback_data=f'admin:edit_name:{target_uid}'),
             InlineKeyboardButton("✏️ ویرایش گروه",   callback_data=f'admin:edit_group:{target_uid}')],
            [InlineKeyboardButton("✏️ ویرایش شماره",  callback_data=f'admin:edit_sid:{target_uid}')],
        ]
        if user.get('role','student') == 'student':
            keyboard.append([InlineKeyboardButton("🎓 دادن دسترسی محتوا", callback_data=f'admin:ca_set:{target_uid}')])
        elif user.get('role') == 'content_admin':
            keyboard.append([InlineKeyboardButton("↩️ لغو دسترسی محتوا",  callback_data=f'admin:ca_remove:{target_uid}')])
        if user.get('approved'):
            keyboard.append([InlineKeyboardButton("🚫 تعلیق کاربر", callback_data=f'admin:suspend:{target_uid}')])
        else:
            keyboard.append([
                InlineKeyboardButton("✅ تأیید",  callback_data=f'admin:approve:{target_uid}'),
                InlineKeyboardButton("❌ رد",     callback_data=f'admin:reject:{target_uid}')
            ])
        keyboard.append([InlineKeyboardButton("🗑 حذف کامل", callback_data=f'admin:confirm_delete_user:{target_uid}')])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت",   callback_data='admin:users')])
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # ─ ویرایش کاربر ─
    elif action in ('edit_name', 'edit_group', 'edit_sid'):
        target_uid = int(parts[2])
        field_map  = {'edit_name': ('name','نام'), 'edit_group': ('group','گروه'), 'edit_sid': ('student_id','شماره دانشجویی')}
        field, label = field_map[action]
        context.user_data['edit_user'] = {'uid': target_uid, 'field': field, 'label': label}
        context.user_data['mode']      = 'edit_user'
        await query.edit_message_text(
            f"✏️ <b>ویرایش {label}</b>\n\nمقدار جدید را وارد کنید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data=f'admin:user_detail:{target_uid}')]]))

    # ─ تعلیق ─
    elif action == 'suspend':
        target_uid = int(parts[2])
        await db.update_user(target_uid, {'approved': False})
        try: await context.bot.send_message(target_uid, "⚠️ دسترسی شما موقتاً تعلیق شد.")
        except: pass
        await query.answer("🚫 تعلیق شد!", show_alert=True)
        await _show_users_list(query, 0)

    # ─ حذف ─
    elif action == 'confirm_delete_user':
        target_uid = int(parts[2])
        user = await db.get_user(target_uid)
        name = user.get('name','') if user else ''
        await query.edit_message_text(
            f"⚠️ <b>حذف کاربر</b>\n\nمطمئنی می‌خواهی <b>{name}</b> را حذف کنی؟",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚠️ بله، حذف کن",  callback_data=f'admin:delete_user:{target_uid}')],
                [InlineKeyboardButton("❌ لغو",           callback_data=f'admin:user_detail:{target_uid}')]
            ]))

    elif action == 'delete_user':
        target_uid = int(parts[2])
        user = await db.get_user(target_uid)
        name = user.get('name','') if user else ''
        await db.delete_user(target_uid)
        try: await context.bot.send_message(target_uid, "❌ حساب شما حذف شد.")
        except: pass
        await query.answer(f"🗑 {name} حذف شد!", show_alert=True)
        await _show_users_list(query, 0)

    # ─ تأیید کاربران ─
    elif action == 'pending':
        await _show_pending(query)

    elif action == 'approve':
        target_uid = int(parts[2])
        await db.update_user(target_uid, {'approved': True})
        user = await db.get_user(target_uid)
        try:
            kb = admin_keyboard() if target_uid == ADMIN_ID else (
                content_admin_keyboard() if user and user.get('role')=='content_admin' else main_keyboard()
            )
            await context.bot.send_message(target_uid,
                "✅ <b>دسترسی شما تأیید شد!</b>\nمی‌توانید از ربات استفاده کنید.",
                parse_mode='HTML', reply_markup=kb)
        except: pass
        await query.answer("✅ تأیید شد!", show_alert=True)
        await _show_pending(query)

    elif action == 'reject':
        target_uid = int(parts[2])
        await db.delete_user(target_uid)
        try: await context.bot.send_message(target_uid, "❌ درخواست شما رد شد.")
        except: pass
        await query.answer("❌ رد شد.", show_alert=True)
        await _show_pending(query)

    # ─ جستجوی کاربر ─
    elif action == 'search_user':
        context.user_data['mode'] = 'search_user'
        await query.edit_message_text(
            "🔍 <b>جستجوی کاربر</b>\n\nنام، شماره دانشجویی یا یوزرنیم را وارد کنید:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='admin:main')]]))

    # ─ ادمین محتوا ─
    elif action == 'content_admins':
        admins = await db.get_content_admins()
        keyboard = []
        for a in admins:
            aid  = a['user_id']
            name = a.get('name','')
            keyboard.append([
                InlineKeyboardButton(f"🎓 {name}", callback_data=f'admin:user_detail:{aid}'),
                InlineKeyboardButton("🗑 لغو دسترسی", callback_data=f'admin:ca_remove:{aid}')
            ])
        keyboard.append([InlineKeyboardButton("➕ دادن دسترسی", callback_data='admin:ca_grant')])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت",       callback_data='admin:main')])
        await query.edit_message_text(
            f"🎓 <b>ادمین‌های محتوا</b> — {len(admins)} نفر",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == 'ca_grant':
        users = await db.all_users(approved_only=True)
        students = [u for u in users if u.get('role','student') == 'student'][:20]
        keyboard = []
        for u in students:
            keyboard.append([InlineKeyboardButton(
                f"👤 {u.get('name','')} | گروه {u.get('group','')}",
                callback_data=f'admin:ca_set:{u["user_id"]}'
            )])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:content_admins')])
        await query.edit_message_text("➕ کاربر مورد نظر را انتخاب کنید:",
                                       reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == 'ca_set':
        target_uid = int(parts[2])
        await db.update_user(target_uid, {'role': 'content_admin'})
        try:
            await context.bot.send_message(target_uid,
                "🎓 <b>دسترسی ادمین محتوا به شما داده شد!</b>\n"
                "حالا دکمه 🎓 پنل محتوا در کیبوردتان ظاهر می‌شود.",
                parse_mode='HTML', reply_markup=content_admin_keyboard())
        except: pass
        await query.answer("✅ دسترسی داده شد!", show_alert=True)
        await _admin_menu(query)

    elif action == 'ca_remove':
        target_uid = int(parts[2])
        await db.update_user(target_uid, {'role': 'student'})
        try:
            await context.bot.send_message(target_uid,
                "⚠️ دسترسی ادمین محتوای شما لغو شد.", reply_markup=main_keyboard())
        except: pass
        await query.answer("↩️ دسترسی لغو شد!", show_alert=True)
        await _admin_menu(query)

    # ─ بانک سوال ─
    elif action == 'qbank_manage':
        keyboard = [
            [InlineKeyboardButton("📁 مشاهده فایل‌ها",    callback_data='admin:qbank_list')],
            [InlineKeyboardButton("📤 آپلود فایل جدید",   callback_data='admin:qbank_upload')],
            [InlineKeyboardButton("🔙 بازگشت به پنل",     callback_data='admin:main')],
        ]
        await query.edit_message_text("🧪 <b>مدیریت بانک سوال</b>", parse_mode='HTML',
                                       reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == 'qbank_upload':
        lessons = await db.get_lessons()
        if not lessons:
            await query.edit_message_text(
                "❌ هنوز درسی تعریف نشده.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='admin:qbank_manage')]]))
            return
        context.user_data['_lessons'] = lessons
        keyboard = [[InlineKeyboardButton(l, callback_data=f'admin:qbank_lesson:{i}')] for i, l in enumerate(lessons)]
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:qbank_manage')])
        await query.edit_message_text("📤 <b>آپلود فایل بانک سوال</b>\n\nدرس را انتخاب کنید:",
                                       parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == 'qbank_lesson':
        idx = int(parts[2])
        lessons = context.user_data.get('_lessons', [])
        if idx < len(lessons):
            lesson = lessons[idx]
            context.user_data['qbank_lesson'] = lesson
            topics = await db.get_topics(lesson)
            context.user_data['_topics'] = topics
            keyboard = [[InlineKeyboardButton(t, callback_data=f'admin:qbank_topic:{i}')] for i, t in enumerate(topics)]
            keyboard.append([InlineKeyboardButton("📂 همه مباحث", callback_data='admin:qbank_topic:all')])
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:qbank_upload')])
            await query.edit_message_text(f"📚 {lesson}\n\nمبحث را انتخاب کنید:",
                                           reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == 'qbank_topic':
        topics  = context.user_data.get('_topics', [])
        topic   = '' if parts[2] == 'all' else (topics[int(parts[2])] if int(parts[2]) < len(topics) else '')
        context.user_data['qbank_topic'] = topic
        context.user_data['mode']        = 'qbank_upload'
        await query.edit_message_text(
            "📤 فایل PDF یا عکس بانک سوال را ارسال کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='admin:qbank_manage')]]))

    elif action == 'qbank_list':
        files = await db.get_qbank_files()
        if not files:
            await query.edit_message_text("❌ فایلی آپلود نشده.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='admin:qbank_manage')]]))
            return
        keyboard = []
        for f in files[:15]:
            fid = str(f['_id'])
            keyboard.append([
                InlineKeyboardButton(f"📁 {f.get('lesson','')} — {f.get('topic','')[:15]}", callback_data=f'admin:qbank_list'),
                InlineKeyboardButton("🗑", callback_data=f'admin:qbank_del:{fid}')
            ])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:qbank_manage')])
        await query.edit_message_text(f"📁 <b>فایل‌های بانک سوال</b> — {len(files)} فایل",
                                       parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == 'qbank_del':
        fid = parts[2]
        await db.delete_qbank_file(fid)
        await query.answer("🗑 حذف شد!", show_alert=True)
        files = await db.get_qbank_files()
        keyboard = []
        for f in files[:15]:
            fid2 = str(f['_id'])
            keyboard.append([
                InlineKeyboardButton(f"📁 {f.get('lesson','')} — {f.get('topic','')[:15]}", callback_data=f'admin:qbank_list'),
                InlineKeyboardButton("🗑", callback_data=f'admin:qbank_del:{fid2}')
            ])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:qbank_manage')])
        await query.edit_message_text(f"📁 <b>فایل‌های بانک سوال</b> — {len(files)} فایل",
                                       parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # ─ سوالات تستی ─
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

    # ─ برنامه ─
    elif action == 'add_schedule':
        keyboard = [
            [InlineKeyboardButton("📖 کلاس درسی", callback_data='admin:sched_type:class')],
            [InlineKeyboardButton("📝 امتحان",     callback_data='admin:sched_type:exam')],
            [InlineKeyboardButton("🔄 جبرانی",     callback_data='admin:sched_type:makeup')],
            [InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')],
        ]
        await query.edit_message_text("📅 <b>برنامه جدید</b>\n\nنوع رویداد را انتخاب کنید:",
                                       parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == 'sched_type':
        stype = parts[2]
        context.user_data['sched_type'] = stype
        keyboard = [
            [InlineKeyboardButton("1️⃣ گروه ۱",   callback_data=f'admin:sched_group:{stype}:1')],
            [InlineKeyboardButton("2️⃣ گروه ۲",   callback_data=f'admin:sched_group:{stype}:2')],
            [InlineKeyboardButton("👥 هر دو گروه", callback_data=f'admin:sched_group:{stype}:هر دو')],
            [InlineKeyboardButton("🔙 بازگشت",    callback_data='admin:add_schedule')],
        ]
        type_names = {'class': 'کلاس', 'exam': 'امتحان', 'makeup': 'جبرانی'}
        await query.edit_message_text(
            f"📅 <b>{type_names.get(stype,'')}</b>\n\nاین برنامه برای کدام گروه است؟",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == 'sched_group':
        stype = parts[2]
        group = parts[3]
        context.user_data['sched_group'] = group
        context.user_data['sched_type']  = stype
        if stype == 'class':
            keyboard = [
                [InlineKeyboardButton("🔁 هفتگی (هر هفته تکرار)", callback_data=f'admin:sched_freq:{stype}:{group}:weekly')],
                [InlineKeyboardButton("📅 یکبار (تاریخ مشخص)",   callback_data=f'admin:sched_freq:{stype}:{group}:once')],
                [InlineKeyboardButton("🔙 بازگشت", callback_data=f'admin:sched_type:{stype}')],
            ]
            await query.edit_message_text(
                "🔁 <b>نوع کلاس</b>\n\nاین کلاس چه نوع برنامه‌ای دارد؟",
                parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            context.user_data['sched_weekly'] = False
            await _ask_schedule_details(query, context, stype, group, is_weekly=False)

    elif action == 'sched_freq':
        stype     = parts[2]
        group     = parts[3]
        is_weekly = parts[4] == 'weekly'
        context.user_data['sched_weekly'] = is_weekly
        await _ask_schedule_details(query, context, stype, group, is_weekly)

    elif action == 'del_schedule_list':
        items = await db.get_schedules(upcoming=False)
        if not items:
            await query.edit_message_text("❌ برنامه‌ای ثبت نشده.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='admin:main')]]))
            return
        keyboard = []
        for s in items[:15]:
            sid = str(s['_id'])
            keyboard.append([
                InlineKeyboardButton(f"📅 {s.get('lesson','')} | {s.get('date','')} | گروه {s.get('group','')}", callback_data='admin:del_schedule_list'),
                InlineKeyboardButton("🗑", callback_data=f'admin:del_sched:{sid}')
            ])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='admin:main')])
        await query.edit_message_text(f"🗑 <b>حذف برنامه</b>\n{len(items)} رویداد ثبت‌شده:",
                                       parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == 'del_sched':
        sid = parts[2]
        await db.delete_schedule(sid)
        await query.answer("🗑 حذف شد!")
        await _admin_menu(query)

    # ─ ارسال همگانی ─
    elif action == 'broadcast':
        context.user_data['mode'] = 'broadcast'
        await query.edit_message_text(
            "📢 <b>ارسال همگانی</b>\n\nپیام خود را بنویسید (متن، عکس، فیلم):",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='admin:main')]]))
        return BROADCAST


# ══════════════════════════════════════════════════
#  توابع نمایش
# ══════════════════════════════════════════════════
async def _show_users_list(query, page=0):
    all_users = await db.all_users(approved_only=False)
    per_page  = 8
    start     = page * per_page
    chunk     = all_users[start:start + per_page]
    total     = len(all_users)
    approved  = sum(1 for u in all_users if u.get('approved'))

    text = (f"👥 <b>کاربران</b>\n"
            f"✅ تأیید: {approved} | ⏳ منتظر: {total-approved} | مجموع: {total}\n\n")
    keyboard = []
    for u in chunk:
        icon  = "✅" if u.get('approved') else "⏳"
        role  = "🎓" if u.get('role') == 'content_admin' else ""
        label = f"{icon}{role} {u.get('name','')[:12]} | {u.get('student_id','')} | گروه {u.get('group','')}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f'admin:user_detail:{u["user_id"]}')])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f'admin:users:{page-1}'))
    if start + per_page < total:
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f'admin:users:{page+1}'))
    if nav: keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔍 جستجو",     callback_data='admin:search_user')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')])
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_pending(query):
    pending = await db.pending_users()
    if not pending:
        await query.edit_message_text("✅ هیچ کاربر در انتظاری وجود ندارد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')]]))
        return
    keyboard = []
    for u in pending:
        uid   = u['user_id']
        label = f"👤 {u.get('name','')} | {u.get('student_id','')} | گروه {u.get('group','')}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f'admin:user_detail:{uid}')])
        keyboard.append([
            InlineKeyboardButton("✅ تأیید",  callback_data=f'admin:approve:{uid}'),
            InlineKeyboardButton("❌ رد",     callback_data=f'admin:reject:{uid}')
        ])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')])
    await query.edit_message_text(
        f"⏳ <b>کاربران در انتظار</b> — {len(pending)} نفر",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _pending_questions(query):
    questions = await db.pending_questions()
    if not questions:
        await query.edit_message_text("✅ هیچ سوال در انتظاری وجود ندارد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')]]))
        return
    keyboard = []
    for q in questions[:10]:
        qid   = str(q['_id'])
        label = q.get('question','')[:40]
        keyboard.append([InlineKeyboardButton(f"❓ {label}", callback_data=f'admin:pending_q')])
        keyboard.append([
            InlineKeyboardButton("✅ تأیید", callback_data=f'admin:approve_q:{qid}'),
            InlineKeyboardButton("🗑 رد",    callback_data=f'admin:reject_q:{qid}'),
        ])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data='admin:main')])
    await query.edit_message_text(
        f"⏳ <b>سوالات در انتظار</b> — {len(questions)} سوال",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def _ask_schedule_details(query, context, stype, group, is_weekly):
    type_names = {'class': '📖 کلاس', 'exam': '📝 امتحان', 'makeup': '🔄 جبرانی'}
    weekly_txt = "🔁 هفتگی" if is_weekly else "📅 یکبار"
    context.user_data['mode']         = 'add_schedule'
    context.user_data['sched_type']   = stype
    context.user_data['sched_group']  = group
    context.user_data['sched_weekly'] = is_weekly
    await query.edit_message_text(
        f"📅 <b>{type_names.get(stype,'')} — گروه {group} — {weekly_txt}</b>\n\n"
        "اطلاعات را به این فرمت وارد کنید:\n"
        "<code>نام درس, استاد, تاریخ(YYYY-MM-DD), ساعت(HH:MM), مکان, توضیح</code>\n\n"
        "مثال:\n"
        "<code>فیزیولوژی, دکتر احمدی, 2025-02-01, 08:00, کلاس 201, </code>\n\n"
        "<i>تاریخ به میلادی وارد کنید — در ربات شمسی نمایش داده می‌شود.</i>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='admin:add_schedule')]]))


# ══════════════════════════════════════════════════
#  هندلرهای متن
# ══════════════════════════════════════════════════
async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    mode = context.user_data.get('mode', '')
    text = update.message.text.strip()

    if mode == 'edit_user':
        info  = context.user_data.get('edit_user', {})
        uid   = info.get('uid')
        field = info.get('field')
        label = info.get('label','')
        if uid and field:
            await db.update_user(uid, {field: text})
            context.user_data['mode'] = ''
            await update.message.reply_text(f"✅ {label} ویرایش شد.")
            return True

    elif mode == 'search_user':
        users = await db.search_users(text)
        if not users:
            await update.message.reply_text("❌ کاربری یافت نشد.")
            return True
        keyboard = []
        for u in users:
            icon = "✅" if u.get('approved') else "⏳"
            keyboard.append([InlineKeyboardButton(
                f"{icon} {u.get('name','')} | {u.get('student_id','')}",
                callback_data=f'admin:user_detail:{u["user_id"]}'
            )])
        context.user_data['mode'] = ''
        await update.message.reply_text(
            f"🔍 {len(users)} نتیجه:",
            reply_markup=InlineKeyboardMarkup(keyboard))
        return True

    elif mode == 'add_schedule':
        parts_list = [p.strip() for p in text.split(',')]
        if len(parts_list) < 5:
            await update.message.reply_text("❌ فرمت اشتباه. دقیقاً ۶ بخش با کاما جدا کنید.")
            return True
        lesson   = parts_list[0]
        teacher  = parts_list[1]
        date     = parts_list[2]
        time_s   = parts_list[3]
        location = parts_list[4]
        notes    = parts_list[5] if len(parts_list) > 5 else ''
        stype    = context.user_data.get('sched_type', 'class')
        group    = context.user_data.get('sched_group', 'هر دو')
        is_w     = context.user_data.get('sched_weekly', False)
        await db.add_schedule(stype, lesson, teacher, date, time_s, location, notes, group=group, is_weekly=is_w)
        context.user_data['mode'] = ''
        # اطلاع به دانشجویان
        users = await db.notif_users('schedule')
        for u in users:
            if u.get('group','') in (group, '') or group == 'هر دو':
                try:
                    await context.bot.send_message(u['user_id'],
                        f"📅 <b>برنامه جدید</b>\n📖 {lesson}\n👨‍🏫 {teacher}\n📅 {date} ساعت {time_s}\n📍 {location}",
                        parse_mode='HTML')
                except: pass
        await update.message.reply_text(f"✅ برنامه ثبت شد و اطلاع‌رسانی انجام شد.")
        return True

    elif mode == 'qbank_upload':
        context.user_data['qbank_description'] = text
        context.user_data['mode']              = 'qbank_awaiting_file'
        await update.message.reply_text("📤 حالا فایل PDF یا عکس را ارسال کنید:")
        return True

    return False


async def upload_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آپلود فایل بانک سوال توسط ادمین اصلی"""
    uid = update.effective_user.id
    if uid != ADMIN_ID: return
    if context.user_data.get('mode') != 'qbank_awaiting_file': return

    doc = update.message.document or update.message.photo
    if not doc:
        await update.message.reply_text("❌ فایل معتبر ارسال کنید.")
        return

    if update.message.document:
        file_id   = update.message.document.file_id
        file_type = 'document'
    else:
        file_id   = update.message.photo[-1].file_id
        file_type = 'photo'

    lesson      = context.user_data.get('qbank_lesson', '')
    topic       = context.user_data.get('qbank_topic', '')
    description = context.user_data.get('qbank_description', '')

    await db.add_qbank_file(lesson, topic, file_id, description, file_type)
    context.user_data['mode'] = ''
    await update.message.reply_text(f"✅ فایل بانک سوال آپلود شد!\n📚 {lesson} — {topic}")


async def admin_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    if uid != ADMIN_ID: return
    if context.user_data.get('mode') != 'broadcast': return

    users  = await db.all_users(approved_only=True)
    sent   = 0
    failed = 0
    for u in users:
        try:
            if update.message.text:
                await context.bot.send_message(u['user_id'], update.message.text, parse_mode='HTML')
            elif update.message.photo:
                await context.bot.send_photo(u['user_id'], update.message.photo[-1].file_id,
                                              caption=update.message.caption or '')
            elif update.message.video:
                await context.bot.send_video(u['user_id'], update.message.video.file_id,
                                              caption=update.message.caption or '')
            elif update.message.document:
                await context.bot.send_document(u['user_id'], update.message.document.file_id,
                                                 caption=update.message.caption or '')
            sent += 1
        except:
            failed += 1

    context.user_data['mode'] = ''
    await update.message.reply_text(f"✅ ارسال همگانی:\n✅ موفق: {sent}\n❌ ناموفق: {failed}")
    return ConversationHandler.END

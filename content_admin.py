"""
پنل ادمین محتوا — نسخه نهایی با:
  ✅ ترتیب‌بندی درس‌ها (بالا/پایین)
  ✅ ترتیب‌بندی فایل‌های جلسه
  ✅ چند جلد برای رفرنس
  ✅ توضیحات اضافه (اختیاری) برای فایل
  ✅ لغو با /cancel در هر مرحله
  ✅ ویرایش و حذف همه موارد
"""
import os, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

TERMS = ['ترم ۱', 'ترم ۲', 'ترم ۳', 'ترم ۴', 'ترم ۵']
CONTENT_TYPES = [
    ('video', '🎥 ویدیو کلاس'),
    ('ppt',   '📊 پاورپوینت'),
    ('pdf',   '📄 جزوه PDF'),
    ('note',  '📝 نکات'),
    ('test',  '🧪 تست'),
    ('voice', '🎙 ویس استاد'),
]

CA_WAITING_FILE = 50
CA_WAITING_TEXT = 51


def _clear(context):
    for k in ['ca_mode','ca_pending_file','ca_content_type',
              'ca_edit_target','ca_edit_field','ca_ref_lang','ca_ref_volume']:
        context.user_data.pop(k, None)


def _back_btn(label, cb):
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=cb)]])


# ══════════════════════════════════════════════════════════
#  Callback اصلی
# ══════════════════════════════════════════════════════════
async def content_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    uid    = update.effective_user.id
    data   = query.data
    parts  = data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    if not await db.is_content_admin(uid):
        await query.answer("❌ دسترسی ندارید!", show_alert=True); return

    KEEP_MODE = ('sel_ctype','upload_ref','add_lesson_prompt','add_session_prompt',
                 'add_ref_subject_prompt','add_ref_book_prompt','add_faq_prompt',
                 'upload_ref_volume_prompt','upload_content',
                 'edit_lesson_prompt','edit_session_prompt',
                 'edit_ref_subject_prompt','edit_ref_book_prompt')
    if action not in KEEP_MODE:
        _clear(context)

    from_admin = action.endswith('_admin')
    back_main  = 'admin:main' if from_admin else 'ca:main'

    # ════ منوی اصلی ════
    if action == 'main':
        await _show_main(query)

    # ══════════ علوم پایه ══════════

    elif action in ('terms','terms_admin'):
        context.user_data['ca_from_admin'] = from_admin
        await _show_terms(query, back=back_main)

    elif action == 'term':
        idx = int(parts[2])
        context.user_data.update({'ca_term': TERMS[idx], 'ca_term_idx': idx})
        fa  = context.user_data.get('ca_from_admin', False)
        await _show_lessons(query, context, TERMS[idx],
                            back='ca:terms_admin' if fa else 'ca:terms')

    # ─ افزودن درس ─
    elif action == 'add_lesson_prompt':
        idx  = int(parts[2]); term = TERMS[idx]
        context.user_data.update({'ca_term_idx': idx, 'ca_term': term, 'ca_mode': 'add_lesson'})
        await query.edit_message_text(
            f"➕ <b>درس جدید — {term}</b>\n\n"
            "فرمت: <code>نام درس, نام استاد</code>\n"
            "مثال: <code>فیزیولوژی, دکتر احمدی</code>\n"
            "<i>استاد اختیاری</i>\n\n⌨️ /cancel برای لغو",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:term:{idx}'))

    # ─ ترتیب درس‌ها ─
    elif action == 'lesson_up':
        lid = parts[2]; idx = context.user_data.get('ca_term_idx', 0)
        await db.reorder_up('bs_lessons', lid, {'term': TERMS[idx]})
        fa = context.user_data.get('ca_from_admin', False)
        await _show_lessons(query, context, TERMS[idx],
                            back='ca:terms_admin' if fa else 'ca:terms')

    elif action == 'lesson_down':
        lid = parts[2]; idx = context.user_data.get('ca_term_idx', 0)
        await db.reorder_down('bs_lessons', lid, {'term': TERMS[idx]})
        fa = context.user_data.get('ca_from_admin', False)
        await _show_lessons(query, context, TERMS[idx],
                            back='ca:terms_admin' if fa else 'ca:terms')

    # ─ ویرایش درس ─
    elif action == 'edit_lesson_menu':
        lid = parts[2]; lesson = await db.bs_get_lesson(lid)
        if not lesson: return
        kb = [
            [InlineKeyboardButton("✏️ ویرایش نام درس",   callback_data=f'ca:edit_lesson_prompt:{lid}:name')],
            [InlineKeyboardButton("✏️ ویرایش نام استاد", callback_data=f'ca:edit_lesson_prompt:{lid}:teacher')],
            [InlineKeyboardButton("🔙 بازگشت",            callback_data=f'ca:lesson:{lid}')],
        ]
        await query.edit_message_text(
            f"✏️ <b>ویرایش درس «{lesson['name']}»</b>",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

    elif action == 'edit_lesson_prompt':
        lid = parts[2]; field = parts[3]
        lesson = await db.bs_get_lesson(lid)
        if not lesson: return
        label = 'نام درس' if field == 'name' else 'نام استاد'
        context.user_data.update({'ca_mode':'edit_lesson','ca_edit_target':lid,'ca_edit_field':field})
        await query.edit_message_text(
            f"✏️ <b>ویرایش {label}</b>\n\nفعلی: <b>{lesson.get(field,'')}</b>\n\nجدید بنویسید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:lesson:{lid}'))

    # ─ حذف درس ─
    elif action == 'del_lesson':
        lid = parts[2]; lesson = await db.bs_get_lesson(lid)
        if not lesson: return
        idx = context.user_data.get('ca_term_idx', 0)
        await query.edit_message_text(
            f"⚠️ <b>حذف درس «{lesson['name']}»؟</b>\nتمام جلسات و محتوا حذف می‌شود!",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 بله", callback_data=f'ca:confirm_del_lesson:{lid}')],
                [InlineKeyboardButton("❌ لغو", callback_data=f'ca:term:{idx}')],
            ]))

    elif action == 'confirm_del_lesson':
        lid = parts[2]; lesson = await db.bs_get_lesson(lid)
        name = lesson['name'] if lesson else ''
        await db.bs_delete_lesson(lid)
        idx = context.user_data.get('ca_term_idx', 0)
        await query.edit_message_text(f"✅ درس «{name}» حذف شد.",
            reply_markup=_back_btn("🔙 بازگشت", f'ca:term:{idx}'))

    # ─ جلسات ─
    elif action == 'lesson':
        lid = parts[2]; context.user_data['ca_lesson_id'] = lid
        await _show_sessions(query, context, lid)

    elif action == 'add_session_prompt':
        lid = parts[2]
        context.user_data.update({'ca_lesson_id': lid, 'ca_mode': 'add_session'})
        sessions = await db.bs_get_sessions(lid); next_n = len(sessions) + 1
        lesson   = await db.bs_get_lesson(lid)
        await query.edit_message_text(
            f"➕ <b>جلسه جدید — {lesson.get('name','') if lesson else ''}</b>\n\n"
            f"فرمت: <code>شماره, موضوع, استاد</code>\n"
            f"مثال: <code>{next_n}, فیزیولوژی کلیه, دکتر احمدی</code>\n"
            f"<i>شماره پیشنهادی: {next_n} — استاد اختیاری</i>\n\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:lesson:{lid}'))

    elif action == 'edit_session_menu':
        sid = parts[2]; session = await db.bs_get_session(sid)
        if not session: return
        kb = [
            [InlineKeyboardButton("✏️ موضوع",      callback_data=f'ca:edit_session_prompt:{sid}:topic')],
            [InlineKeyboardButton("✏️ نام استاد",  callback_data=f'ca:edit_session_prompt:{sid}:teacher')],
            [InlineKeyboardButton("✏️ شماره جلسه", callback_data=f'ca:edit_session_prompt:{sid}:number')],
            [InlineKeyboardButton("🔙 بازگشت",     callback_data=f'ca:session:{sid}')],
        ]
        await query.edit_message_text(
            f"✏️ <b>ویرایش جلسه {session.get('number','')} — {session.get('topic','')}</b>",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

    elif action == 'edit_session_prompt':
        sid = parts[2]; field = parts[3]; session = await db.bs_get_session(sid)
        if not session: return
        labels = {'topic':'موضوع','teacher':'نام استاد','number':'شماره جلسه'}
        context.user_data.update({'ca_mode':'edit_session','ca_edit_target':sid,'ca_edit_field':field})
        await query.edit_message_text(
            f"✏️ <b>ویرایش {labels.get(field,'')}</b>\n\nفعلی: <b>{session.get(field,'')}</b>\n\nجدید بنویسید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:session:{sid}'))

    elif action == 'del_session':
        sid = parts[2]; session = await db.bs_get_session(sid)
        if not session: return
        lid = context.user_data.get('ca_lesson_id','')
        await query.edit_message_text(
            f"⚠️ <b>حذف جلسه {session.get('number','')} — {session.get('topic','')}؟</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 بله", callback_data=f'ca:confirm_del_session:{sid}')],
                [InlineKeyboardButton("❌ لغو", callback_data=f'ca:lesson:{lid}')],
            ]))

    elif action == 'confirm_del_session':
        sid = parts[2]; await db.bs_delete_session(sid)
        lid = context.user_data.get('ca_lesson_id','')
        await query.edit_message_text("✅ جلسه حذف شد.",
            reply_markup=_back_btn("🔙 بازگشت", f'ca:lesson:{lid}'))

    # ─ محتوای جلسه ─
    elif action == 'session':
        sid = parts[2]; context.user_data['ca_session_id'] = sid
        await _show_session_content(query, context, sid)

    elif action == 'upload_content':
        sid = parts[2]; context.user_data['ca_session_id'] = sid
        kb = [[InlineKeyboardButton(label, callback_data=f'ca:sel_ctype:{sid}:{ct}')]
              for ct, label in CONTENT_TYPES]
        kb.append([InlineKeyboardButton("❌ لغو", callback_data=f'ca:session:{sid}')])
        await query.edit_message_text("📤 <b>نوع محتوا:</b>",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

    elif action == 'sel_ctype':
        sid = parts[2]; ctype = parts[3]
        context.user_data.update({'ca_session_id':sid,'ca_content_type':ctype,'ca_mode':'waiting_file'})
        tl = dict(CONTENT_TYPES).get(ctype, ctype)
        await query.edit_message_text(
            f"📤 <b>آپلود {tl}</b>\n\nفایل را ارسال کنید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:session:{sid}'))
        return CA_WAITING_FILE

    # ─ ترتیب فایل‌های جلسه ─
    elif action == 'content_up':
        cid = parts[2]; sid = context.user_data.get('ca_session_id','')
        await db.reorder_content_up(cid, sid)
        await _show_session_content(query, context, sid)

    elif action == 'content_down':
        cid = parts[2]; sid = context.user_data.get('ca_session_id','')
        await db.reorder_content_down(cid, sid)
        await _show_session_content(query, context, sid)

    # ─ حذف محتوا ─
    elif action == 'del_content':
        cid = parts[2]; item = await db.bs_get_content_item(cid)
        if not item: return
        sid = context.user_data.get('ca_session_id','')
        tl  = dict(CONTENT_TYPES).get(item.get('type',''),'فایل')
        await query.edit_message_text(
            f"⚠️ <b>حذف {tl}؟</b>\n{item.get('description','')[:40]}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 حذف", callback_data=f'ca:confirm_del_content:{cid}')],
                [InlineKeyboardButton("❌ لغو", callback_data=f'ca:session:{sid}')],
            ]))

    elif action == 'confirm_del_content':
        cid = parts[2]; await db.bs_delete_content(cid)
        sid = context.user_data.get('ca_session_id','')
        await query.edit_message_text("✅ محتوا حذف شد.",
            reply_markup=_back_btn("🔙 بازگشت", f'ca:session:{sid}'))

    # ══════════ رفرنس‌ها ══════════

    elif action in ('refs','refs_admin'):
        context.user_data['ca_ref_from_admin'] = from_admin
        await _show_ref_subjects(query, back=back_main)

    # ─ ترتیب درس‌های رفرنس ─
    elif action == 'ref_subject_up':
        sid = parts[2]
        await db.reorder_up('ref_subjects', sid, {})
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await _show_ref_subjects(query, back=back)

    elif action == 'ref_subject_down':
        sid = parts[2]
        await db.reorder_down('ref_subjects', sid, {})
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await _show_ref_subjects(query, back=back)

    elif action == 'add_ref_subject_prompt':
        context.user_data['ca_mode'] = 'add_ref_subject'
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await query.edit_message_text(
            "➕ <b>درس جدید</b>\n\nنام درس را بنویسید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", back))

    elif action == 'edit_ref_subject_prompt':
        sid = parts[2]; subj = await db.ref_get_subject(sid)
        if not subj: return
        context.user_data.update({'ca_mode':'edit_ref_subject','ca_edit_target':sid})
        await query.edit_message_text(
            f"✏️ <b>ویرایش نام درس</b>\n\nفعلی: <b>{subj['name']}</b>\n\nجدید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_subject:{sid}'))

    elif action == 'del_ref_subject':
        sid = parts[2]; subj = await db.ref_get_subject(sid)
        if not subj: return
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await query.edit_message_text(
            f"⚠️ <b>حذف درس «{subj['name']}»؟</b>\nتمام کتاب‌ها و فایل‌ها حذف می‌شوند!",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 بله", callback_data=f'ca:confirm_del_ref_subject:{sid}')],
                [InlineKeyboardButton("❌ لغو", callback_data=back)],
            ]))

    elif action == 'confirm_del_ref_subject':
        sid = parts[2]; await db.ref_delete_subject(sid)
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await query.edit_message_text("✅ درس حذف شد.", reply_markup=_back_btn("🔙 بازگشت", back))

    elif action == 'ref_subject':
        sid = parts[2]; context.user_data['ca_ref_subject_id'] = sid
        fa  = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await _show_ref_books(query, context, sid, back=back)

    # ─ ترتیب کتاب‌های رفرنس ─
    elif action == 'ref_book_up':
        bid = parts[2]; sid = context.user_data.get('ca_ref_subject_id','')
        await db.reorder_up('ref_books', bid, {'subject_id': sid})
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await _show_ref_books(query, context, sid, back=back)

    elif action == 'ref_book_down':
        bid = parts[2]; sid = context.user_data.get('ca_ref_subject_id','')
        await db.reorder_down('ref_books', bid, {'subject_id': sid})
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        await _show_ref_books(query, context, sid, back=back)

    elif action == 'add_ref_book_prompt':
        sid = parts[2]
        context.user_data.update({'ca_ref_subject_id': sid, 'ca_mode': 'add_ref_book'})
        await query.edit_message_text(
            "➕ <b>کتاب جدید</b>\n\nنام کتاب را بنویسید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_subject:{sid}'))

    elif action == 'edit_ref_book_prompt':
        bid = parts[2]; book = await db.ref_get_book(bid)
        if not book: return
        context.user_data.update({'ca_mode':'edit_ref_book','ca_edit_target':bid})
        await query.edit_message_text(
            f"✏️ <b>ویرایش نام کتاب</b>\n\nفعلی: <b>{book['name']}</b>\n\nجدید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_book:{bid}'))

    elif action == 'del_ref_book':
        bid = parts[2]; book = await db.ref_get_book(bid)
        if not book: return
        sid = context.user_data.get('ca_ref_subject_id','')
        await query.edit_message_text(
            f"⚠️ <b>حذف رفرنس «{book['name']}»؟</b>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 حذف", callback_data=f'ca:confirm_del_ref_book:{bid}')],
                [InlineKeyboardButton("❌ لغو", callback_data=f'ca:ref_subject:{sid}')],
            ]))

    elif action == 'confirm_del_ref_book':
        bid = parts[2]; await db.ref_delete_book(bid)
        sid = context.user_data.get('ca_ref_subject_id','')
        await query.edit_message_text("✅ رفرنس حذف شد.",
            reply_markup=_back_btn("🔙 بازگشت", f'ca:ref_subject:{sid}'))

    elif action == 'ref_book':
        bid = parts[2]; context.user_data['ca_ref_book_id'] = bid
        await _show_ref_book_files(query, context, bid)

    # ─ آپلود جلد رفرنس ─
    elif action == 'upload_ref_volume_prompt':
        bid  = parts[2]; lang = parts[3]
        files = await db.ref_get_files(bid)
        existing_vols = [f.get('volume', 1) for f in files if f.get('lang') == lang]
        next_vol = max(existing_vols, default=0) + 1
        ll = "🇮🇷 فارسی" if lang == 'fa' else "🌐 لاتین"
        context.user_data.update({
            'ca_ref_book_id': bid,
            'ca_ref_lang':    lang,
            'ca_ref_volume':  next_vol,
            'ca_mode':        'waiting_ref_file',
        })
        await query.edit_message_text(
            f"📤 <b>آپلود {ll} — جلد {next_vol}</b>\n\n"
            f"فایل PDF را ارسال کنید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_book:{bid}'))
        # چون ممکنه خارج از ConversationHandler باشیم، state رو نمی‌تونیم return بدیم
        # message_router.py با چک ca_mode='waiting_ref_file' این رو handle می‌کنه

    elif action == 'upload_ref':
        # جایگزین کردن یک جلد موجود
        bid = parts[2]; lang = parts[3]; vol = int(parts[4])
        ll  = "🇮🇷 فارسی" if lang == 'fa' else "🌐 لاتین"
        context.user_data.update({
            'ca_ref_book_id': bid,
            'ca_ref_lang':    lang,
            'ca_ref_volume':  vol,
            'ca_mode':        'waiting_ref_file',
        })
        await query.edit_message_text(
            f"🔄 <b>جایگزین {ll} جلد {vol}</b>\n\nفایل جدید ارسال کنید:\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:ref_book:{bid}'))

    elif action == 'del_ref_file':
        fid = parts[2]; await db.ref_delete_file(fid)
        bid = context.user_data.get('ca_ref_book_id','')
        await query.edit_message_text("✅ فایل حذف شد.",
            reply_markup=_back_btn("🔙 بازگشت", f'ca:ref_book:{bid}'))

    # ══════════ FAQ ══════════

    elif action == 'overview':
        await _show_overview(query)

    elif action == 'create_q':
        # redirect به بانک سوال برای طراحی سوال
        kb = [[InlineKeyboardButton("✏️ شروع طراحی سوال", callback_data='questions:create_ca')],
              [InlineKeyboardButton("🔙 بازگشت", callback_data='ca:main')]]
        await query.edit_message_text(
            "✏️ <b>طراحی سوال (ادمین محتوا)</b>\n\n"
            "سوالات شما با برچسب <b>«طراحی شده توسط بات»</b> مشخص می‌شوند\n"
            "و بدون نیاز به تأیید، مستقیم در بانک سوال قرار می‌گیرند.",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

    elif action == 'faq':
        await _show_faq(query)

    elif action == 'add_faq_prompt':
        context.user_data['ca_mode'] = 'add_faq'
        await query.edit_message_text(
            "➕ <b>سوال متداول جدید</b>\n\n"
            "فرمت: <code>سوال | جواب | دسته</code>\n⌨️ /cancel",
            parse_mode='HTML', reply_markup=_back_btn("❌ لغو", 'ca:faq'))

    elif action == 'del_faq':
        await db.faq_delete(parts[2]); await _show_faq(query)


# ══════════════════════════════════════════════════════════
#  توابع نمایش
# ══════════════════════════════════════════════════════════

async def _show_main(query):
    kb = [
        [InlineKeyboardButton("📊 نمای کلی و آمار",   callback_data='ca:overview')],
        [InlineKeyboardButton("📘 مدیریت علوم پایه",  callback_data='ca:terms')],
        [InlineKeyboardButton("📚 مدیریت رفرنس‌ها",   callback_data='ca:refs')],
        [InlineKeyboardButton("✏️ طراحی سوال",         callback_data='ca:create_q')],
        [InlineKeyboardButton("❓ مدیریت FAQ",          callback_data='ca:faq')],
    ]
    await query.edit_message_text("🎓 <b>پنل ادمین محتوا</b>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))



async def _show_overview(query):
    """نمای کلی آمار — طراحی حرفه‌ای"""
    s = await db.content_admin_stats()

    # ── نوار پیشرفت ──
    def bar(val, mx, width=8):
        if mx == 0: return '░' * width
        filled = min(width, round(val / mx * width))
        return '█' * filled + '░' * (width - filled)

    bs_bar  = bar(s['bs_total'],   max(s['bs_total'], 1))
    ref_bar = bar(s['ref_files'],  max(s['ref_files'], 1))
    q_bar   = bar(s['q_total'],    max(s['q_total'], 1))

    # ── نسبت پاسخ صحیح سوالات ──
    q_ratio = f"{round(s['q_by_bot'] / s['q_total'] * 100)}٪ بات" if s['q_total'] else '—'

    from datetime import datetime
    now = datetime.now().strftime('%H:%M — %Y/%m/%d')

    text = (
        "╔══════════════════════╗\n"
        "   📊 <b>داشبورد پنل محتوا</b>\n"
        "╚══════════════════════╝\n"
        f"<i>🕐 {now}</i>\n\n"

        "━━━━ 📘 <b>علوم پایه</b> ━━━━\n"
        f"📖 <b>{s['bs_lessons']}</b> درس   "
        f"📌 <b>{s['bs_sessions']}</b> جلسه   "
        f"📁 <b>{s['bs_total']}</b> فایل\n"
        f"<code>[{bs_bar}]</code>\n\n"
        f"  🎥 ویدیو: <b>{s['bs_video']}</b>      "
        f"📄 جزوه: <b>{s['bs_pdf']}</b>\n"
        f"  📊 پاورپوینت: <b>{s['bs_ppt']}</b>   "
        f"🎙 ویس: <b>{s['bs_voice']}</b>\n"
        f"  📝 نکات: <b>{s['bs_note']}</b>        "
        f"🧪 تست: <b>{s['bs_test']}</b>\n\n"

        "━━━━ 📚 <b>رفرنس‌ها</b> ━━━━━\n"
        f"📖 <b>{s['ref_subjects']}</b> درس   "
        f"📘 <b>{s['ref_books']}</b> کتاب   "
        f"📁 <b>{s['ref_files']}</b> فایل\n"
        f"<code>[{ref_bar}]</code>\n"
        f"  🇮🇷 فارسی: <b>{s['ref_fa']}</b>   "
        f"🌐 لاتین: <b>{s['ref_en']}</b>\n\n"

        "━━━━ 🧪 <b>بانک سوال</b> ━━━━\n"
        f"✅ تأیید شده: <b>{s['q_total']}</b>   "
        f"⏳ انتظار: <b>{s['q_pending']}</b>\n"
        f"<code>[{q_bar}]</code>\n"
        f"  🤖 توسط بات: <b>{s['q_by_bot']}</b>   "
        f"👤 کاربران: <b>{s['q_by_users']}</b>\n\n"

        "━━━━ 📈 <b>کلی</b> ━━━━━━━━━\n"
        f"⬇️ کل دانلودها: <b>{s['total_downloads']}</b>\n"
        f"👥 دانشجویان فعال: <b>{s['users_count']}</b>\n"
    )

    kb = [
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data='ca:overview')],
        [InlineKeyboardButton("🔙 بازگشت",    callback_data='ca:main')],
    ]
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def _show_terms(query, back='ca:main'):
    kb = []
    for i in range(0, len(TERMS), 2):
        row = [InlineKeyboardButton(f"📘 {TERMS[i]}", callback_data=f'ca:term:{i}')]
        if i+1 < len(TERMS):
            row.append(InlineKeyboardButton(f"📘 {TERMS[i+1]}", callback_data=f'ca:term:{i+1}'))
        kb.append(row)
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back)])
    await query.edit_message_text("📘 <b>انتخاب ترم — علوم پایه</b>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_lessons(query, context, term, back='ca:terms'):
    lessons = await db.bs_get_lessons(term)
    idx     = context.user_data.get('ca_term_idx', 0)
    kb = []
    for i, l in enumerate(lessons):
        lid = str(l['_id'])
        t   = f" | {l['teacher']}" if l.get('teacher') else ''
        # ردیف اصلی
        kb.append([
            InlineKeyboardButton(f"📖 {l['name']}{t}", callback_data=f'ca:lesson:{lid}'),
            InlineKeyboardButton("✏️", callback_data=f'ca:edit_lesson_menu:{lid}'),
            InlineKeyboardButton("🗑",  callback_data=f'ca:del_lesson:{lid}'),
        ])
        # ردیف ترتیب
        nav = []
        if i > 0:
            nav.append(InlineKeyboardButton("⬆️", callback_data=f'ca:lesson_up:{lid}'))
        if i < len(lessons) - 1:
            nav.append(InlineKeyboardButton("⬇️", callback_data=f'ca:lesson_down:{lid}'))
        if nav:
            kb.append(nav)
    kb.append([InlineKeyboardButton("➕ درس جدید", callback_data=f'ca:add_lesson_prompt:{idx}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",   callback_data=back)])
    await query.edit_message_text(
        f"📘 <b>{term}</b> — {len(lessons)} درس\n"
        "<i>✏️=ویرایش  🗑=حذف  ⬆️⬇️=ترتیب</i>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_sessions(query, context, lid):
    lesson   = await db.bs_get_lesson(lid)
    sessions = await db.bs_get_sessions(lid)
    idx      = context.user_data.get('ca_term_idx', 0)
    kb = []
    for s in sessions:
        sid = str(s['_id'])
        kb.append([
            InlineKeyboardButton(f"📌 {s['number']} — {s.get('topic','')[:22]}", callback_data=f'ca:session:{sid}'),
            InlineKeyboardButton("✏️", callback_data=f'ca:edit_session_menu:{sid}'),
            InlineKeyboardButton("🗑",  callback_data=f'ca:del_session:{sid}'),
        ])
    kb.append([InlineKeyboardButton("➕ جلسه جدید", callback_data=f'ca:add_session_prompt:{lid}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",    callback_data=f'ca:term:{idx}')])
    lname = lesson.get('name','') if lesson else ''
    await query.edit_message_text(
        f"📖 <b>{lname}</b> — {len(sessions)} جلسه\n<i>✏️=ویرایش  🗑=حذف</i>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_session_content(query, context, sid):
    session  = await db.bs_get_session(sid)
    contents = await db.bs_get_content(sid)
    lid      = context.user_data.get('ca_lesson_id','')
    ICONS    = dict(CONTENT_TYPES)
    kb = []
    for i, c in enumerate(contents):
        cid  = str(c['_id'])
        ctype = c.get('type','pdf')
        desc  = c.get('description','')[:18] or f'فایل {i+1}'
        # ردیف فایل
        kb.append([
            InlineKeyboardButton(f"{ICONS.get(ctype,'📎')} {desc}", callback_data=f'ca:session:{sid}'),
            InlineKeyboardButton("🗑", callback_data=f'ca:del_content:{cid}'),
        ])
        # ردیف ترتیب
        nav = []
        if i > 0:
            nav.append(InlineKeyboardButton("⬆️", callback_data=f'ca:content_up:{cid}'))
        if i < len(contents) - 1:
            nav.append(InlineKeyboardButton("⬇️", callback_data=f'ca:content_down:{cid}'))
        if nav:
            kb.append(nav)

    if not contents:
        kb.append([InlineKeyboardButton("📤 آپلود اولین فایل", callback_data=f'ca:upload_content:{sid}')])
    else:
        kb.append([InlineKeyboardButton("📤 ➕ افزودن فایل جدید", callback_data=f'ca:upload_content:{sid}')])
    kb.append([InlineKeyboardButton("✏️ ویرایش اطلاعات جلسه", callback_data=f'ca:edit_session_menu:{sid}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",              callback_data=f'ca:lesson:{lid}')])

    by_type = {}
    for c in contents:
        by_type.setdefault(c.get('type','pdf'), []).append(c)
    summary = '  '.join(f"{ICONS.get(t,'📎')}×{len(v)}" for t,v in by_type.items()) if by_type else '❌ بدون فایل'

    if session:
        header = (f"📌 <b>جلسه {session.get('number','')}</b>\n"
                  f"📚 {session.get('topic','')}\n"
                  f"👨‍🏫 {session.get('teacher','') or 'ثبت نشده'}\n"
                  f"━━━━━━━━━━━━━━━━\n"
                  f"📁 {len(contents)} فایل: {summary}\n"
                  f"<i>⬆️⬇️=ترتیب  🗑=حذف</i>")
    else:
        header = "📌 جلسه"
    await query.edit_message_text(header, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_ref_subjects(query, back='ca:main'):
    subjects = await db.ref_get_subjects()
    kb = []
    for i, s in enumerate(subjects):
        sid = str(s['_id'])
        kb.append([
            InlineKeyboardButton(f"📖 {s['name']}", callback_data=f'ca:ref_subject:{sid}'),
            InlineKeyboardButton("✏️", callback_data=f'ca:edit_ref_subject_prompt:{sid}'),
            InlineKeyboardButton("🗑",  callback_data=f'ca:del_ref_subject:{sid}'),
        ])
        nav = []
        if i > 0:
            nav.append(InlineKeyboardButton("⬆️", callback_data=f'ca:ref_subject_up:{sid}'))
        if i < len(subjects) - 1:
            nav.append(InlineKeyboardButton("⬇️", callback_data=f'ca:ref_subject_down:{sid}'))
        if nav:
            kb.append(nav)
    kb.append([InlineKeyboardButton("➕ درس جدید", callback_data='ca:add_ref_subject_prompt')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",   callback_data=back)])
    await query.edit_message_text(
        f"📚 <b>رفرنس‌ها</b> — {len(subjects)} درس\n<i>✏️=ویرایش  🗑=حذف  ⬆️⬇️=ترتیب</i>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_ref_books(query, context, sid, back='ca:refs'):
    subj  = await db.ref_get_subject(sid)
    books = await db.ref_get_books(sid)
    kb = []
    for i, b in enumerate(books):
        bid = str(b['_id'])
        kb.append([
            InlineKeyboardButton(f"📘 {b['name']}", callback_data=f'ca:ref_book:{bid}'),
            InlineKeyboardButton("✏️", callback_data=f'ca:edit_ref_book_prompt:{bid}'),
            InlineKeyboardButton("🗑",  callback_data=f'ca:del_ref_book:{bid}'),
        ])
        nav = []
        if i > 0:
            nav.append(InlineKeyboardButton("⬆️", callback_data=f'ca:ref_book_up:{bid}'))
        if i < len(books) - 1:
            nav.append(InlineKeyboardButton("⬇️", callback_data=f'ca:ref_book_down:{bid}'))
        if nav:
            kb.append(nav)
    kb.append([InlineKeyboardButton("➕ کتاب جدید", callback_data=f'ca:add_ref_book_prompt:{sid}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",    callback_data=back)])
    name = subj.get('name','') if subj else ''
    await query.edit_message_text(
        f"📖 <b>{name}</b> — {len(books)} رفرنس\n<i>✏️=ویرایش  🗑=حذف  ⬆️⬇️=ترتیب</i>",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_ref_book_files(query, context, bid):
    book    = await db.ref_get_book(bid)
    files   = await db.ref_get_files(bid)
    sid     = context.user_data.get('ca_ref_subject_id','')
    kb      = []

    # گروه‌بندی بر اساس زبان
    fa_files = sorted([f for f in files if f.get('lang') == 'fa'], key=lambda x: x.get('volume',1))
    en_files = sorted([f for f in files if f.get('lang') == 'en'], key=lambda x: x.get('volume',1))

    for lang, items, label_prefix in [('fa', fa_files, '🇮🇷 فارسی'), ('en', en_files, '🌐 لاتین')]:
        for f in items:
            fid = str(f['_id']); vol = f.get('volume',1); dl = f.get('downloads',0)
            desc = f.get('description','')
            row_label = f"✅ {label_prefix} جلد {vol}" + (f" — {desc[:15]}" if desc else '') + f"  ⬇️{dl}"
            kb.append([
                InlineKeyboardButton(row_label, callback_data=f'ca:ref_book:{bid}'),
                InlineKeyboardButton("🔄", callback_data=f'ca:upload_ref:{bid}:{lang}:{vol}'),
                InlineKeyboardButton("🗑", callback_data=f'ca:del_ref_file:{fid}'),
            ])
        # دکمه افزودن جلد جدید
        kb.append([InlineKeyboardButton(
            f"📤 ➕ جلد جدید {label_prefix}",
            callback_data=f'ca:upload_ref_volume_prompt:{bid}:{lang}'
        )])

    kb.append([InlineKeyboardButton("✏️ ویرایش نام کتاب", callback_data=f'ca:edit_ref_book_prompt:{bid}')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",           callback_data=f'ca:ref_subject:{sid}')])
    name = book.get('name','') if book else ''
    await query.edit_message_text(
        f"📘 <b>{name}</b>\n"
        f"📁 {len(files)} فایل\n\n"
        "🔄=جایگزین  🗑=حذف  ➕=جلد جدید",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


async def _show_faq(query):
    faqs = await db.faq_get_all()
    kb   = []
    for f in faqs[:15]:
        fid = str(f['_id'])
        kb.append([
            InlineKeyboardButton(f"❓ {f.get('question','')[:30]}", callback_data='ca:faq'),
            InlineKeyboardButton("🗑", callback_data=f'ca:del_faq:{fid}'),
        ])
    kb.append([InlineKeyboardButton("➕ سوال جدید", callback_data='ca:add_faq_prompt')])
    kb.append([InlineKeyboardButton("🔙 بازگشت",   callback_data='ca:main')])
    await query.edit_message_text(
        f"❓ <b>سوالات متداول</b> — {len(faqs)} سوال",
        parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))


# ══════════════════════════════════════════════════════════
#  هندلر فایل
# ══════════════════════════════════════════════════════════

async def ca_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    if not await db.is_content_admin(uid): return
    ca_mode = context.user_data.get('ca_mode','')
    if ca_mode not in ('waiting_file','waiting_ref_file'): return

    file_obj = (update.message.document or update.message.video or
                update.message.audio    or update.message.voice)
    if not file_obj:
        await update.message.reply_text("❌ فایل معتبر ارسال کنید.\n⌨️ /cancel")
        return CA_WAITING_FILE

    fid = file_obj.file_id

    if ca_mode == 'waiting_ref_file':
        bid  = context.user_data.get('ca_ref_book_id','')
        lang = context.user_data.get('ca_ref_lang','fa')
        vol  = context.user_data.get('ca_ref_volume', 1)
        ll   = "🇮🇷 فارسی" if lang == 'fa' else "🌐 لاتین"
        # بپرس توضیح اضافه بخواد بده
        context.user_data.update({'ca_pending_file': fid, 'ca_mode': 'waiting_ref_description'})
        await update.message.reply_text(
            f"✅ فایل {ll} جلد {vol} دریافت شد!\n\n"
            "📝 توضیح اختیاری (مثلاً: ویرایش سوم):\n"
            "اگر توضیحی ندارید <code>-</code> بزنید:\n⌨️ /cancel",
            parse_mode='HTML',
            reply_markup=_back_btn("❌ لغو (بدون توضیح)", f'ca:ref_book:{bid}'))
        return CA_WAITING_TEXT

    # فایل محتوای جلسه
    context.user_data.update({'ca_pending_file': fid, 'ca_mode': 'waiting_description'})
    sid = context.user_data.get('ca_session_id','')
    await update.message.reply_text(
        "✅ فایل دریافت شد!\n\n"
        "📝 توضیح اختیاری برای این فایل:\n"
        "(مثلاً: ویدیو قسمت اول — فیزیولوژی کلیه)\n"
        "اگر توضیحی ندارید <code>-</code> بزنید:\n⌨️ /cancel",
        parse_mode='HTML',
        reply_markup=_back_btn("❌ لغو", f'ca:session:{sid}'))
    return CA_WAITING_TEXT


# ══════════════════════════════════════════════════════════
#  هندلر متن
# ══════════════════════════════════════════════════════════

async def ca_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    if not await db.is_content_admin(uid): return
    ca_mode = context.user_data.get('ca_mode','')
    text    = update.message.text.strip()

    if text.lower() in ('/cancel','لغو','❌ لغو','cancel'):
        _clear(context)
        await update.message.reply_text("✅ عملیات لغو شد.")
        return ConversationHandler.END

    if ca_mode == 'add_lesson':
        ps = [p.strip() for p in text.split(',')]
        name = ps[0]; teacher = ps[1] if len(ps) > 1 else ''
        term = context.user_data.get('ca_term',''); idx = context.user_data.get('ca_term_idx',0)
        result = await db.bs_add_lesson(term, name, teacher)
        _clear(context)
        msg = f"✅ درس «{name}» اضافه شد!" if result else "⚠️ این درس قبلاً وجود دارد."
        await update.message.reply_text(msg, reply_markup=_back_btn("🔙 برگشت", f'ca:term:{idx}'))

    elif ca_mode == 'edit_lesson':
        lid = context.user_data.get('ca_edit_target',''); field = context.user_data.get('ca_edit_field','')
        ok = await db.bs_update_lesson(lid, {field: text})
        _clear(context)
        await update.message.reply_text("✅ ذخیره شد." if ok else "❌ خطا.",
            reply_markup=_back_btn("🔙 برگشت", f'ca:lesson:{lid}'))

    elif ca_mode == 'add_session':
        ps  = [p.strip() for p in text.split(',')]
        lid = context.user_data.get('ca_lesson_id','')
        if len(ps) < 2:
            await update.message.reply_text(
                "❌ فرمت اشتباه!\nمثال: <code>3, فیزیولوژی کلیه, دکتر احمدی</code>\n⌨️ /cancel",
                parse_mode='HTML', reply_markup=_back_btn("❌ لغو", f'ca:lesson:{lid}'))
            return CA_WAITING_TEXT
        try:    number = int(ps[0])
        except:
            sessions = await db.bs_get_sessions(lid); number = len(sessions) + 1
        topic = ps[1]; teacher = ps[2] if len(ps) > 2 else ''
        await db.bs_add_session(lid, number, topic, teacher)
        _clear(context)
        await update.message.reply_text(f"✅ جلسه {number} — «{topic}» اضافه شد!",
            reply_markup=_back_btn("🔙 برگشت", f'ca:lesson:{lid}'))

    elif ca_mode == 'edit_session':
        sid = context.user_data.get('ca_edit_target',''); field = context.user_data.get('ca_edit_field','')
        val = int(text) if field == 'number' and text.isdigit() else text
        ok  = await db.bs_update_session(sid, {field: val})
        _clear(context)
        await update.message.reply_text("✅ جلسه ویرایش شد." if ok else "❌ خطا.",
            reply_markup=_back_btn("🔙 برگشت", f'ca:session:{sid}'))

    elif ca_mode == 'waiting_description':
        desc = '' if text == '-' else text
        fid  = context.user_data.get('ca_pending_file','')
        sid  = context.user_data.get('ca_session_id','')
        ct   = context.user_data.get('ca_content_type','pdf')
        await db.bs_add_content(sid, ct, fid, description=desc)
        tl = dict(CONTENT_TYPES).get(ct, ct)
        _clear(context)
        await update.message.reply_text(f"✅ {tl} اضافه شد!",
            reply_markup=_back_btn("🔙 برگشت", f'ca:session:{sid}'))

    elif ca_mode == 'waiting_ref_description':
        desc  = '' if text == '-' else text
        fid   = context.user_data.get('ca_pending_file','')
        bid   = context.user_data.get('ca_ref_book_id','')
        lang  = context.user_data.get('ca_ref_lang','fa')
        vol   = context.user_data.get('ca_ref_volume', 1)
        await db.ref_add_file(bid, lang, fid, volume=vol, description=desc)
        ll = "🇮🇷 فارسی" if lang == 'fa' else "🌐 لاتین"
        _clear(context)
        await update.message.reply_text(
            f"✅ {ll} جلد {vol} آپلود شد!" + (f"\n📝 {desc}" if desc else ''),
            reply_markup=_back_btn("🔙 برگشت", f'ca:ref_book:{bid}'))

    elif ca_mode == 'add_ref_subject':
        result = await db.ref_add_subject(text)
        fa = context.user_data.get('ca_ref_from_admin', False)
        back = 'ca:refs_admin' if fa else 'ca:refs'
        _clear(context)
        await update.message.reply_text(
            f"✅ درس «{text}» اضافه شد!" if result else "⚠️ قبلاً وجود دارد.",
            reply_markup=_back_btn("🔙 برگشت", back))

    elif ca_mode == 'edit_ref_subject':
        sid = context.user_data.get('ca_edit_target','')
        ok  = await db.ref_update_subject(sid, {'name': text})
        _clear(context)
        await update.message.reply_text(f"✅ نام به «{text}» تغییر یافت." if ok else "❌ خطا.",
            reply_markup=_back_btn("🔙 برگشت", f'ca:ref_subject:{sid}'))

    elif ca_mode == 'add_ref_book':
        sid = context.user_data.get('ca_ref_subject_id','')
        await db.ref_add_book(sid, text)
        _clear(context)
        await update.message.reply_text(f"✅ رفرنس «{text}» اضافه شد!",
            reply_markup=_back_btn("🔙 برگشت", f'ca:ref_subject:{sid}'))

    elif ca_mode == 'edit_ref_book':
        bid = context.user_data.get('ca_edit_target','')
        ok  = await db.ref_update_book(bid, {'name': text})
        _clear(context)
        await update.message.reply_text(f"✅ نام کتاب به «{text}» تغییر یافت." if ok else "❌ خطا.",
            reply_markup=_back_btn("🔙 برگشت", f'ca:ref_book:{bid}'))

    elif ca_mode == 'add_faq':
        ps = [p.strip() for p in text.split('|')]
        if len(ps) < 2:
            await update.message.reply_text(
                "❌ فرمت اشتباه!\nمثال: <code>سوال | جواب | دسته</code>\n⌨️ /cancel",
                parse_mode='HTML'); return CA_WAITING_TEXT
        question = ps[0]; answer = ps[1]; category = ps[2] if len(ps) > 2 else 'عمومی'
        await db.faq_add(question, answer, category)
        _clear(context)
        await update.message.reply_text(f"✅ سوال اضافه شد!",
            reply_markup=_back_btn("🔙 برگشت", 'ca:faq'))

    else:
        _clear(context)
        await update.message.reply_text("⚠️ لطفاً از منوی ربات استفاده کنید.")
        return ConversationHandler.END

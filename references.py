"""رفرنس‌ها — دانشجو — با پشتیبانی چند جلد"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db

logger = logging.getLogger(__name__)


async def references_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    data   = query.data
    parts  = data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    came_from_admin = context.user_data.get('ref_from_admin', False)

    if action == 'main':
        context.user_data['ref_from_admin'] = False
        await _show_subjects(query, back_cb='resources:menu')

    elif action == 'main_admin':
        context.user_data['ref_from_admin'] = True
        await _show_subjects(query, back_cb='admin:main')

    elif action == 'subject':
        subject_id = parts[2]
        context.user_data['ref_subject_id'] = subject_id
        back = 'ref:main_admin' if came_from_admin else 'ref:main'
        await _show_books(query, context, subject_id, back_cb=back)

    elif action == 'book':
        book_id = parts[2]
        context.user_data['ref_book_id'] = book_id
        subject_id = context.user_data.get('ref_subject_id', '')
        await _show_lang_choice(query, context, book_id,
                                back_cb=f'ref:subject:{subject_id}')

    elif action == 'volumes':
        # نمایش جلدهای یک زبان خاص
        book_id = parts[2]
        lang    = parts[3]
        context.user_data['ref_book_id'] = book_id
        subject_id = context.user_data.get('ref_subject_id', '')
        await _show_volumes(query, context, book_id, lang,
                            back_cb=f'ref:book:{book_id}')

    elif action == 'dl':
        file_id_db = parts[2]
        await _download_ref(query, file_id_db, update.effective_user.id)


# ══════════════════════════════════════════════════════════

async def _show_subjects(query, back_cb='resources:menu'):
    subjects = await db.ref_get_subjects()
    if not subjects:
        await query.edit_message_text(
            "📚 <b>رفرنس‌ها</b>\n\n❌ هنوز درسی تعریف نشده.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb)
            ]]))
        return
    keyboard = []
    for s in subjects:
        sid = str(s['_id'])
        keyboard.append([InlineKeyboardButton(f"📖 {s['name']}",
                                              callback_data=f'ref:subject:{sid}')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb)])
    await query.edit_message_text(
        "📚 <b>رفرنس‌های درسی</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "درس مورد نظر را انتخاب کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_books(query, context, subject_id, back_cb='ref:main'):
    subject = await db.ref_get_subject(subject_id)
    if not subject:
        await query.answer("❌ درس پیدا نشد!", show_alert=True); return
    books = await db.ref_get_books(subject_id)
    if not books:
        await query.edit_message_text(
            f"📖 <b>{subject['name']}</b>\n\n❌ رفرنسی برای این درس تعریف نشده.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb)
            ]]))
        return
    keyboard = []
    for b in books:
        bid = str(b['_id'])
        # نشون بده چند فایل داره
        files     = await db.ref_get_files(bid)
        fa_count  = sum(1 for f in files if f.get('lang') == 'fa')
        en_count  = sum(1 for f in files if f.get('lang') == 'en')
        badges    = []
        if fa_count: badges.append(f"🇮🇷×{fa_count}" if fa_count > 1 else "🇮🇷")
        if en_count: badges.append(f"🌐×{en_count}" if en_count > 1 else "🌐")
        badge_str = "  " + "  ".join(badges) if badges else ""
        keyboard.append([InlineKeyboardButton(
            f"📘 {b['name']}{badge_str}", callback_data=f'ref:book:{bid}')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb)])
    await query.edit_message_text(
        f"📖 <b>{subject['name']}</b>\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"رفرنس مورد نظر را انتخاب کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_lang_choice(query, context, book_id, back_cb='ref:main'):
    """انتخاب زبان — اگه چند جلد داشت مستقیم جلدها رو نشون بده"""
    book = await db.ref_get_book(book_id)
    if not book:
        await query.answer("❌ کتاب پیدا نشد!", show_alert=True); return

    files = await db.ref_get_files(book_id)
    if not files:
        await query.edit_message_text(
            f"📘 <b>{book['name']}</b>\n\n❌ فایلی برای این رفرنس بارگذاری نشده.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb)
            ]]))
        return

    # گروه‌بندی بر اساس زبان
    fa_files = sorted([f for f in files if f.get('lang') == 'fa'],
                      key=lambda x: x.get('volume', 1))
    en_files = sorted([f for f in files if f.get('lang') == 'en'],
                      key=lambda x: x.get('volume', 1))

    keyboard = []

    for lang, lang_files, lang_icon, lang_label in [
        ('fa', fa_files, '🇮🇷', 'ترجمه فارسی'),
        ('en', en_files, '🌐', 'نسخه لاتین (اصلی)'),
    ]:
        if not lang_files:
            continue

        if len(lang_files) == 1:
            # فقط یه جلد — مستقیم دانلود
            f   = lang_files[0]
            fid = str(f['_id'])
            dl  = f.get('downloads', 0)
            vol = f.get('volume', 1)
            desc = f.get('description', '')
            btn_label = f"{lang_icon} {lang_label} | ⬇️ {dl}"
            if desc:
                btn_label = f"{lang_icon} {lang_label} — {desc[:20]} | ⬇️ {dl}"
            keyboard.append([InlineKeyboardButton(btn_label,
                                                  callback_data=f'ref:dl:{fid}')])
        else:
            # چند جلد — نشون بده چند جلده، برو صفحه انتخاب جلد
            total_dl = sum(f.get('downloads', 0) for f in lang_files)
            keyboard.append([InlineKeyboardButton(
                f"{lang_icon} {lang_label} | {len(lang_files)} جلد | ⬇️ {total_dl}",
                callback_data=f'ref:volumes:{book_id}:{lang}'
            )])

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb)])

    await query.edit_message_text(
        f"📘 <b>{book['name']}</b>\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"نسخه مورد نظر را انتخاب کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_volumes(query, context, book_id, lang, back_cb='ref:main'):
    """نمایش همه جلدهای یک زبان برای انتخاب"""
    book = await db.ref_get_book(book_id)
    if not book:
        await query.answer("❌ کتاب پیدا نشد!", show_alert=True); return

    files = await db.ref_get_files(book_id)
    lang_files = sorted([f for f in files if f.get('lang') == lang],
                        key=lambda x: x.get('volume', 1))

    if not lang_files:
        await query.answer("❌ فایلی پیدا نشد!", show_alert=True); return

    lang_icon  = '🇮🇷' if lang == 'fa' else '🌐'
    lang_label = 'ترجمه فارسی' if lang == 'fa' else 'نسخه لاتین (اصلی)'

    keyboard = []
    for f in lang_files:
        fid  = str(f['_id'])
        vol  = f.get('volume', 1)
        dl   = f.get('downloads', 0)
        desc = f.get('description', '')

        # لیبل دکمه: جلد شماره + توضیح (اگه داشت) + تعداد دانلود
        if desc:
            btn_label = f"{lang_icon} جلد {vol} — {desc} | ⬇️ {dl}"
        else:
            btn_label = f"{lang_icon} جلد {vol} | ⬇️ {dl}"

        keyboard.append([InlineKeyboardButton(btn_label,
                                              callback_data=f'ref:dl:{fid}')])

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb)])

    await query.edit_message_text(
        f"📘 <b>{book['name']}</b>\n"
        f"{lang_icon} <b>{lang_label}</b>\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"جلد مورد نظر را انتخاب کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard))


async def _download_ref(query, file_id_db, uid):
    item = await db.ref_get_file(file_id_db)
    if not item:
        await query.answer("❌ فایل پیدا نشد!", show_alert=True); return
    await db.ref_inc_download(file_id_db, uid)

    lang  = item.get('lang', 'fa')
    vol   = item.get('volume', 1)
    desc  = item.get('description', '')
    dl    = item.get('downloads', 0)

    lang_icon  = '🇮🇷' if lang == 'fa' else '🌐'
    lang_label = 'ترجمه فارسی' if lang == 'fa' else 'نسخه لاتین (اصلی)'

    caption_parts = [f"📘 {lang_icon} {lang_label} — جلد {vol}"]
    if desc:
        caption_parts.append(f"📝 {desc}")
    caption_parts.append(f"📥 {dl} دانلود")
    caption = "\n".join(caption_parts)

    try:
        await query.message.reply_document(
            item['file_id'],
            caption=caption,
            parse_mode='HTML')
    except Exception as e:
        logger.error(f"ref download error: {e}")
        await query.answer("❌ خطا در ارسال فایل!", show_alert=True)

"""
🤖 پنل مدیریت AiHums — تنظیمات هوش مصنوعی کاملاً از دیتابیس
  (هیچ‌چیز هاردکد نیست). ادمین ارشد می‌تونه از همینجا:
   ✅ روشن/خاموش کنه
   ✅ API Key رو تنظیم/تغییر بده (بدون لمس کد یا env)
   ✅ مدل رو عوض کنه
   ✅ محدودیت روزانه‌ی هر کاربر رو تنظیم کنه
   ✅ دستور سیستمی (System Prompt) رو ویرایش کنه
   ✅ اتصال رو تست کنه
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils import ADMIN_ID, send_audit_log
from ai_solver import (
    get_ai_config, set_ai_setting, ask_ai,
    DEFAULT_PROMPT, AIError,
)

logger = logging.getLogger(__name__)

MODEL_PRESETS = [
    ('gemini-2.5-flash',      '⚡ Gemini 2.5 Flash (پیشنهادی)'),
    ('gemini-2.5-flash-lite', '💨 Gemini 2.5 Flash-Lite (سریع‌تر و سبک‌تر)'),
    ('gemini-2.5-pro',        '🧠 Gemini 2.5 Pro (دقیق‌تر، محدودیت کمتر)'),
]


def _mask_key(key: str) -> str:
    if not key:
        return "⚠️ تنظیم نشده"
    if len(key) <= 8:
        return "•" * len(key)
    return key[:4] + "•" * 6 + key[-4:]


async def show_ai_main(query):
    cfg = await get_ai_config()
    status_txt = "✅ فعال" if cfg['enabled'] else "⬜ غیرفعال"
    toggle_txt = "🔴 غیرفعال کردن" if cfg['enabled'] else "🟢 فعال کردن"
    limit      = cfg['daily_limit']
    limit_txt  = "بدون محدودیت" if not limit else f"{limit} سوال در روز / هر کاربر"

    text = (
        "🤖 <b>مدیریت AiHums — دستیار هوشمند حل سوال</b>\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"📊 وضعیت: {status_txt}\n"
        f"🧠 ارائه‌دهنده: <code>{cfg['provider']}</code>\n"
        f"🧩 مدل: <code>{cfg['model']}</code>\n"
        f"🔑 API Key: <code>{_mask_key(cfg['api_key'])}</code>\n"
        f"👥 محدودیت روزانه: {limit_txt}\n\n"
        "<i>دانشجویان با دکمه‌ی «🤖 AiHums» در منوی اصلی، سوال متنی یا "
        "عکس سوال می‌فرستن و طبق همین تنظیمات جواب می‌گیرن.</i>"
    )
    keyboard = [
        [InlineKeyboardButton(toggle_txt, callback_data='ai:toggle')],
        [InlineKeyboardButton("🔑 تنظیم / تغییر API Key", callback_data='ai:set_key')],
        [InlineKeyboardButton("🧩 انتخاب مدل", callback_data='ai:pick_model')],
        [InlineKeyboardButton("👥 محدودیت روزانه هر کاربر", callback_data='ai:set_limit')],
        [InlineKeyboardButton("💬 ویرایش دستور سیستمی", callback_data='ai:set_prompt')],
        [InlineKeyboardButton("🧪 تست اتصال", callback_data='ai:test')],
        [InlineKeyboardButton("🔙 بازگشت", callback_data='admin:cat_settings')],
    ]
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def ai_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = update.effective_user.id

    if uid != ADMIN_ID:
        await query.answer("⛔️ این بخش فقط برای مدیر ارشد است.", show_alert=True)
        return

    await query.answer()
    parts  = query.data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    if action == 'main':
        await show_ai_main(query)
        return

    if action == 'toggle':
        cfg = await get_ai_config()
        new_val = not cfg['enabled']
        if new_val and not cfg['api_key']:
            await query.answer("⚠️ اول باید یک API Key تنظیم کنی.", show_alert=True)
            return
        await set_ai_setting('enabled', new_val)
        await query.answer("✅ AiHums فعال شد" if new_val else "✅ AiHums غیرفعال شد", show_alert=True)
        await send_audit_log(
            context.bot, 'admin', 'مدیر ارشد', uid,
            "فعال‌سازی AiHums" if new_val else "غیرفعال‌سازی AiHums",
            module='AI', severity='HIGH', actor_role='مدیر ارشد',
        )
        await show_ai_main(query)
        return

    if action == 'set_key':
        context.user_data['mode'] = 'ai_set_key'
        await query.edit_message_text(
            "🔑 <b>تنظیم API Key</b>\n\n"
            "کلید API رو همین‌جا برام بفرست (مثلاً کلید Gemini از "
            "aistudio.google.com/apikey).\n\n"
            "<i>بلافاصله بعد از ذخیره، پیامت حذف می‌شه که جایی نمونه.</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='ai:main')]])
        )
        return

    if action == 'pick_model':
        kb = [[InlineKeyboardButton(label, callback_data=f'ai:set_model:{model_id}')]
              for model_id, label in MODEL_PRESETS]
        kb.append([InlineKeyboardButton("✏️ مدل سفارشی (تایپ دستی)", callback_data='ai:set_model_custom')])
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')])
        await query.edit_message_text(
            "🧩 <b>انتخاب مدل</b>\n\nیکی از مدل‌های آماده رو انتخاب کن یا مدل سفارشی وارد کن:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if action == 'set_model':
        model_id = parts[2] if len(parts) > 2 else ''
        if model_id:
            await set_ai_setting('model', model_id)
            await query.answer(f"✅ مدل روی {model_id} تنظیم شد", show_alert=True)
        await show_ai_main(query)
        return

    if action == 'set_model_custom':
        context.user_data['mode'] = 'ai_set_model'
        await query.edit_message_text(
            "✏️ نام دقیق مدل رو بفرست (مثلاً <code>gemini-2.5-flash</code>).",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='ai:main')]])
        )
        return

    if action == 'set_limit':
        context.user_data['mode'] = 'ai_set_limit'
        cfg = await get_ai_config()
        await query.edit_message_text(
            "👥 <b>محدودیت روزانه‌ی هر کاربر</b>\n\n"
            f"مقدار فعلی: <b>{cfg['daily_limit'] or 'نامحدود'}</b>\n\n"
            "یک عدد بفرست (مثلاً 15). برای نامحدود، عدد 0 رو بفرست.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='ai:main')]])
        )
        return

    if action == 'set_prompt':
        context.user_data['mode'] = 'ai_set_prompt'
        cfg = await get_ai_config()
        await query.edit_message_text(
            "💬 <b>ویرایش دستور سیستمی (System Prompt)</b>\n\n"
            "این متن به هوش مصنوعی می‌گه چه نقشی داره و چطور جواب بده.\n\n"
            f"متن فعلی:\n<code>{cfg['system_prompt']}</code>\n\n"
            "متن جدید رو بفرست، یا کلمه‌ی «حذف» رو بفرست تا به پیش‌فرض برگرده.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='ai:main')]])
        )
        return

    if action == 'test':
        cfg = await get_ai_config()
        if not cfg['api_key']:
            await query.edit_message_text(
                "⚠️ هنوز API Key تنظیم نشده.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')]])
            )
            return
        await query.edit_message_text("⏳ در حال تست اتصال...")
        try:
            result = await ask_ai(text="فقط با کلمه‌ی «سلام» جواب بده تا تستِ اتصال انجام بشه.")
            await query.edit_message_text(
                f"✅ اتصال موفق بود.\n\nپاسخ نمونه:\n{result[:300]}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')]])
            )
        except AIError as e:
            await query.edit_message_text(
                f"❌ تست ناموفق:\n{e}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')]])
            )
        except Exception as e:
            logger.exception("AI test failed")
            await query.edit_message_text(
                f"❌ خطای غیرمنتظره: {e}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')]])
            )
        return


async def ai_admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ورودی متنی حالت‌های تنظیمات AiHums (فقط ادمین ارشد)."""
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        return

    mode = context.user_data.get('mode', '')
    text = (update.message.text or '').strip()

    if mode == 'ai_set_key':
        context.user_data.pop('mode', None)
        await set_ai_setting('api_key', text)
        try:
            await update.message.delete()
        except Exception:
            pass
        await update.message.reply_text(
            "✅ API Key ذخیره شد (پیامت هم حذف شد که جایی نمونه).\n\n"
            "حالا از پنل AiHums دکمه‌ی «فعال کردن» رو بزن تا برای کاربرها فعال بشه."
        )
        return

    if mode == 'ai_set_model':
        context.user_data.pop('mode', None)
        await set_ai_setting('model', text)
        await update.message.reply_text(f"✅ مدل روی <code>{text}</code> تنظیم شد.", parse_mode='HTML')
        return

    if mode == 'ai_set_limit':
        if not text.isdigit():
            await update.message.reply_text("⚠️ یک عدد بفرست (مثلاً 15، یا 0 برای نامحدود).")
            return
        context.user_data.pop('mode', None)
        await set_ai_setting('daily_limit', int(text))
        await update.message.reply_text(
            f"✅ محدودیت روزانه روی {text if int(text) else 'نامحدود'} تنظیم شد."
        )
        return

    if mode == 'ai_set_prompt':
        context.user_data.pop('mode', None)
        if text in ('حذف', 'reset', 'پیش‌فرض', 'پیشفرض'):
            await set_ai_setting('system_prompt', DEFAULT_PROMPT)
            await update.message.reply_text("✅ دستور سیستمی به حالت پیش‌فرض برگشت.")
        else:
            await set_ai_setting('system_prompt', text)
            await update.message.reply_text("✅ دستور سیستمی جدید ذخیره شد.")
        return

"""
🤖 پنل مدیریت هوشیار — تنظیمات هوش مصنوعی کاملاً از دیتابیس
  (هیچ‌چیز هاردکد نیست). ادمین ارشد می‌تونه از همینجا:
   ✅ روشن/خاموش کنه
   ✅ API Key رو تنظیم/تغییر بده (بدون لمس کد یا env)
   ✅ مدل رو عوض کنه
   ✅ محدودیت روزانه‌ی هر کاربر رو تنظیم کنه
   ✅ دستور سیستمی (System Prompt) رو ویرایش کنه
   ✅ اتصال رو تست کنه
"""
import json
import logging
from datetime import datetime
from html import escape as _esc
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import db
from utils import ADMIN_ID, send_audit_log
from ai_solver import (
    get_ai_config, set_ai_setting, ask_ai, save_persona, delete_persona,
    DEFAULT_PROMPT, DEFAULT_DISABLED_MSG, AIError,
)

logger = logging.getLogger(__name__)

MODEL_PRESETS = {
    'gemini': [
        ('gemini-3.6-flash',      '🌟 Gemini 3.6 Flash (جدیدترین و پیشنهادیِ گوگل)'),
        ('gemini-3.5-flash',      '🆕 Gemini 3.5 Flash (قوی، برای استدلال سنگین)'),
        ('gemini-3.5-flash-lite', '🆕 Gemini 3.5 Flash-Lite (سریع و ارزون‌تر)'),
        ('gemini-2.5-flash',      '⚡ Gemini 2.5 Flash (پایدار و قدیمی‌تر)'),
        ('gemini-flash-latest',   '🔄 Gemini Flash Latest (اگه بالایی 404 داد)'),
        ('gemini-2.5-flash-lite', '💨 Gemini 2.5 Flash-Lite (سریع‌تر و سبک‌تر)'),
        ('gemini-2.5-pro',        '🧠 Gemini 2.5 Pro (دقیق‌تر، محدودیت کمتر)'),
    ],
    'openrouter': [
        ('google/gemma-4-31b-it:free', '⚡ Gemma 4 31B (پیشنهادی، تصویر+متن)'),
        ('openrouter/free',            '🎲 انتخاب خودکار از مدل‌های رایگان'),
    ],
}
PROVIDER_LABELS = {
    'gemini':     '🟦 Google Gemini',
    'openrouter': '🟪 OpenRouter',
}

# ══════════════════════════════════════════════════
#  قیمتِ رسمیِ گوگل برای هر ۱ میلیون توکن، به دلار — (ورودی, خروجی).
#  منبع: صفحه‌ی رسمیِ pricing گوگل (تیرماه ۱۴۰۵ / جولای ۲۰۲۶). این‌ها
#  نرخِ Paid Tier هستن؛ اگه پروژه روی Free Tier باشه هزینه‌ی واقعی صفره،
#  این عدد فقط برای تخمینِ «اگه پولی بود چقدر می‌شد» مفیده. مدل‌های
#  OpenRouter که اسمشون به «:free» ختم می‌شه هم صفر در نظر گرفته می‌شن.
# ══════════════════════════════════════════════════
PRICING = {
    'gemini-3.6-flash':      (1.50, 7.50),
    'gemini-3.5-flash':      (1.50, 9.00),
    'gemini-3.5-flash-lite': (0.30, 2.50),
    'gemini-2.5-flash':      (0.30, 2.50),
    'gemini-flash-latest':   (0.30, 2.50),
    'gemini-2.5-flash-lite': (0.10, 0.40),
    'gemini-2.5-pro':        (1.25, 10.00),
}
# فرضِ نسبتِ ورودی/خروجی برای تبدیلِ «توکنِ کل» به یه نرخِ ترکیبی؛ چون
# جواب‌های آموزشی معمولاً طولانی‌ترن، وزنِ بیشتری به قیمتِ خروجی می‌دیم.
_COST_INPUT_WEIGHT, _COST_OUTPUT_WEIGHT = 0.15, 0.85


def _blended_price_per_1m(model: str) -> float | None:
    if model.endswith(':free'):
        return 0.0
    prices = PRICING.get(model)
    if not prices:
        return None
    inp, out = prices
    return inp * _COST_INPUT_WEIGHT + out * _COST_OUTPUT_WEIGHT


def _estimate_cost(tokens: int, model: str) -> str:
    price = _blended_price_per_1m(model)
    if price is None:
        return "نامشخص برای این مدل"
    cost = (tokens / 1_000_000) * price
    return f"~${cost:.4f}" if cost >= 0.0001 else "~$0"


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
        "🤖 <b>مدیریت هوشیار — دستیار هوشمند حل سوال</b>\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"📊 وضعیت: {status_txt}\n"
        f"🧠 ارائه‌دهنده: <code>{PROVIDER_LABELS.get(cfg['provider'], cfg['provider'])}</code>\n"
        f"🧩 مدل: <code>{cfg['model']}</code>\n"
        f"🔑 API Key: <code>{_mask_key(cfg['api_key'])}</code>\n"
        f"👥 محدودیت روزانه: {limit_txt}\n"
        f"🧠 عمقِ استدلال: {'🔥 بالا (High Thinking)' if cfg['thinking'] == 'high' else 'خودکار (پیش‌فرضِ مدل)'}\n\n"
        "<i>دانشجویان با دکمه‌ی «🤖 هوشیار» در منوی اصلی، سوال متنی، عکس، "
        "PDF یا حتی ویس می‌فرستن و طبق همین تنظیمات جواب می‌گیرن.</i>"
    )
    keyboard = [
        [InlineKeyboardButton(toggle_txt, callback_data='ai:toggle')],
        [InlineKeyboardButton("🔁 تغییر ارائه‌دهنده (Gemini/OpenRouter)", callback_data='ai:pick_provider')],
        [InlineKeyboardButton("🔑 تنظیم / تغییر API Key", callback_data='ai:set_key')],
        [InlineKeyboardButton("🧩 انتخاب مدل", callback_data='ai:pick_model')],
        [InlineKeyboardButton("👥 محدودیت روزانه هر کاربر", callback_data='ai:set_limit')],
        [InlineKeyboardButton("🧠 عمقِ استدلال (Thinking)", callback_data='ai:toggle_thinking')],
        [InlineKeyboardButton("💬 ویرایش دستور سیستمی", callback_data='ai:set_prompt')],
        [InlineKeyboardButton("🎭 پرسونا‌های ذخیره‌شده", callback_data='ai:personas')],
        [InlineKeyboardButton("📝 پیامِ حالتِ خاموش", callback_data='ai:set_disabled_msg')],
        [InlineKeyboardButton("📊 آمار مصرف", callback_data='ai:stats')],
        [InlineKeyboardButton("🔄 ریست سهمیه‌ی یک کاربر", callback_data='ai:reset_quota')],
        [
            InlineKeyboardButton("⛔ مسدودکردن کاربر", callback_data='ai:ban_search'),
            InlineKeyboardButton("📋 لیست مسدودشده‌ها", callback_data='ai:ban_list'),
        ],
        [InlineKeyboardButton("🚩 گزارش‌های اخیر", callback_data='ai:reports')],
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

    # ⚠️ فیکس باگ ناوبری: قبلاً وقتی مثلاً توی «ویرایش دستور سیستمی» بودی
    # و دکمه‌ی «❌ لغو» رو می‌زدی، فقط صفحه برمی‌گشت ولی mode توی
    # user_data پاک نمی‌شد — یعنی ربات هنوز منتظرِ متنِ جدید بود و پیامِ
    # بعدیت (حتی اگه دکمه‌ی کاملاً نامرتبط دیگه‌ای بود) به‌عنوان ورودیِ
    # همون حالت قبلی پردازش می‌شد. با پاک کردنِ mode همین‌جا (قبل از هر
    # اکشنی)، هر بار که روی هر دکمه‌ای توی این پنل بزنی، حالت‌های نیمه‌کاره
    # قبلی خودش پاک می‌شه؛ اکشن‌هایی که واقعاً به ورودی متنی نیاز دارن
    # (set_key/set_limit/set_prompt/set_model_custom/reset_quota) بلافاصله
    # همون‌جا mode مخصوص خودشون رو دوباره ست می‌کنن.
    context.user_data.pop('mode', None)

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
        await query.answer("✅ هوشیار فعال شد" if new_val else "✅ هوشیار غیرفعال شد", show_alert=True)
        await send_audit_log(
            context.bot, 'admin', 'مدیر ارشد', uid,
            "فعال‌سازی هوشیار" if new_val else "غیرفعال‌سازی هوشیار",
            module='AI', severity='HIGH', actor_role='مدیر ارشد',
        )
        await show_ai_main(query)
        return

    if action == 'pick_provider':
        kb = [[InlineKeyboardButton(label, callback_data=f'ai:set_provider:{key}')]
              for key, label in PROVIDER_LABELS.items()]
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')])
        await query.edit_message_text(
            "🔁 <b>انتخاب ارائه‌دهنده‌ی هوش مصنوعی</b>\n\n"
            "توجه: با عوض کردن ارائه‌دهنده باید API Key مخصوص همون رو هم "
            "دوباره تنظیم کنی (کلید Gemini با OpenRouter کار نمی‌کنه و برعکس).\n\n"
            "🟦 Gemini → کلید از aistudio.google.com/apikey\n"
            "🟪 OpenRouter → کلید از openrouter.ai/keys",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if action == 'set_provider':
        provider = parts[2] if len(parts) > 2 else ''
        if provider in PROVIDER_LABELS:
            await set_ai_setting('provider', provider)
            await set_ai_setting('model', '')  # ریست مدل روی پیش‌فرض همون ارائه‌دهنده
            await query.answer(f"✅ ارائه‌دهنده روی {PROVIDER_LABELS[provider]} تنظیم شد", show_alert=True)
        await show_ai_main(query)
        return

    if action == 'set_key':
        cfg = await get_ai_config()
        context.user_data['mode'] = 'ai_set_key'
        hint = (
            "aistudio.google.com/apikey" if cfg['provider'] == 'gemini'
            else "openrouter.ai/keys"
        )
        await query.edit_message_text(
            "🔑 <b>تنظیم API Key</b>\n\n"
            f"کلید API مربوط به «{PROVIDER_LABELS.get(cfg['provider'], cfg['provider'])}» رو بفرست "
            f"(از {hint}).\n\n"
            "<i>بلافاصله بعد از ذخیره، پیامت حذف می‌شه که جایی نمونه.</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='ai:main')]])
        )
        return

    if action == 'pick_model':
        cfg = await get_ai_config()
        presets = MODEL_PRESETS.get(cfg['provider'], [])
        kb = [[InlineKeyboardButton(label, callback_data=f'ai:set_model:{model_id}')]
              for model_id, label in presets]
        kb.append([InlineKeyboardButton("✏️ مدل سفارشی (تایپ دستی)", callback_data='ai:set_model_custom')])
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')])
        await query.edit_message_text(
            f"🧩 <b>انتخاب مدل — ارائه‌دهنده‌ی فعلی: {PROVIDER_LABELS.get(cfg['provider'], cfg['provider'])}</b>\n\n"
            "یکی از مدل‌های آماده رو انتخاب کن یا مدل سفارشی وارد کن:",
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

        # ⚠️ فیکس باگ «Message_too_long»: اگه ادمین قبلاً یه دستور سیستمیِ
        # خیلی طولانی ست کرده باشه، نمایش کاملش توی همین پیام از سقف ۴۰۹۶
        # کاراکتریِ تلگرام رد می‌شه و edit_message_text با خطا شکست می‌خوره
        # (که بعد به‌صورت «خطای ربات» به ادمین گزارش می‌شه). این‌جا متن رو
        # هم escape می‌کنیم (که کاراکترهای HTML مثل < و & پارس رو خراب نکنن)
        # و هم در صورت طولانی بودن، خلاصه‌ش می‌کنیم.
        raw_prompt = cfg['system_prompt'] or ''
        prompt_preview = _esc(raw_prompt)
        MAX_PREVIEW = 3000
        if len(prompt_preview) > MAX_PREVIEW:
            prompt_preview = (
                prompt_preview[:MAX_PREVIEW]
                + f"…\n\n<i>(متن کامل {len(raw_prompt)} کاراکتره؛ برای اینجا "
                "خلاصه شد ولی خودِ متنِ کامل ذخیره‌ست و همون استفاده می‌شه.)</i>"
            )

        await query.edit_message_text(
            "💬 <b>ویرایش دستور سیستمی (System Prompt)</b>\n\n"
            "این متن به هوش مصنوعی می‌گه چه نقشی داره و چطور جواب بده.\n\n"
            f"متن فعلی:\n<code>{prompt_preview}</code>\n\n"
            "متن جدید رو بفرست، یا کلمه‌ی «حذف» رو بفرست تا به پیش‌فرض برگرده.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='ai:main')]])
        )
        return

    if action == 'stats':
        cfg = await get_ai_config()
        stats = await db.ai_usage_stats()
        cost_today   = _estimate_cost(stats['tokens_today'], cfg['model'])
        cost_alltime = _estimate_cost(stats['tokens_alltime'], cfg['model'])
        lines = [
            "📊 <b>آمار مصرف هوشیار</b>\n━━━━━━━━━━━━━━━━\n",
            f"📅 امروز: <b>{stats['total_today']}</b> سوال از <b>{stats['users_today']}</b> کاربر"
            f" (~{stats['tokens_today']:,} توکن، تخمین هزینه: {cost_today})",
            f"📈 مجموع کل: <b>{stats['total_alltime']}</b> سوال از <b>{stats['users_alltime']}</b> کاربر"
            f" (~{stats['tokens_alltime']:,} توکن، تخمین هزینه: {cost_alltime})",
            f"\n<i>💡 تخمینِ هزینه بر اساسِ مدلِ فعلی (<code>{_esc(cfg['model'])}</code>) و نرخِ Paid "
            "Tier حساب شده؛ اگه پروژه‌ت روی Free Tier باشه، هزینه‌ی واقعی صفره.</i>",
        ]
        if stats['top_today']:
            lines.append("\n🏆 پرمصرف‌ترین‌های امروز:")
            for name, u_id, cnt in stats['top_today']:
                lines.append(f"• {_esc(str(name))} (<code>{u_id}</code>): {cnt} سوال")
        if stats['top_alltime']:
            lines.append("\n🏆 پرمصرف‌ترین‌ها (کل زمان):")
            for name, u_id, cnt in stats['top_alltime']:
                lines.append(f"• {_esc(str(name))} (<code>{u_id}</code>): {cnt} سوال")
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')]])
        )
        return

    if action == 'reset_quota':
        context.user_data['mode'] = 'ai_reset_quota_search'
        await query.edit_message_text(
            "🔄 <b>ریست سهمیه‌ی روزانه‌ی یک کاربر</b>\n\n"
            "آیدی عددی تلگرام، یوزرنیم یا اسمِ کاربر رو بفرست تا پیداش کنم.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='ai:main')]])
        )
        return

    if action == 'do_reset_quota':
        target_uid = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        if not target_uid:
            await query.answer("⚠️ شناسه‌ی کاربر نامعتبره.", show_alert=True)
            return
        await db.update_user(target_uid, {
            'ai_usage_count': 0,
            'ai_usage_date':  datetime.now().strftime('%Y-%m-%d'),
        })
        await query.answer("✅ سهمیه‌ی امروزِ این کاربر ریست شد.", show_alert=True)
        await send_audit_log(
            context.bot, 'admin', 'مدیر ارشد', uid,
            f"ریست سهمیه‌ی روزانه‌ی هوشیار برای کاربر {target_uid}",
            module='AI', severity='MEDIUM', actor_role='مدیر ارشد',
        )
        await show_ai_main(query)
        return

    if action == 'toggle_thinking':
        cfg = await get_ai_config()
        new_val = 'auto' if cfg['thinking'] == 'high' else 'high'
        await set_ai_setting('thinking', new_val)
        await query.answer(
            "🔥 عمقِ استدلال روی «بالا» تنظیم شد — جواب‌ها دقیق‌تر ولی کمی کندتر می‌شن."
            if new_val == 'high' else
            "✅ عمقِ استدلال روی «خودکار» (پیش‌فرضِ مدل) برگشت.",
            show_alert=True,
        )
        await show_ai_main(query)
        return

    if action == 'personas':
        cfg = await get_ai_config()
        personas = cfg['personas']
        names = list(personas.keys())
        context.user_data['ai_persona_list'] = names   # برای رفرنس دادن با ایندکس در دکمه‌های بعدی
        kb = []
        for i, name in enumerate(names):
            kb.append([
                InlineKeyboardButton(f"▶️ {name}", callback_data=f'ai:load_persona:{i}'),
                InlineKeyboardButton("🗑", callback_data=f'ai:del_persona:{i}'),
            ])
        kb.append([InlineKeyboardButton("💾 ذخیره‌ی پرامپتِ فعلی به‌عنوانِ پرسونای جدید", callback_data='ai:save_persona')])
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')])
        text = (
            "🎭 <b>پرسونا‌های ذخیره‌شده</b>\n\n"
            "چند سبکِ شخصیتی/دستورِ سیستمی می‌تونی از قبل ذخیره کنی و سریع "
            "بینشون سوییچ کنی — مثلاً «رسمی و درسی» و «خودمونی و باحال» — "
            "بدون اینکه هر بار کل متن رو دوباره تایپ کنی."
        )
        if not names:
            text += "\n\n<i>هنوز پرسونایی ذخیره نشده.</i>"
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
        return

    if action == 'save_persona':
        context.user_data['mode'] = 'ai_save_persona_name'
        await query.edit_message_text(
            "💾 <b>ذخیره‌ی پرسونای جدید</b>\n\n"
            "یه اسم کوتاه براش بفرست (مثلاً «رسمی» یا «باحال»). "
            "دستورِ سیستمیِ *فعلی* (همونی که الان فعاله) با همین اسم ذخیره می‌شه.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='ai:personas')]])
        )
        return

    if action in ('load_persona', 'del_persona'):
        idx_str = parts[2] if len(parts) > 2 else ''
        names = context.user_data.get('ai_persona_list', [])
        if not idx_str.isdigit() or int(idx_str) >= len(names):
            await query.answer("⚠️ این لیست منقضی شده، دوباره وارد «پرسونا‌ها» شو.", show_alert=True)
            return
        name = names[int(idx_str)]
        cfg = await get_ai_config()
        if action == 'load_persona':
            prompt = cfg['personas'].get(name)
            if prompt:
                await set_ai_setting('system_prompt', prompt)
                await query.answer(f"✅ پرسونای «{name}» فعال شد.", show_alert=True)
                await send_audit_log(
                    context.bot, 'admin', 'مدیر ارشد', uid,
                    f"سوییچ به پرسونای «{name}»", module='AI', severity='LOW', actor_role='مدیر ارشد',
                )
        else:
            await delete_persona(name)
            await query.answer(f"🗑 پرسونای «{name}» حذف شد.", show_alert=True)
        await show_ai_main(query)
        return

    if action == 'set_disabled_msg':
        context.user_data['mode'] = 'ai_set_disabled_msg'
        cfg = await get_ai_config()
        current = cfg['disabled_message'] or DEFAULT_DISABLED_MSG
        await query.edit_message_text(
            "📝 <b>پیامِ حالتِ خاموش</b>\n\n"
            "وقتی هوشیار غیرفعاله، دانشجو به‌جایِ پیامِ پیش‌فرض این متن رو می‌بینه.\n\n"
            f"متنِ فعلی:\n<code>{_esc(current)}</code>\n\n"
            "متنِ جدید رو بفرست، یا «حذف» برای برگشتن به پیش‌فرض.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='ai:main')]])
        )
        return

    if action == 'ban_search':
        context.user_data['mode'] = 'ai_ban_search'
        await query.edit_message_text(
            "⛔ <b>مسدودکردن / رفعِ مسدودیتِ یک کاربر از هوشیار</b>\n\n"
            "این جدا از بلاک‌کردنِ کاملِ رباته — کاربر بقیه‌ی امکاناتِ ربات "
            "رو عادی داره، فقط نمی‌تونه از هوشیار سوال بپرسه.\n\n"
            "آیدی عددی، یوزرنیم یا اسمِ کاربر رو بفرست تا پیداش کنم.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data='ai:main')]])
        )
        return

    if action == 'do_ban':
        target_uid = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        new_state = parts[3] == '1' if len(parts) > 3 else None
        if target_uid is None or new_state is None:
            await query.answer("⚠️ درخواست نامعتبره.", show_alert=True)
            return
        await db.ai_set_banned(target_uid, new_state)
        await query.answer(
            "⛔ کاربر مسدود شد." if new_state else "✅ مسدودیتِ کاربر برداشته شد.",
            show_alert=True,
        )
        await send_audit_log(
            context.bot, 'admin', 'مدیر ارشد', uid,
            f"{'مسدودکردن' if new_state else 'رفعِ مسدودیتِ'} کاربر {target_uid} از هوشیار",
            module='AI', severity='MEDIUM', actor_role='مدیر ارشد',
        )
        await show_ai_main(query)
        return

    if action == 'ban_list':
        banned = await db.ai_list_banned()
        if not banned:
            text = "📋 هیچ کاربری الان مسدود نیست."
            kb = [[InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')]]
        else:
            text = "📋 <b>کاربرهای مسدودشده از هوشیار</b>\n\nروی هرکدوم بزن تا رفعِ مسدودیت بشه:"
            kb = [
                [InlineKeyboardButton(f"✅ رفع مسدودیت: {u.get('name') or u.get('user_id')}",
                                       callback_data=f"ai:do_ban:{u.get('user_id')}:0")]
                for u in banned
            ]
            kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')])
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))
        return

    if action == 'reports':
        reports = await db.ai_recent_reports(limit=10)
        if not reports:
            text = "🚩 هنوز هیچ گزارشی ثبت نشده."
        else:
            lines = ["🚩 <b>۱۰ گزارشِ اخیر</b>\n━━━━━━━━━━━━━━━━"]
            for r in reports:
                when = r.get('created_at')
                when_txt = when.strftime('%Y-%m-%d %H:%M') if when else '—'
                lines.append(
                    f"\n👤 {_esc(str(r.get('name')))} (<code>{r.get('user_id')}</code>) — {when_txt}\n"
                    f"❓ {_esc((r.get('question') or '')[:200])}\n"
                    f"🤖 {_esc((r.get('answer') or '')[:300])}"
                )
            text = "\n".join(lines)
            if len(text) > 3800:
                text = text[:3800] + "\n…"
        await query.edit_message_text(
            text, parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')]])
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
            answer, tokens = await ask_ai(text="فقط با کلمه‌ی «سلام» جواب بده تا تستِ اتصال انجام بشه.")
            await query.edit_message_text(
                f"✅ اتصال موفق بود. (~{tokens} توکن مصرف شد)\n\nپاسخ نمونه:\n{_esc(answer[:300])}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')]])
            )
        except AIError as e:
            await query.edit_message_text(
                f"❌ تست ناموفق:\n{_esc(str(e))}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')]])
            )
        except Exception as e:
            logger.exception("AI test failed")
            await query.edit_message_text(
                f"❌ خطای غیرمنتظره: {_esc(str(e))}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='ai:main')]])
            )
        return


async def ai_admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ورودی متنی حالت‌های تنظیمات هوشیار (فقط ادمین ارشد)."""
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
            "حالا از پنل هوشیار دکمه‌ی «فعال کردن» رو بزن تا برای کاربرها فعال بشه."
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

    if mode == 'ai_reset_quota_search':
        context.user_data.pop('mode', None)
        results = await db.search_users(text)
        if not results:
            await update.message.reply_text("❌ کاربری با این مشخصات پیدا نشد.")
            return
        kb = [
            [InlineKeyboardButton(
                f"{u.get('name') or 'بدون نام'} — {u.get('user_id')}",
                callback_data=f"ai:do_reset_quota:{u.get('user_id')}",
            )]
            for u in results[:10]
        ]
        kb.append([InlineKeyboardButton("❌ لغو", callback_data='ai:main')])
        await update.message.reply_text(
            "یکی رو انتخاب کن تا سهمیه‌ی امروزش ریست بشه:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if mode == 'ai_save_persona_name':
        context.user_data.pop('mode', None)
        if not text:
            await update.message.reply_text("⚠️ اسم نمی‌تونه خالی باشه.")
            return
        cfg = await get_ai_config()
        await save_persona(text, cfg['system_prompt'])
        await update.message.reply_text(f"✅ پرسونای «{text[:40]}» با دستور سیستمیِ فعلی ذخیره شد.")
        return

    if mode == 'ai_set_disabled_msg':
        context.user_data.pop('mode', None)
        if text in ('حذف', 'reset', 'پیش‌فرض', 'پیشفرض'):
            await set_ai_setting('disabled_message', '')
            await update.message.reply_text("✅ پیامِ حالتِ خاموش به پیش‌فرض برگشت.")
        else:
            await set_ai_setting('disabled_message', text)
            await update.message.reply_text("✅ پیامِ حالتِ خاموش ذخیره شد.")
        return

    if mode == 'ai_ban_search':
        context.user_data.pop('mode', None)
        results = await db.search_users(text)
        if not results:
            await update.message.reply_text("❌ کاربری با این مشخصات پیدا نشد.")
            return
        kb = []
        for u in results[:10]:
            is_banned = bool(u.get('ai_banned'))
            label = f"{'✅ رفعِ مسدودیتِ' if is_banned else '⛔ مسدودکردنِ'} {u.get('name') or 'بدون نام'} — {u.get('user_id')}"
            kb.append([InlineKeyboardButton(
                label, callback_data=f"ai:do_ban:{u.get('user_id')}:{0 if is_banned else 1}",
            )])
        kb.append([InlineKeyboardButton("❌ لغو", callback_data='ai:main')])
        await update.message.reply_text("یکی رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(kb))
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

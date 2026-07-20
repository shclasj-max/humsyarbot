"""
🤖 AiHums — موتور هوش مصنوعی حل سوالات درسی (متن/عکس)
  ✅ هیچ‌چیز هاردکد نیست: کلید API، ارائه‌دهنده، مدل، محدودیت روزانه و
     دستور سیستمی همگی از bot_settings (پنل ادمین → ai_admin.py) خوانده
     می‌شوند.
  ✅ معماری چندارائه‌دهنده: برای اضافه‌کردن یک AI دیگر (مثلاً OpenRouter/
     OpenAI) فقط یک تابع جدید به PROVIDERS اضافه می‌شود — بقیه‌ی کد و
     پنل ادمین دست‌نخورده باقی می‌ماند.
  ✅ محدودیت روزانه‌ی سوال، به‌ازای هر کاربر (روی خودِ سند کاربر در
     دیتابیس ذخیره می‌شود؛ نیازی به کالکشن جدید نیست).
"""
import os
import base64
import logging
from datetime import datetime

import httpx
from telegram import Update
from telegram.ext import ContextTypes

from database import db

logger   = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# ══════════════════════════════════════════════════
#  پیش‌فرض‌ها — فقط وقتی استفاده می‌شن که ادمین هنوز چیزی ست نکرده
# ══════════════════════════════════════════════════
DEFAULT_MODELS = {
    'gemini':     'gemini-2.5-flash',
    'openrouter': 'google/gemma-4-31b-it:free',
}
DEFAULT_MODEL  = DEFAULT_MODELS['gemini']   # برای سازگاری با کدهای قبلی
DEFAULT_LIMIT  = 15   # سقف روزانه‌ی هر کاربر عادی؛ 0 = نامحدود
DEFAULT_PROMPT = (
    "تو «هوشیار» هستی، دستیار هوش مصنوعیِ ربات همیار (Humsyar) برای "
    "دانشجویان دانشگاه علوم پزشکی هرمزگان. کارت کمک به حل سوالات درسی "
    "پزشکی و علوم پایه است — چه به‌صورت متن، چه عکسِ سوال.\n\n"
    "قوانین پاسخ‌دهی:\n"
    "۱. همیشه به فارسی و خلاصه جواب بده.\n"
    "۲. اگر سوال تستی چندگزینه‌ای است، ابتدا گزینه‌ی درست را با شماره‌اش "
    "مشخص کن، بعد در ۲ تا ۴ خط دلیلش را توضیح بده.\n"
    "۳. اگر عکس ناخوانا یا سوال مبهم بود، حدس نزن — صادقانه بگو که "
    "متوجه نشدی و از کاربر بخواه واضح‌تر بفرستد.\n"
    "۴. برای نکات حساس پزشکی (مثل دوز دارو) با احتیاط پاسخ بده و "
    "همیشه یادآوری کن که باید با منبع درسی یا استاد چک شود.\n"
    "۵. اگر سوالی درباره‌ی خودِ ربات همیار پرسیده شد نه یک سوال درسی، "
    "صادقانه بگو که فعلاً فقط برای حل سوالات درسی تنظیم شده‌ای."
)


# ══════════════════════════════════════════════════
#  خطاهای اختصاصی
# ══════════════════════════════════════════════════
class AIError(Exception):
    """خطای قابل‌نمایش به کاربر/ادمین."""


class AIQuotaError(AIError):
    pass


class AIConfigError(AIError):
    pass


# ══════════════════════════════════════════════════
#  تنظیمات — همه از bot_settings (کلید-مقدار عمومی دیتابیس)
# ══════════════════════════════════════════════════

async def get_ai_config() -> dict:
    raw = await db.get_settings_by_prefix('ai_')
    provider = raw.get('ai_provider', 'gemini')
    return {
        'enabled':       bool(raw.get('ai_enabled', False)),
        'provider':      provider,
        'api_key':       raw.get('ai_api_key', ''),
        'model':         raw.get('ai_model') or DEFAULT_MODELS.get(provider, DEFAULT_MODEL),
        'daily_limit':   int(raw.get('ai_daily_limit', DEFAULT_LIMIT) or 0),
        'system_prompt': raw.get('ai_system_prompt', DEFAULT_PROMPT),
    }


async def set_ai_setting(key: str, value) -> None:
    await db.set_setting(f'ai_{key}', value)


# ══════════════════════════════════════════════════
#  ارائه‌دهنده‌ها (Providers)
#  برای افزودن یک AI جدید: یک تابع async با همین امضا بنویس و در
#  دیکشنری PROVIDERS پایین ثبتش کن. سپس از پنل ادمین می‌شود روی
#  provider جدید سوییچ کرد — بدون تغییر جای دیگری از کد.
# ══════════════════════════════════════════════════

async def _call_gemini(api_key: str, model: str, system_prompt: str,
                        text: str = None, image_bytes: bytes = None,
                        image_mime: str = 'image/jpeg', **_) -> str:
    # FIX: از اواسط ۲۰۲۶ گوگل کلیدهای جدید با پیشوند «AQ.» صادر می‌کند که
    # با روش قدیمیِ فرستادن کلید در URL (?key=...) کار نمی‌کنند و ۴۰۴/۴۰۳
    # برمی‌گردانند. روش رسمی و سازگار با هر دو فرمت (چه AIzaSy... قدیمی،
    # چه AQ.... جدید) فرستادن کلید در هدر x-goog-api-key است.
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        'Content-Type':   'application/json',
        'x-goog-api-key': api_key,
    }

    parts = []
    if image_bytes:
        parts.append({
            'inline_data': {
                'mime_type': image_mime,
                'data': base64.b64encode(image_bytes).decode('utf-8'),
            }
        })
    if text:
        parts.append({'text': text})
    if not parts:
        parts.append({'text': 'کاربر متن یا عکسی ارسال نکرده.'})

    payload = {
        'system_instruction': {'parts': [{'text': system_prompt}]},
        'contents': [{'role': 'user', 'parts': parts}],
        'generationConfig': {'temperature': 0.3, 'maxOutputTokens': 1024},
    }

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException:
        raise AIError("سرویس هوش مصنوعی دیر جواب داد (timeout) — دوباره امتحان کن.")
    except httpx.HTTPError as e:
        raise AIError(f"خطا در اتصال به سرویس هوش مصنوعی: {e}")

    if resp.status_code == 429:
        raise AIQuotaError("سقف رایگان API برای امروز پر شده — کمی بعد دوباره امتحان کن.")
    if resp.status_code in (400, 401, 403, 404):
        raise AIConfigError(
            "کلید API نامعتبره، مدل اشتباهه یا دسترسی لازم رو نداره — ادمین باید از پنل "
            f"AiHums تنظیماتش رو چک کنه. (کد خطا: {resp.status_code})"
        )
    if resp.status_code >= 500:
        raise AIError("سرویس هوش مصنوعی موقتاً در دسترس نیست — کمی بعد دوباره امتحان کن.")

    try:
        resp.raise_for_status()
        data = resp.json()
        return data['candidates'][0]['content']['parts'][0]['text'].strip()
    except (KeyError, IndexError, ValueError):
        reason = ''
        try:
            reason = data.get('candidates', [{}])[0].get('finishReason', '')
        except Exception:
            pass
        raise AIConfigError(f"مدل پاسخی برنگردوند{f' (دلیل: {reason})' if reason else ''}.")


async def _call_openrouter(api_key: str, model: str, system_prompt: str,
                            text: str = None, image_bytes: bytes = None,
                            image_mime: str = 'image/jpeg', **_) -> str:
    """
    ارائه‌دهنده‌ی جایگزین رایگان (openrouter.ai) — مستقل از مشکل فعلی
    کلیدهای AQ. گوگل. برای گرفتن کلید: openrouter.ai/keys (بدون کارت).
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type':  'application/json',
    }

    content = []
    if text:
        content.append({'type': 'text', 'text': text})
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode('utf-8')
        content.append({
            'type': 'image_url',
            'image_url': {'url': f'data:{image_mime};base64,{b64}'},
        })
    if not content:
        content.append({'type': 'text', 'text': 'کاربر متن یا عکسی ارسال نکرده.'})

    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': content},
        ],
        'temperature': 0.3,
        'max_tokens': 1024,
    }

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException:
        raise AIError("سرویس هوش مصنوعی دیر جواب داد (timeout) — دوباره امتحان کن.")
    except httpx.HTTPError as e:
        raise AIError(f"خطا در اتصال به سرویس هوش مصنوعی: {e}")

    if resp.status_code == 429:
        raise AIQuotaError("سقف رایگان API برای امروز پر شده — کمی بعد دوباره امتحان کن.")
    if resp.status_code in (400, 401, 403, 404):
        raise AIConfigError(
            "کلید API نامعتبره، مدل اشتباهه یا دسترسی لازم رو نداره — ادمین باید از پنل "
            f"AiHums تنظیماتش رو چک کنه. (کد خطا: {resp.status_code})"
        )
    if resp.status_code >= 500:
        raise AIError("سرویس هوش مصنوعی موقتاً در دسترس نیست — کمی بعد دوباره امتحان کن.")

    try:
        resp.raise_for_status()
        data = resp.json()
        return data['choices'][0]['message']['content'].strip()
    except (KeyError, IndexError, ValueError):
        raise AIConfigError("مدل پاسخی برنگردوند — احتمالاً مدل انتخاب‌شده الان در دسترس نیست.")


PROVIDERS = {
    'gemini':     _call_gemini,
    'openrouter': _call_openrouter,
    # نمونه برای بعداً — فقط یک تابع مثل _call_gemini/_call_openrouter بنویس
    # و اینجا اضافه کن:
    # 'openai': _call_openai,
}


async def ask_ai(text: str = None, image_bytes: bytes = None,
                  image_mime: str = 'image/jpeg') -> str:
    cfg = await get_ai_config()
    if not cfg['enabled']:
        raise AIConfigError("بخش هوش مصنوعی فعلاً توسط مدیریت غیرفعال است.")
    if not cfg['api_key']:
        raise AIConfigError("هنوز کلید API توسط ادمین تنظیم نشده.")

    fn = PROVIDERS.get(cfg['provider'])
    if not fn:
        raise AIConfigError(f"ارائه‌دهنده‌ی «{cfg['provider']}» پشتیبانی نمی‌شود.")

    return await fn(
        api_key=cfg['api_key'], model=cfg['model'],
        system_prompt=cfg['system_prompt'],
        text=text, image_bytes=image_bytes, image_mime=image_mime,
    )


# ══════════════════════════════════════════════════
#  محدودیت روزانه‌ی هر کاربر
# ══════════════════════════════════════════════════

async def check_and_consume_quota(uid: int) -> tuple:
    """
    برمی‌گرداند (allowed, used_after, limit).
    ادمین ارشد همیشه نامحدود است؛ daily_limit=0 یعنی نامحدود برای همه.
    """
    cfg   = await get_ai_config()
    limit = cfg['daily_limit']
    if uid == ADMIN_ID or limit <= 0:
        return True, 0, 0

    user  = await db.get_user(uid) or {}
    today = datetime.now().strftime('%Y-%m-%d')
    used  = user.get('ai_usage_count', 0) if user.get('ai_usage_date') == today else 0

    if used >= limit:
        return False, used, limit

    await db.update_user(uid, {'ai_usage_date': today, 'ai_usage_count': used + 1})
    return True, used + 1, limit


# ══════════════════════════════════════════════════
#  فلوی کاربر — دکمه‌ی «🤖 AiHums» در منوی اصلی
# ══════════════════════════════════════════════════

async def show_ai_intro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cfg = await get_ai_config()

    if not cfg['enabled']:
        await update.message.reply_text(
            "🤖 بخش «AiHums» فعلاً توسط مدیریت غیرفعال است. بعداً دوباره سر بزن."
        )
        return

    context.user_data['mode'] = 'ai_query'

    limit = cfg['daily_limit']
    if uid == ADMIN_ID or limit <= 0:
        quota_line = "🔓 بدون محدودیت روزانه"
    else:
        user  = await db.get_user(uid) or {}
        today = datetime.now().strftime('%Y-%m-%d')
        used  = user.get('ai_usage_count', 0) if user.get('ai_usage_date') == today else 0
        quota_line = f"📊 امروز: {used}/{limit} سوال استفاده شده"

    await update.message.reply_text(
        "🤖 <b>AiHums — دستیار هوشمند حل سوال</b>\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "سوال درسی‌تو بفرست:\n"
        "📝 متن سوال رو تایپ کن\n"
        "📷 یا عکس سوال رو بفرست (می‌تونی زیرش توضیح هم بنویسی)\n\n"
        f"{quota_line}\n\n"
        "⚠️ پاسخ‌ها توسط هوش مصنوعی تولید می‌شن و ممکنه خطا داشته باشن — "
        "حتماً با منبع درسی/استاد چک کن.\n\n"
        "برای خروج از این حالت، هر دکمه‌ی دیگه از منو رو بزن.",
        parse_mode='HTML'
    )


def _footer(limit: int, used: int) -> str:
    if not limit:
        return ""
    return f"\n\n📊 {used}/{limit} سوال امروز"


async def handle_ai_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = (update.message.text or '').strip()
    if not text:
        return

    cfg = await get_ai_config()
    if not cfg['enabled']:
        context.user_data.pop('mode', None)
        await update.message.reply_text("🤖 بخش هوش مصنوعی توسط مدیریت غیرفعال شد.")
        return

    allowed, used, limit = await check_and_consume_quota(uid)
    if not allowed:
        await update.message.reply_text(
            f"⛔️ سقف روزانه‌ی سوال از AiHums تموم شده ({used}/{limit}).\n"
            "فردا دوباره امتحان کن."
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    try:
        answer = await ask_ai(text=text)
        await update.message.reply_text(f"🤖 {answer}{_footer(limit, used)}")
    except AIError as e:
        await update.message.reply_text(f"⚠️ {e}")
    except Exception:
        logger.exception("AI text error")
        await update.message.reply_text("⚠️ مشکلی در ارتباط با سرویس هوش مصنوعی پیش اومد، دوباره امتحان کن.")


async def handle_ai_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    cfg = await get_ai_config()
    if not cfg['enabled']:
        context.user_data.pop('mode', None)
        await update.message.reply_text("🤖 بخش هوش مصنوعی توسط مدیریت غیرفعال شد.")
        return

    if update.message.photo:
        tg_file = await update.message.photo[-1].get_file()
        mime    = 'image/jpeg'
    elif update.message.document and (update.message.document.mime_type or '').startswith('image/'):
        tg_file = await update.message.document.get_file()
        mime    = update.message.document.mime_type
    else:
        return  # نوع فایل پشتیبانی‌نشده — نادیده گرفته می‌شود

    allowed, used, limit = await check_and_consume_quota(uid)
    if not allowed:
        await update.message.reply_text(
            f"⛔️ سقف روزانه‌ی سوال از AiHums تموم شده ({used}/{limit}).\n"
            "فردا دوباره امتحان کن."
        )
        return

    image_bytes = bytes(await tg_file.download_as_bytearray())
    caption     = (update.message.caption or '').strip() or None

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    try:
        answer = await ask_ai(text=caption, image_bytes=image_bytes, image_mime=mime)
        await update.message.reply_text(f"🤖 {answer}{_footer(limit, used)}")
    except AIError as e:
        await update.message.reply_text(f"⚠️ {e}")
    except Exception:
        logger.exception("AI photo error")
        await update.message.reply_text("⚠️ مشکلی در ارتباط با سرویس هوش مصنوعی پیش اومد، دوباره امتحان کن.")

"""
🤖 هوشیار — موتور هوش مصنوعی حل سوالات درسی (متن/عکس)
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
import random
import asyncio
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
    "تو «هوشیار» هستی؛ دستیار هوش مصنوعیِ ربات هامزیار (Humsyar) برای "
    "دانشجویان دانشگاه علوم پزشکی هرمزگان. یه دستیار باحال، خودمونی و "
    "بامعرفتی که هم می‌تونه احوال‌پرسی کنه و گپ بزنه، هم وقتی پای درس "
    "وسط باشه حسابی حرفه‌ای و دقیق جواب بده.\n\n"

    "🎯 شخصیت و لحن\n"
    "- خودمونی، گرم و بامزه باش؛ مثل یه هم‌کلاسیِ باهوش‌تر که همیشه "
    "حاضر به کمکه، نه یه ربات خشکِ اداری.\n"
    "- اگه کاربر فقط سلام کرد، حال‌پرسی کرد یا خواست گپ بزنه، راحت و "
    "طبیعی جواب بده — لازم نیست هر پیام رو تبدیل به یه درس کنی.\n"
    "- می‌تونی توی موضوعات مختلف (نه فقط پزشکی) هم باهاش حرف بزنی؛ "
    "کنجکاو و بامزه باش، ولی همیشه صادق بمون و چیزی رو که نمی‌دونی با "
    "اطمینانِ دروغین جا نزن.\n"
    "- اگه سوالی درباره‌ی خودِ ربات هامزیار پرسید، خودمونی توضیح بده که "
    "برای اطلاعات کامل‌تر ربات بهتره از منوی اصلی یا پشتیبانی کمک "
    "بگیره.\n\n"

    "📚 وقتی پای سوال درسی وسطه (متن یا عکس)\n"
    "۱. برای تست چندگزینه‌ای:\n"
    "   • خط اول: «✅ گزینه‌ی X صحیح است»\n"
    "   • بعدش در ۲ تا ۴ خط، دلیل علمی‌اش رو دقیق و بی‌حاشیه بگو\n"
    "   • اگه لازم بود، یه اشاره‌ی کوتاه هم به چرایی رد شدن گزینه‌های "
    "پرتکرارِ اشتباه بکن\n"
    "۲. برای سوال باز/تشریحی: پاسخ رو مرتب، خلاصه و در حد ۴ تا ۶ خط "
    "بده؛ اگه فهرست‌وار روشن‌تره از لیست کوتاه استفاده کن.\n"
    "این قالب‌ها یه راهنمان، نه یه چارچوب سفت‌وسخت — اگه سوال طوریه که "
    "یه توضیح متفاوت بهتر جواب می‌ده، همون‌جوری برو جلو.\n\n"

    "🔍 صداقت علمی (این بخش مهمه، حتی توی لحن راحت)\n"
    "- هیچ‌وقت حدس رو جای دونستن جا نزن. اگه عکس نامفهوم بود یا سوال "
    "مبهم بود، رک بگو متوجه نشدی و بخواه واضح‌تر بفرسته.\n"
    "- اگه بین منابع/گایدلاین‌های رایج اختلاف‌نظر هست، بگو که اختلاف‌نظر "
    "وجود داره، به‌جای این‌که یکی رو قطعی جا بزنی.\n"
    "- اسم کتاب، منبع یا آمار رو الکی نساز؛ اگه مطمئن نیستی از کجا "
    "اومده، اصلاً اشاره نکن.\n\n"

    "⚕️ یه‌ذره احتیاط پزشکی\n"
    "- برای چیزای حساس (دوز دارو، مقادیر مرزی آزمایشگاهی، تصمیم "
    "درمانی) با احتیاط جواب بده و در آخر یه یادآوری کوچیک بذار که با "
    "منبع درسی یا استاد چک بشه.\n"
    "- این یه ابزار کمک‌آموزشیه، نه جایگزین مشاوره‌ی پزشکیِ واقعی برای "
    "بیمار واقعی.\n\n"

    "🚫 فقط همین یکی مهمه\n"
    "- هیچ‌وقت توی پاسخت متن‌های فنیِ داخلی، برچسب ارزیابی/دسته‌بندیِ "
    "ایمنی یا فراداده نشون نده — فقط همون جوابی که کاربر منتظرشه."
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
    if resp.status_code == 402:
        raise AIConfigError(
            "خطای ۴۰۲ (نیاز به پرداخت) از گوگل — پروژه‌ی Google Cloud این کلید "
            "نیاز به فعال‌سازی Billing داره یا در منطقه‌ی شما ردهٔ رایگان در "
            "دسترس نیست."
        )
    if resp.status_code in (400, 401, 403, 404):
        raise AIConfigError(
            "کلید API نامعتبره، مدل اشتباهه یا دسترسی لازم رو نداره — ادمین باید از پنل "
            f"هوشیار تنظیماتش رو چک کنه. (کد خطا: {resp.status_code})"
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
    if resp.status_code == 402:
        raise AIConfigError(
            "خطای ۴۰۲ (نیاز به پرداخت) از OpenRouter. معمولاً یکی از این‌هاست:\n"
            "۱) نام مدل درست/کامل نیست — باید دقیقاً google/gemma-4-31b-it:free "
            "باشه (با google/ اول و :free آخرش)\n"
            "۲) موجودی حساب openrouter.ai/settings/credits منفیه\n"
            "۳) توی تنظیمات اکانت OpenRouter، Provider ی که این مدل رایگان رو "
            "می‌ده Ignore/بلاک شده"
        )
    if resp.status_code in (400, 401, 403, 404):
        raise AIConfigError(
            "کلید API نامعتبره، مدل اشتباهه یا دسترسی لازم رو نداره — ادمین باید از پنل "
            f"هوشیار تنظیماتش رو چک کنه. (کد خطا: {resp.status_code})"
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

    answer = await fn(
        api_key=cfg['api_key'], model=cfg['model'],
        system_prompt=cfg['system_prompt'],
        text=text, image_bytes=image_bytes, image_mime=image_mime,
    )
    _guard_against_meta_leak(answer, cfg)
    return answer


# نشانه‌های شناخته‌شده‌ی «نشتِ فراداده»: بعضی مدل‌های رایگان (مخصوصاً وقتی
# با روتر خودکارِ «openrouter/free» یک مدل نامناسب/کلاسیفایر انتخاب می‌شود)
# به‌جای پاسخِ واقعی، برچسب‌های داخلیِ ارزیابیِ ایمنی را برمی‌گردانند، مثل:
#   "User Safety: safe / Response Safety: unsafe / Safety Categories: ..."
# این خروجی برای دانشجو کاملاً بی‌معنی و گمراه‌کننده است، پس به‌جای نمایش
# مستقیم آن، خطای شفاف نشان می‌دهیم تا ادمین مدل را عوض کند.
_META_LEAK_MARKERS = (
    'user safety', 'response safety', 'safety categories',
    'safety category', 'content policy violation', 'moderation result',
)


def _guard_against_meta_leak(answer: str, cfg: dict) -> None:
    lowered = (answer or '').lower()
    if any(marker in lowered for marker in _META_LEAK_MARKERS):
        hint = (
            "اگه از OpenRouter استفاده می‌کنی و مدلت روی «انتخاب خودکار» "
            "(openrouter/free) تنظیمه، از پنل ادمین یه مدل مشخص مثل "
            "google/gemma-4-31b-it:free رو انتخاب کن."
            if cfg.get('provider') == 'openrouter' else
            "مدل انتخابی خروجی نامناسب برگردوند؛ از پنل ادمین مدل رو عوض کن."
        )
        raise AIConfigError(
            f"مدل به‌جای پاسخِ درسی، یک خروجیِ فنیِ نامرتبط برگردوند. {hint}"
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
#  فلوی کاربر — دکمه‌ی «🤖 هوشیار» در منوی اصلی
# ══════════════════════════════════════════════════

async def show_ai_intro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cfg = await get_ai_config()

    if not cfg['enabled']:
        await update.message.reply_text(
            "🤖 بخش «هوشیار» فعلاً توسط مدیریت غیرفعال است. بعداً دوباره سر بزن."
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
        "🤖 <b>هوشیار — دستیار هوشمند حل سوال</b>\n"
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


# ══════════════════════════════════════════════════
#  عبارت‌های بامزه‌ی «در حال فکر کردن» و «طول کشیدن»
#  هرچی جواب دیرتر بیاد، پیام یکی‌یکی عوض می‌شه و باحال‌تر می‌شه 😄
# ══════════════════════════════════════════════════
THINKING_PHRASES = [
    "💭 در حال فکر کردن...",
    "🧠 هوشیار داره رو سوالت مغز می‌ریزه...",
    "🔎 دارم سوالتو دقیق می‌خونم...",
    "⚡️ یه لحظه، دارم جوابتو آماده می‌کنم...",
    "📖 دارم می‌رم سراغ جواب...",
    "🚀 موشکِ فکر کردن پرتاب شد، منتظر بمون...",
    "🍿 بشین یه چیزی ببین، الان میام با جواب...",
]

STALL_PHRASES = [
    "🕵️‍♂️ هوشیار رفته کوچه‌پس‌کوچه‌های اینترنت دنبال جوابت بگرده...",
    "🤯 مخِ هوشیار یه لحظه هنگید، یه دقه صبر کن 😂",
    "⏳ ویت‌ا‌مینت (wait a minute)... دارم روش کار می‌کنم",
    "😎 صبر کن رفیق، الان بهت میگم...",
    "🥹 عزیزم بذار یه‌کم فکر کنم...",
    "📚 دارم کتابای قطور رو ورق می‌زنم، یه لحظه صبر کن...",
    "🧩 دارم تیکه‌های جواب رو کنار هم می‌چینم...",
    "☕️ یه چایی بریز، دارم رو جوابت کار می‌کنم...",
    "🌀 مغزم داره لود می‌شه... ۹۹٪ ... یه‌کم دیگه مونده",
    "🔬 دارم زیر ذره‌بین بررسیش می‌کنم، صبور باش...",
    "🛰 دارم از فضا سیگنال جواب رو می‌گیرم، یه لحظه...",
    "🎯 دقیقاً دارم رو نشونه می‌رم، چند لحظه‌ی دیگه می‌رسم...",
    "🐌 اینترنتم امروز یه‌کم تنبله، ولی دارم میام...",
    "🧙‍♂️ داره یه طلسمِ علمی رو می‌خونم، یه ثانیه...",
    "🍃 نفس عمیق بکش، جوابت داره می‌رسه...",
    "😵‍💫 اوه اوه سوالت باحاله‌ها، بذار درست فکر کنم...",
    "🕰 یه چرخِ کوچولو بزن، الان جوابتو در میارم...",
    "🥱 نه بابا خوابم نبرد، دارم فکر می‌کنم فقط 😄",
    "🍵 یه استکان چایی بخور تا من فکرامو جمع کنم...",
    "📡 آنتنام یه‌کم ضعیفه، دارم سیگنال جواب رو می‌گیرم...",
    "🧑‍🔬 دارم توی آزمایشگاه مغزم دنبالش می‌گردم...",
    "🐢 آروم‌آروم داریم می‌رسیم به جواب، صبور باش رفیق...",
    "🎲 تاس جواب رو انداختم، منتظر بمون ببینم چی میاد 😂",
    "🍔 بذار اول این لقمه فکرو قورت بدم، الان میام...",
    "🚦 چراغ فکر کردن سبز شد، دارم می‌رونم سمت جواب...",
    "🧵 دارم نخِ جواب رو از کلاف درسا در میارم...",
    "🐝 مثل زنبورِ کارگر دارم روش وز‌وز می‌کنم...",
    "🎧 یه آهنگ بذار تا من مغزمو داغ کنم...",
    "🧊 مخم یخ زده بود، دارم گرمش می‌کنم دوباره 😅",
    "🏃‍♂️ دارم می‌دوئم سمت جواب، نفس‌نفس می‌زنم ولی می‌رسم...",
    "🧵 دارم سرنخ سوالتو دنبال می‌کنم...",
    "🛎 زنگ فکر کردن به صدا در اومد، یه لحظه...",
    "🎨 دارم جوابتو رنگ‌آمیزی می‌کنم، قشنگ میشه...",
    "🍜 عینِ رشته‌ی آش دارم افکارمو جمع می‌کنم...",
    "🧨 ترقه‌ی فکر منفجر شد، الان می‌گم چی شد 😂",
    "🚴‍♂️ دارم رکاب می‌زنم سمت جواب، نزدیکم...",
    "🧃 یه‌کم آبمیوه بخور، من دارم فکر می‌کنم...",
    "🏗 دارم جوابتو از پایه می‌سازم، محکم باشه بهتره...",
    "🎬 صحنه‌ی «هوشیار داره فکر می‌کنه» رو تصور کن، الان تمومه...",
    "🐇 خرگوش فکرم داره می‌دوئه، تقریباً رسیدیم...",
]


def _pick_unused(pool: list, used: set) -> str:
    choices = [p for p in pool if p not in used] or pool
    choice = random.choice(choices)
    used.add(choice)
    return choice


async def _animate_while_waiting(thinking_msg, context: ContextTypes.DEFAULT_TYPE,
                                  chat_id: int, coro):
    """
    تا وقتی جواب واقعی آماده بشه، پیامِ «در حال فکر کردن» رو هر چند ثانیه با
    یه عبارت بامزه‌ی جدید عوض می‌کنه (اگه طول بکشه) — به‌جای یک پیام ثابت.
    """
    task   = asyncio.ensure_future(coro)
    delays = [3.0, 4.0, 4.0, 4.0, 4.0]   # فاصله‌ی هر تغییرِ پیام (ثانیه)
    used   = set()

    for delay in delays:
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=delay)
        except asyncio.TimeoutError:
            pass
        if task.done():
            break
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action='typing')
        except Exception:
            pass
        try:
            await thinking_msg.edit_text(_pick_unused(STALL_PHRASES, used))
        except Exception:
            pass

    return await task  # اگه فاز شوخی هم تموم شد، فقط منتظرِ نتیجه‌ی واقعی بمون


async def _answer_with_live_edit(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  get_answer_coro, footer_suffix: str = "") -> None:
    """
    یه پیامِ بامزه‌ی «در حال فکر کردن» می‌فرسته و وقتی جواب آماده شد، همون
    پیام رو ادیت می‌کنه — حس تعاملیِ زنده‌تری به گفتگو می‌ده. اگه جواب دیر
    برسه، پیام رو با عبارت‌های بامزه‌تر یکی‌یکی عوض می‌کنه.
    """
    thinking_msg = await update.message.reply_text(random.choice(THINKING_PHRASES))
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    try:
        answer = await _animate_while_waiting(thinking_msg, context, chat_id, get_answer_coro)
        final_text = f"🤖 {answer}{footer_suffix}"
    except AIError as e:
        final_text = f"⚠️ {e}"
    except Exception:
        logger.exception("AI error")
        final_text = "⚠️ مشکلی در ارتباط با سرویس هوش مصنوعی پیش اومد، دوباره امتحان کن."

    if len(final_text) > 4000:  # سقف تلگرام برای طول یک پیام
        final_text = final_text[:3990] + "…"

    try:
        await thinking_msg.edit_text(final_text)
    except Exception:
        # اگه ادیت به هر دلیلی شکست خورد (مثلاً پیام حذف شده)، حداقل جواب رو جدا بفرست
        await update.message.reply_text(final_text)


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
            f"⛔️ سقف روزانه‌ی سوال از هوشیار تموم شده ({used}/{limit}).\n"
            "فردا دوباره امتحان کن."
        )
        return

    await _answer_with_live_edit(update, context, ask_ai(text=text), _footer(limit, used))


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
            f"⛔️ سقف روزانه‌ی سوال از هوشیار تموم شده ({used}/{limit}).\n"
            "فردا دوباره امتحان کن."
        )
        return

    image_bytes = bytes(await tg_file.download_as_bytearray())
    caption     = (update.message.caption or '').strip() or None

    await _answer_with_live_edit(
        update, context,
        ask_ai(text=caption, image_bytes=image_bytes, image_mime=mime),
        _footer(limit, used),
    )

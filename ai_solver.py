"""
🤖 هوشیار — موتور هوش مصنوعی حل سوالات درسی (متن/عکس)
  ✅ هیچ‌چیز هاردکد نیست: کلید API، ارائه‌دهنده، مدل، محدودیت روزانه و
     دستور سیستمی همگی از bot_settings (پنل ادمین → ai_admin.py) خوانده
     می‌شوند.
  ✅ معماری چندارائه‌دهنده: برای اضافه‌کردن یک AI دیگر (مثلاً OpenRouter/
     OpenAI) فقط یک تابع جدید به STREAM_PROVIDERS اضافه می‌شود — بقیه‌ی کد و
     پنل ادمین دست‌نخورده باقی می‌ماند.
  ✅ محدودیت روزانه‌ی سوال، به‌ازای هر کاربر (روی خودِ سند کاربر در
     دیتابیس ذخیره می‌شود؛ نیازی به کالکشن جدید نیست).
"""
import os
import re
import json
import time
import shutil
import base64
import random
import asyncio
import logging
from html import escape as _esc
from collections import deque, OrderedDict
from datetime import datetime

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
MAX_INPUT_CHARS = 2000  # سقف طول متن ورودی کاربر (جلوگیری از هدررفت توکن/هزینه)

# ══════════════════════════════════════════════════
#  حافظه‌ی مکالمه — ⚠️ فیکس: قبلاً فقط توی RAM بود و با هر ری‌استارتِ
#  سرور (که این چند روز به‌خاطرِ آپدیت‌های پیاپی زیاد اتفاق افتاد)
#  کاملاً پاک می‌شد — انگار هوشیار «حافظه‌ی ماهی» داشت. حالا روی سندِ
#  خودِ کاربر توی دیتابیس ذخیره می‌شه: پایدار در برابرِ ری‌استارت، ولی
#  فشرده — با $slice همیشه فقط چند آیتمِ آخر نگه داشته می‌شه، نه یه
#  آرشیوِ بی‌نهایت‌رشد.
# ══════════════════════════════════════════════════
MEMORY_TTL_SECONDS   = 6 * 60 * 60   # ۶ ساعت بی‌فعالیتی → شروعِ تازه (نه فراموشیِ زودهنگام)
MAX_HISTORY_ITEMS    = 8             # ۸ آیتم = ۴ سوال + ۴ جواب اخیر
REPORT_CACHE_MAX     = 2000      # سقفِ حافظه‌ی کش «گزارش پاسخ» (هرس LRU)
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
#  حافظه‌ی مکالمه (پایدار، روی دیتابیس — نه RAM؛ توضیح در بالا)
# ══════════════════════════════════════════════════

async def _get_history(uid: int) -> list:
    items, updated_at = await db.ai_get_memory(uid)
    if not items:
        return []
    if updated_at and (datetime.now() - updated_at).total_seconds() > MEMORY_TTL_SECONDS:
        return []   # قدیمیه؛ نادیده‌اش می‌گیریم (خودش با remember بعدی جایگزین می‌شه)
    return [{'role': it.get('r'), 'text': it.get('t', '')} for it in items]


async def _remember(uid: int, role: str, text: str) -> None:
    if not text:
        return
    try:
        await db.ai_remember(uid, role, text, MAX_HISTORY_ITEMS)
    except Exception:
        logger.exception("ذخیره‌ی حافظه‌ی مکالمه‌ی هوشیار ناموفق بود")


async def _clear_memory(uid: int) -> None:
    try:
        await db.ai_clear_memory(uid)
    except Exception:
        logger.exception("پاک‌کردنِ حافظه‌ی مکالمه‌ی هوشیار ناموفق بود")


# ══════════════════════════════════════════════════
#  کشِ «گزارش پاسخ نامناسب» — نگاشتِ (chat_id, message_id) به
#  متن سوال/جواب، فقط برای چند دقیقه‌ای که دکمه‌ی 🚩 زیر پیام فعاله.
#  این هم فقط RAM هست، با سقف LRU که رشدش رو محدود می‌کنه.
# ══════════════════════════════════════════════════
_report_cache: "OrderedDict[str, dict]" = OrderedDict()


def _cache_for_report(chat_id: int, message_id: int, uid: int, name: str,
                       question: str, answer: str) -> None:
    key = f"{chat_id}:{message_id}"
    _report_cache[key] = {
        'uid': uid, 'name': name or '—',
        'question': question or '—', 'answer': answer or '—',
    }
    _report_cache.move_to_end(key)
    while len(_report_cache) > REPORT_CACHE_MAX:
        _report_cache.popitem(last=False)


# ══════════════════════════════════════════════════
#  تنظیمات — همه از bot_settings (کلید-مقدار عمومی دیتابیس)
# ══════════════════════════════════════════════════

DEFAULT_DISABLED_MSG = "🤖 بخش هوش مصنوعی توسط مدیریت غیرفعال شد."


async def get_ai_config() -> dict:
    raw = await db.get_settings_by_prefix('ai_')
    provider = raw.get('ai_provider', 'gemini')
    personas_raw = raw.get('ai_personas', '{}')
    try:
        personas = json.loads(personas_raw) if isinstance(personas_raw, str) else (personas_raw or {})
    except (ValueError, TypeError):
        personas = {}
    return {
        'enabled':          bool(raw.get('ai_enabled', False)),
        'provider':         provider,
        'api_key':          raw.get('ai_api_key', ''),
        'model':            raw.get('ai_model') or DEFAULT_MODELS.get(provider, DEFAULT_MODEL),
        'daily_limit':      int(raw.get('ai_daily_limit', DEFAULT_LIMIT) or 0),
        'system_prompt':    raw.get('ai_system_prompt', DEFAULT_PROMPT),
        'disabled_message': raw.get('ai_disabled_message', ''),
        'personas':         personas,   # {نامِ_پرسونا: متنِ_پرامپت}
        # ⚠️ قابلیت جدید: عمقِ استدلال. 'auto' یعنی دست‌نخورده (پیش‌فرضِ
        # خودِ مدل)، 'high' یعنی برای سوالاتِ سخت بیشتر «فکر کنه» قبل از
        # جواب — رایگانه، فقط جزوِ توکنِ خروجی حساب می‌شه.
        'thinking':         raw.get('ai_thinking', 'auto'),
    }


async def set_ai_setting(key: str, value) -> None:
    await db.set_setting(f'ai_{key}', value)


async def save_persona(name: str, prompt: str) -> None:
    """پرسونای فعلی رو با یه اسم ذخیره می‌کنه تا بعداً سریع بشه بهش سوییچ کرد."""
    cfg = await get_ai_config()
    personas = cfg['personas']
    personas[name.strip()[:40]] = prompt
    await set_ai_setting('personas', json.dumps(personas, ensure_ascii=False))


async def delete_persona(name: str) -> None:
    cfg = await get_ai_config()
    personas = cfg['personas']
    personas.pop(name, None)
    await set_ai_setting('personas', json.dumps(personas, ensure_ascii=False))


# ══════════════════════════════════════════════════
#  ارائه‌دهنده‌ها (Providers)
#  برای افزودن یک AI جدید: یک تابع async با همین امضا بنویس و در
#  دیکشنری STREAM_PROVIDERS پایین ثبتش کن. سپس از پنل ادمین می‌شود روی
#  provider جدید سوییچ کرد — بدون تغییر جای دیگری از کد.
# ══════════════════════════════════════════════════

# ══════════════════════════════════════════════════
#  ⚠️ قابلیتِ جدید: Function Calling — هوشیار می‌تونه واقعاً از
#  دیتابیسِ خودِ هامزیار (برنامه/نمراتِ همون دانشجو) بخونه، نه اینکه
#  حدس بزنه. فقط وقتی uid داریم (یعنی یه دانشجوی واقعی داره سوال
#  می‌پرسه، نه تستِ ادمین) فعال می‌شه.
# ══════════════════════════════════════════════════
AI_FUNCTIONS = [
    {
        'name': 'get_my_schedule',
        'description': (
            'برنامه‌ی کلاسی/امتحانیِ آینده‌ی همین دانشجو رو از دیتابیسِ هامزیار می‌خونه. '
            'برای سوالاتی مثل «کی امتحان دارم؟» یا «برنامه‌ی این هفته‌ام چیه؟» استفاده کن.'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'type_filter': {
                    'type': 'string',
                    'description': 'فیلترِ نوع، مثلاً "امتحان" یا "کلاس" — اگه خالی بمونه همه برمی‌گرده.',
                }
            },
        },
    },
    {
        'name': 'get_my_grades',
        'description': (
            'نمراتِ ثبت‌شده‌ی همین دانشجو رو از دیتابیسِ هامزیار می‌خونه. '
            'برای سوالاتی مثل «نمره‌ی آخرین کوییزم چند شد؟» استفاده کن.'
        ),
        'parameters': {'type': 'object', 'properties': {}},
    },
]


async def _execute_ai_function(name: str, args: dict, uid: int) -> str:
    args = args or {}
    try:
        if name == 'get_my_schedule':
            user = await db.get_user(uid) or {}
            rows = await db.get_schedules(group=user.get('group'))
            type_filter = (args.get('type_filter') or '').strip()
            if type_filter:
                rows = [r for r in rows if type_filter in (r.get('type') or '')]
            if not rows:
                return 'هیچ برنامه‌ی آینده‌ای برای این دانشجو ثبت نشده.'
            lines = [
                f"- {r.get('type','')}: {r.get('lesson','')} | استاد: {r.get('teacher','')} | "
                f"{r.get('date','')} ساعت {r.get('time','')}"
                for r in rows[:15]
            ]
            return "\n".join(lines)

        if name == 'get_my_grades':
            rows = await db.grade_list_for_student(uid)
            if not rows:
                return 'هنوز نمره‌ای برای این دانشجو ثبت نشده.'
            lines = [
                f"- {r.get('lesson','')} ({r.get('exam_title','')}): {r.get('score','')} "
                f"| تاریخ: {r.get('exam_date','')}"
                for r in rows[:20]
            ]
            return "\n".join(lines)

        return 'تابعِ ناشناخته.'
    except Exception:
        logger.exception("اجرای تابعِ هوشیار (%s) ناموفق بود", name)
        return 'خطا در خواندنِ اطلاعات از دیتابیس.'


# ══════════════════════════════════════════════════
#  ⚠️ قابلیتِ جدید: آپلودِ فایل به Gemini Files API — برای «سندِ مرجعِ
#  فعال» (RAG سبک). خودِ فایل روی سرورهای گوگل ذخیره می‌شه (رایگان،
#  ۴۸ ساعت)، فقط یه URI کوچیک برمی‌گردونیم که بعداً توی سوالاتِ بعدی
#  ارجاع بدیم — بدون اینکه هر بار کاربر دوباره فایل رو بفرسته.
# ══════════════════════════════════════════════════

async def _gemini_upload_file(api_key: str, file_bytes: bytes, mime_type: str, display_name: str) -> dict:
    base = "https://generativelanguage.googleapis.com/upload/v1beta/files"
    start_headers = {
        'x-goog-api-key':                    api_key,
        'X-Goog-Upload-Protocol':            'resumable',
        'X-Goog-Upload-Command':             'start',
        'X-Goog-Upload-Header-Content-Length': str(len(file_bytes)),
        'X-Goog-Upload-Header-Content-Type': mime_type,
        'Content-Type':                      'application/json',
    }
    async with httpx.AsyncClient(timeout=60) as client:
        start_resp = await client.post(base, headers=start_headers, json={'file': {'display_name': display_name}})
        if start_resp.status_code != 200:
            raise AIError("آپلودِ فایل روی سرویسِ هوش مصنوعی ناموفق بود.")
        upload_url = start_resp.headers.get('x-goog-upload-url')
        if not upload_url:
            raise AIError("آپلودِ فایل ناموفق بود (URL آپلود دریافت نشد).")

        upload_resp = await client.post(
            upload_url,
            headers={
                'Content-Length':          str(len(file_bytes)),
                'X-Goog-Upload-Offset':    '0',
                'X-Goog-Upload-Command':   'upload, finalize',
            },
            content=file_bytes,
        )
        if upload_resp.status_code != 200:
            raise AIError("آپلودِ فایل روی سرویسِ هوش مصنوعی ناموفق بود.")
        file_info = (upload_resp.json() or {}).get('file') or {}
        if not file_info.get('uri'):
            raise AIError("آپلودِ فایل ناموفق بود (URI دریافت نشد).")
        return file_info


def _raise_gemini_status_error(status_code: int) -> None:
    if status_code == 429:
        raise AIQuotaError("سقف رایگان API برای امروز پر شده — کمی بعد دوباره امتحان کن.")
    if status_code == 402:
        raise AIConfigError(
            "خطای ۴۰۲ (نیاز به پرداخت) از گوگل — پروژه‌ی Google Cloud این کلید "
            "نیاز به فعال‌سازی Billing داره یا در منطقه‌ی شما ردهٔ رایگان در "
            "دسترس نیست."
        )
    if status_code in (400, 401, 403, 404):
        raise AIConfigError(
            "کلید API نامعتبره، مدل اشتباهه یا دسترسی لازم رو نداره — ادمین باید از پنل "
            f"هوشیار تنظیماتش رو چک کنه. (کد خطا: {status_code})"
        )
    if status_code >= 500:
        raise AIError("سرویس هوش مصنوعی موقتاً در دسترس نیست — کمی بعد دوباره امتحان کن.")


async def _stream_gemini(api_key: str, model: str, system_prompt: str,
                          text: str = None, image_bytes: bytes = None,
                          image_mime: str = 'image/jpeg', history: list = None,
                          thinking: str = 'auto', uid: int = None, doc: dict = None, **_):
    """
    ⚠️ موتورِ جدید — سه قابلیت رو یکجا پیاده می‌کنه:
      ۱) پاسخِ استریمینگ (کلمه‌به‌کلمه) به‌جای یک‌جا برگشتنِ کل جواب
      ۲) Function Calling (خوندنِ برنامه/نمره از دیتابیسِ خودِ هامزیار)
      ۳) ابزارِ url_context (خوندنِ لینک‌هایی که کاربر می‌فرسته)
    این یک async generator است که رویدادهای {'type': 'delta'/'done'}
    yield می‌کند. حلقه‌ی function-calling کاملاً داخلی و نامرئی برای
    فراخوان است — فقط دلتاهای متنِ جوابِ نهایی به بیرون می‌رسه.
    """
    # FIX: از اواسط ۲۰۲۶ گوگل کلیدهای جدید با پیشوند «AQ.» صادر می‌کند که
    # با روش قدیمیِ فرستادن کلید در URL (?key=...) کار نمی‌کنند و ۴۰۴/۴۰۳
    # برمی‌گردانند. روش رسمی و سازگار با هر دو فرمت فرستادن کلید در هدر
    # x-goog-api-key است.
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
    headers = {'Content-Type': 'application/json', 'x-goog-api-key': api_key}

    contents = []
    for item in (history or []):
        role = 'model' if item.get('role') == 'assistant' else 'user'
        contents.append({'role': role, 'parts': [{'text': item.get('text', '')}]})

    parts = []
    if image_bytes:
        parts.append({'inline_data': {'mime_type': image_mime, 'data': base64.b64encode(image_bytes).decode('utf-8')}})
    if doc and doc.get('uri'):
        # ⚠️ سندِ مرجعِ فعال (RAG سبک) — اگه دانشجو قبلاً یه PDF فرستاده
        # و هنوز منقضی نشده، خودکار به همین سوال هم اضافه می‌شه.
        parts.append({'file_data': {'mime_type': doc.get('mime') or 'application/pdf', 'file_uri': doc['uri']}})
    if text:
        parts.append({'text': text})
    if not parts:
        parts.append({'text': 'کاربر متن یا فایلی ارسال نکرده.'})
    contents.append({'role': 'user', 'parts': parts})

    # ⚠️ طبق مستندات رسمیِ گوگل، برای خانواده‌ی مدل‌های Gemini 3.x توصیه
    # شده temperature از پیش‌فرض تغییر داده نشه.
    generation_config = {'maxOutputTokens': 3072}
    if not model.startswith('gemini-3'):
        generation_config['temperature'] = 0.3
    if thinking == 'high':
        if model.startswith('gemini-3'):
            generation_config['thinkingConfig'] = {'thinkingLevel': 'high'}
        else:
            generation_config['thinkingConfig'] = {'thinkingBudget': -1}

    tools = [{'code_execution': {}}, {'url_context': {}}]
    if uid is not None:
        tools.append({'function_declarations': AI_FUNCTIONS})

    total_tokens = 0
    full_answer_parts = []
    finish_reason = None

    for _round in range(4):   # سقفِ دورهای فراخوانیِ تابع — جلوگیری از حلقه‌ی بی‌نهایت
        payload = {
            'system_instruction': {'parts': [{'text': system_prompt}]},
            'contents': contents,
            'generationConfig': generation_config,
            'tools': tools,
        }

        function_call = None
        round_model_parts = []

        client = httpx.AsyncClient(timeout=90)
        try:
            for attempt in range(2):   # ⚠️ یک بار ری‌ترای خودکار روی خطای موقتِ سرور (۵xx)
                try:
                    async with client.stream('POST', url, headers=headers, json=payload) as resp:
                        if resp.status_code != 200:
                            if resp.status_code >= 500 and attempt == 0:
                                await asyncio.sleep(1.5)
                                continue
                            _raise_gemini_status_error(resp.status_code)
                        async for line in resp.aiter_lines():
                            if not line.startswith('data:'):
                                continue
                            chunk_str = line[5:].strip()
                            if not chunk_str:
                                continue
                            try:
                                chunk = json.loads(chunk_str)
                            except ValueError:
                                continue
                            usage = chunk.get('usageMetadata') or {}
                            if usage.get('totalTokenCount'):
                                total_tokens = int(usage['totalTokenCount'])
                            cands = chunk.get('candidates') or []
                            if not cands:
                                continue
                            cand = cands[0]
                            if cand.get('finishReason'):
                                finish_reason = cand['finishReason']
                            for part in (cand.get('content', {}) or {}).get('parts', []) or []:
                                if part.get('thought'):
                                    continue
                                if 'functionCall' in part:
                                    function_call = part['functionCall']
                                    round_model_parts.append(part)
                                elif part.get('text') and function_call is None:
                                    round_model_parts.append(part)
                                    full_answer_parts.append(part['text'])
                                    yield {'type': 'delta', 'text': part['text']}
                    break   # استریم با موفقیت تموم شد، از حلقه‌ی ری‌ترای خارج شو
                except httpx.TimeoutException:
                    raise AIError("سرویس هوش مصنوعی دیر جواب داد (timeout) — دوباره امتحان کن.")
                except httpx.HTTPError as e:
                    raise AIError(f"خطا در اتصال به سرویس هوش مصنوعی: {e}")
        finally:
            await client.aclose()

        if function_call:
            fn_name = function_call.get('name')
            fn_args = function_call.get('args') or {}
            result_text = await _execute_ai_function(fn_name, fn_args, uid)
            contents.append({'role': 'model', 'parts': round_model_parts})
            contents.append({'role': 'user', 'parts': [{
                'function_response': {'name': fn_name, 'response': {'result': result_text}}
            }]})
            continue   # دورِ بعدی — این‌بار با نتیجه‌ی تابع

        break   # این دور function call نداشت → جوابِ نهایی همینه

    answer = ''.join(full_answer_parts).strip()
    if not answer:
        raise AIConfigError("مدل پاسخی برنگردوند.")
    if finish_reason == 'MAX_TOKENS':
        note = "\n\n⏳ (جواب طولانی بود و همین‌جا قطع شد؛ اگه خواستی بقیه‌ش رو بگم، بنویس «ادامه بده».)"
        answer += note
        yield {'type': 'delta', 'text': note}

    yield {'type': 'done', 'answer': answer, 'tokens': total_tokens}


async def _call_openrouter(api_key: str, model: str, system_prompt: str,
                            text: str = None, image_bytes: bytes = None,
                            image_mime: str = 'image/jpeg', history: list = None,
                            **_) -> tuple:
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

    messages = [{'role': 'system', 'content': system_prompt}]
    for item in (history or []):
        role = 'assistant' if item.get('role') == 'assistant' else 'user'
        messages.append({'role': role, 'content': item.get('text', '')})
    messages.append({'role': 'user', 'content': content})

    payload = {
        'model': model,
        'messages': messages,
        'temperature': 0.3,
        'max_tokens': 3072,   # ⚠️ فیکس باگِ «پیامِ نصفه» — قبلاً 1024 بود
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = None
            for attempt in range(2):   # ⚠️ یک بار ری‌ترای خودکار روی خطای موقتِ سرور (۵xx)
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 500 and attempt == 0:
                    await asyncio.sleep(1.5)
                    continue
                break
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
        raise AIError("سرویس هوش مصنوعی موقتاً در دسترس نیست — یه بار دیگه هم امتحان شد ولی جواب نداد؛ کمی بعد دوباره امتحان کن.")

    try:
        resp.raise_for_status()
        data = resp.json()
        choice = data['choices'][0]
        answer = choice['message']['content'].strip()
        tokens = int((data.get('usage') or {}).get('total_tokens', 0) or 0)
        if choice.get('finish_reason') == 'length':
            answer += "\n\n⏳ (جواب طولانی بود و همین‌جا قطع شد؛ اگه خواستی بقیه‌ش رو بگم، بنویس «ادامه بده».)"
        return answer, tokens
    except (KeyError, IndexError, ValueError):
        raise AIConfigError("مدل پاسخی برنگردوند — احتمالاً مدل انتخاب‌شده الان در دسترس نیست.")


STREAM_PROVIDERS = {
    'gemini': _stream_gemini,
    # نمونه برای بعداً: یک async generator با همین قرارداد رویداد بنویس
    # ({'type': 'delta', 'text': ...} / {'type': 'done', 'answer':..., 'tokens':...})
}


async def _openrouter_as_stream(**kwargs):
    """
    OpenRouter فعلاً استریمِ واقعی نداره؛ برای اینکه رابطِ یکسانی به
    فراخوان بدیم، کل جواب رو یک‌جا می‌گیریم و به‌عنوان یک delta واحد +
    یک done برمی‌گردونیم — کدِ بالادستی (نمایشِ پیام) فرقی نمی‌کنه.
    """
    answer, tokens = await _call_openrouter(**kwargs)
    yield {'type': 'delta', 'text': answer}
    yield {'type': 'done', 'answer': answer, 'tokens': tokens}


STREAM_PROVIDERS['openrouter'] = _openrouter_as_stream


async def ask_ai_stream(text: str = None, image_bytes: bytes = None,
                         image_mime: str = 'image/jpeg', history: list = None,
                         uid: int = None):
    """
    رابطِ اصلیِ جدید: یک async generator که رویدادهای {'type': 'delta',
    'text': ...} (پاسخِ تدریجی) و در آخر {'type': 'done', 'answer':...,
    'tokens':...} می‌دهد. uid برای Function Calling و سندِ مرجعِ فعال
    (RAG) استفاده می‌شود.
    """
    cfg = await get_ai_config()
    if not cfg['enabled']:
        raise AIConfigError("بخش هوش مصنوعی فعلاً توسط مدیریت غیرفعال است.")
    if not cfg['api_key']:
        raise AIConfigError("هنوز کلید API توسط ادمین تنظیم نشده.")

    fn = STREAM_PROVIDERS.get(cfg['provider'])
    if not fn:
        raise AIConfigError(f"ارائه‌دهنده‌ی «{cfg['provider']}» پشتیبانی نمی‌شود.")

    doc = None
    if cfg['provider'] == 'gemini' and uid is not None:
        try:
            doc = await db.ai_get_doc(uid)
            if doc and doc.get('at') and (datetime.now() - doc['at']).total_seconds() > 48 * 3600:
                doc = None   # فایلِ گوگل بعد از ۴۸ ساعت خودش منقضی می‌شه
        except Exception:
            doc = None

    kwargs = dict(
        api_key=cfg['api_key'], model=cfg['model'], system_prompt=cfg['system_prompt'],
        text=text, image_bytes=image_bytes, image_mime=image_mime,
        history=history or [], thinking=cfg['thinking'],
    )
    if cfg['provider'] == 'gemini':
        kwargs['uid'] = uid
        kwargs['doc'] = doc

    full_answer = None
    async for event in fn(**kwargs):
        if event['type'] == 'done':
            full_answer = event['answer']
        yield event

    if full_answer is not None:
        _guard_against_meta_leak(full_answer, cfg)


async def ask_ai(text: str = None, image_bytes: bytes = None,
                  image_mime: str = 'image/jpeg', history: list = None,
                  uid: int = None) -> tuple:
    """
    نسخه‌ی ساده (غیر-استریم) برای فراخوان‌هایی که فقط جوابِ نهایی رو
    می‌خوان (مثلاً دکمه‌ی «تست اتصال» توی پنل ادمین) — همون
    ask_ai_stream رو زیرِ پوستش صدا می‌زنه و رویدادها رو جمع می‌کنه.
    """
    answer, tokens = '', 0
    async for event in ask_ai_stream(text=text, image_bytes=image_bytes,
                                      image_mime=image_mime, history=history, uid=uid):
        if event['type'] == 'done':
            answer, tokens = event['answer'], event['tokens']
    return answer, tokens


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
    در هر دو حالت، ai_total_usage (مصرف کل، برای آمار پنل ادمین) هم
    یک واحد بالا می‌رود. اگه روز عوض شده باشه، ai_tokens_today هم صفر
    می‌شه (خودِ record_token_usage بعد از جواب گرفتن رویش $inc می‌زند).
    """
    cfg   = await get_ai_config()
    limit = cfg['daily_limit']
    today = datetime.now().strftime('%Y-%m-%d')
    user  = await db.get_user(uid) or {}
    total_before = user.get('ai_total_usage', 0) or 0
    is_new_day   = user.get('ai_usage_date') != today

    if uid == ADMIN_ID or limit <= 0:
        update = {'ai_total_usage': total_before + 1, 'ai_usage_date': today}
        if is_new_day:
            update['ai_tokens_today'] = 0
        await db.update_user(uid, update)
        return True, 0, 0

    used = user.get('ai_usage_count', 0) if not is_new_day else 0

    if used >= limit:
        return False, used, limit

    update = {
        'ai_usage_date':  today,
        'ai_usage_count': used + 1,
        'ai_total_usage': total_before + 1,
    }
    if is_new_day:
        update['ai_tokens_today'] = 0
    await db.update_user(uid, update)
    return True, used + 1, limit


async def record_token_usage(uid: int, tokens: int) -> None:
    """بعد از دریافت جواب صدا زده می‌شه؛ توکن مصرفی رو (امروز + کل) اضافه می‌کنه."""
    if not tokens:
        return
    try:
        await db.ai_inc_tokens(uid, tokens)
    except Exception:
        logger.exception("ثبت توکن مصرفی هوشیار ناموفق بود")


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
        quota_line = "🔓 امروز محدودیتی نداری — هر چقدر دلت خواست بپرس"
    else:
        user  = await db.get_user(uid) or {}
        today = datetime.now().strftime('%Y-%m-%d')
        used  = user.get('ai_usage_count', 0) if user.get('ai_usage_date') == today else 0
        quota_line = f"📊 تا الان {used} از {limit} سوالِ امروزتو استفاده کردی"

    await update.message.reply_text(
        "⚡️ <b>سلام، هوشیارم!</b>\n"
        "همون هم‌کلاسیِ باهوش‌تر که همیشه حاضر به کمکه 😎\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "هر جور راحتی سوالتو بفرست:\n"
        "📝 تایپ کن، ساده و مستقیم\n"
        "📷 عکسِ سوال رو بفرست (می‌تونی زیرش توضیح هم بنویسی)\n"
        "📄 یا جزوه/برگه‌ت رو به‌صورت PDF بفرست\n"
        "🎙️ یا اصلاً برام ویس بفرست و سوالتو بگو، حوصله‌ی تایپ نداری بی‌خیال\n\n"
        f"{quota_line}\n\n"
        "💡 فقط یه نکته: من هوش مصنوعی‌ام، نه پیغمبر! ممکنه یه‌جا اشتباه کنم — "
        "برای چیزای مهم حتماً با منبع درسی یا استاد هم یه چک بزن.\n\n"
        "هر وقت خواستی بری سراغ کارِ دیگه، کافیه یه دکمه‌ی دیگه از منو رو بزنی — "
        "من همیشه همینجام 👋",
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


# ══════════════════════════════════════════════════
#  تبدیل Markdown سبکِ خروجیِ مدل (**bold**, `code`, لیست‌ها، #تیتر) به
#  HTML قابل‌نمایش در تلگرام. ⚠️ فیکس باگ: قبلاً متنِ خامِ AI بدون هیچ
#  parse_mode ای فرستاده می‌شد، برای همین کاراکترهای «**» و امثالش عیناً
#  توی پیامِ کاربر دیده می‌شدن. اول باید کاراکترهای خاصِ HTML (& < >) رو
#  escape کنیم (که خودِ متنِ AI باعث خرابیِ پارسِ HTML نشه)، بعد الگوهای
#  Markdown رو به تگ‌های HTML تبدیل کنیم.
# ══════════════════════════════════════════════════

def _md_to_telegram_html(text: str) -> str:
    if not text:
        return text
    out = _esc(text, quote=False)                                      # 1) امن‌سازی HTML
    out = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', out, flags=re.S)       # 2) **bold**
    out = re.sub(r'(?m)^#{1,6}\s*(.+)$', r'<b>\1</b>', out)             # 3) # تیتر → بولد
    out = re.sub(r'`([^`\n]+?)`', r'<code>\1</code>', out)              # 4) `code`
    out = re.sub(r'(?m)^[*\-]\s+', '• ', out)                          # 5) لیست * یا - → •
    out = re.sub(r'(?<!\w)_(?!_)(.+?)(?<!_)_(?!\w)', r'<i>\1</i>', out)  # 6) _italic_
    return out


EDIT_THROTTLE_SECONDS = 1.3   # حداقل فاصله بین دو ادیتِ پیام حین استریم (جلوگیری از Flood-limit تلگرام)


async def _typing_pinger(context: ContextTypes.DEFAULT_TYPE, chat_id: int, stop_event: asyncio.Event):
    """در پس‌زمینه هر چند ثانیه یک‌بار وضعیتِ «در حال تایپ» رو نگه می‌داره — تا وقتی stop_event ست بشه."""
    while not stop_event.is_set():
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action='typing')
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4)
        except asyncio.TimeoutError:
            pass


async def _answer_with_live_edit(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  stream_gen, footer_suffix: str,
                                  uid: int, question_label: str) -> None:
    """
    ⚠️ قابلیتِ جدید: پاسخِ استریمینگِ واقعی — به‌جای اینکه یک‌جا منتظرِ
    کلِ جواب بمونیم و بعد نشونش بدیم، همون‌طور که متن از Gemini می‌رسه،
    پیام رو تدریجاً (با یه throttle برای رعایتِ محدودیتِ ویرایشِ تلگرام)
    آپدیت می‌کنیم — دقیقاً حسِ «داره جلوی چشمت تایپ می‌کنه» رو می‌ده.
    اگه جواب موفق بود: توی حافظه‌ی مکالمه ثبتش می‌کنه، توکن مصرفی رو به
    دیتابیس اضافه می‌کنه، و زیرِ پیام دکمه‌ها رو می‌ذاره.
    """
    chat_id = update.effective_chat.id
    thinking_msg = await context.bot.send_message(chat_id, random.choice(THINKING_PHRASES))

    stop_event = asyncio.Event()
    pinger = asyncio.ensure_future(_typing_pinger(context, chat_id, stop_event))

    buffer: list = []
    tokens = 0
    answer_text = None
    last_edit_at = 0.0
    final_text = ''

    try:
        async for event in stream_gen:
            if event['type'] == 'delta':
                buffer.append(event['text'])
                now = time.time()
                if now - last_edit_at >= EDIT_THROTTLE_SECONDS:
                    raw_partial = ''.join(buffer)
                    if len(raw_partial) > 3480:
                        raw_partial = raw_partial[:3480] + "…"
                    try:
                        await thinking_msg.edit_text(
                            f"🤖 {_md_to_telegram_html(raw_partial)} ▌", parse_mode='HTML',
                        )
                    except Exception:
                        pass   # مثلاً «message not modified» یا محدودیتِ نرخ — بی‌خیالش شو، دورِ بعد دوباره امتحان می‌شه
                    last_edit_at = now
            elif event['type'] == 'done':
                answer_text = event['answer']
                tokens = event['tokens']

        raw_answer = answer_text or ''
        # ⚠️ برشِ طولِ پیام روی متنِ خام (نه HTML) انجام می‌شه تا هیچ‌وقت
        # وسطِ یه تگ قطع نشه.
        if len(raw_answer) > 3500:
            raw_answer = raw_answer[:3480] + "…"
        final_text = f"🤖 {_md_to_telegram_html(raw_answer)}{_esc(footer_suffix, quote=False)}"

    except AIConfigError as e:
        # ⚠️ این خطا فنیه و فقط برای ادمین معنی داره. دانشجو فقط یه پیامِ
        # ساده می‌بینه، و متنِ فنی مستقیم برای ادمین ارشد فوروارد می‌شه.
        final_text = (
            "⚠️ هوشیار الان یه مشکل فنی داره و نمی‌تونه درست جواب بده.\n"
            "به ادمین اطلاع داده شد؛ لطفاً چند دقیقه‌ی دیگه دوباره امتحان کن 🙏"
        )
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    "🛠 <b>خطای فنیِ هوشیار</b> (فقط برای شما نمایش داده می‌شه؛ کاربر پیامِ ساده دید)\n\n"
                    f"👤 کاربر: {_esc(update.effective_user.full_name or '—')} "
                    f"(<code>{uid}</code>)\n\n"
                    f"❓ سوال:\n{_esc(question_label[:500])}\n\n"
                    f"🧩 جزئیات خطا:\n{_esc(str(e))}",
                    parse_mode='HTML',
                )
            except Exception:
                logger.exception("ارسال هشدار خطای فنیِ هوشیار به ادمین ناموفق بود")
    except AIError as e:
        final_text = f"⚠️ {_esc(str(e), quote=False)}"
    except Exception:
        logger.exception("AI error")
        final_text = "⚠️ مشکلی در ارتباط با سرویس هوش مصنوعی پیش اومد، دوباره امتحان کن."
    finally:
        stop_event.set()
        pinger.cancel()
        try:
            await pinger
        except Exception:
            pass

    if len(final_text) > 4000:  # محافظِ نهایی (به‌ندرت لازم می‌شه)
        final_text = final_text[:3990] + "…"

    reply_markup = None
    if answer_text:
        reply_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔬 مثال بزن", callback_data="aiu:fu:example"),
                InlineKeyboardButton("📝 خلاصه‌ترش کن", callback_data="aiu:fu:summary"),
                InlineKeyboardButton("🎯 سوالِ مشابه", callback_data="aiu:fu:similar"),
            ],
            [
                InlineKeyboardButton("🆕 گفتگوی جدید", callback_data="aiu:newchat"),
                InlineKeyboardButton("🚩 گزارش این جواب", callback_data=f"aiu:report:{chat_id}:{thinking_msg.message_id}"),
            ],
        ])

    try:
        await thinking_msg.edit_text(final_text, reply_markup=reply_markup, parse_mode='HTML')
    except Exception:
        try:
            await thinking_msg.edit_text(final_text, reply_markup=reply_markup)
        except Exception:
            await context.bot.send_message(chat_id, final_text, reply_markup=reply_markup)

    if tokens:
        await record_token_usage(uid, tokens)

    if answer_text:
        await _remember(uid, 'user', question_label)
        await _remember(uid, 'assistant', answer_text)
        _cache_for_report(
            chat_id, thinking_msg.message_id, uid,
            update.effective_user.full_name, question_label, answer_text,
        )


# ══════════════════════════════════════════════════
#  قفل هم‌زمانی — جلوگیری از اینکه یک کاربر قبل از تمام‌شدن جواب سوال
#  قبلی‌اش، سوال دومی بفرسته و دو تا درخواست هم‌زمان برای AI اجرا بشه
#  (هم هزینه‌ی اضافه داره، هم می‌تونه باعث به‌هم‌ریختن پیامِ در حال ادیت
#  بشه چون هر دو تا درخواست دارن روی یک thinking_msg کار می‌کنن).
# ══════════════════════════════════════════════════
_busy_users: set = set()


async def handle_ai_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = (update.message.text or '').strip()
    if not text:
        return

    cfg = await get_ai_config()
    if not cfg['enabled']:
        context.user_data.pop('mode', None)
        await update.message.reply_text(cfg.get('disabled_message') or DEFAULT_DISABLED_MSG)
        return

    if await db.ai_is_banned(uid):
        await update.message.reply_text("⛔️ دسترسیِ شما به هوشیار توسط مدیریت مسدود شده.")
        return

    if len(text) > MAX_INPUT_CHARS:
        await update.message.reply_text(
            f"✍️ سوالت یه‌کم طولانیه (بیشتر از {MAX_INPUT_CHARS} کاراکتر). "
            "لطفاً خلاصه‌ترش کن یا فقط بخش اصلی سوال رو بفرست."
        )
        return

    if uid in _busy_users:
        await update.message.reply_text("⏳ صبر کن جواب سوال قبلی‌ت آماده بشه، بعد این یکی رو بفرست 🙂")
        return

    allowed, used, limit = await check_and_consume_quota(uid)
    if not allowed:
        await update.message.reply_text(
            f"⛔️ سقف روزانه‌ی سوال از هوشیار تموم شده ({used}/{limit}).\n"
            "فردا دوباره امتحان کن."
        )
        return

    _busy_users.add(uid)
    try:
        history = await _get_history(uid)
        await _answer_with_live_edit(
            update, context, ask_ai_stream(text=text, history=history, uid=uid),
            _footer(limit, used), uid, text,
        )
    finally:
        _busy_users.discard(uid)


MAX_MEDIA_BYTES = 15 * 1024 * 1024  # ⚠️ قابلیتِ جدید (PDF/صدا): سقفِ حجمِ فایلِ ورودی

def _find_ffmpeg() -> str | None:
    """
    اول دنبالِ ffmpeg سیستمی می‌گرده (شاید ادمین با apt نصبش کرده باشه).
    اگه پیدا نشد، سراغِ پکیجِ pip به‌اسمِ imageio-ffmpeg می‌ره — این پکیج
    یه نسخه‌ی آماده‌ی ffmpeg رو خودش موقعِ نصب دانلود می‌کنه، پس نیازی
    به sudo/apt روی سرور نیست؛ کافیه توی requirements.txt باشه.
    """
    path = shutil.which('ffmpeg')
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


_FFMPEG_PATH = _find_ffmpeg()  # فقط یک بار موقعِ import چک می‌شه


async def _transcode_ogg_opus_to_wav(ogg_bytes: bytes) -> bytes | None:
    """
    ⚠️ فیکسِ باگِ «ارور ۴۰۰ روی پیامِ صوتی»: پیام‌های صوتیِ تلگرام با
    فرمتِ OGG (کدکِ Opus) ضبط می‌شن، ولی طبقِ مستنداتِ رسمیِ گوگل،
    Gemini از «OGG Vorbis» پشتیبانی می‌کنه، نه Opus — همین ناهماهنگی
    باعثِ ارور ۴۰۰ می‌شد. اینجا با ffmpeg (اگه روی سرور نصب باشه) به
    WAV (که همه‌جا پشتیبانی می‌شه) تبدیلش می‌کنیم. اگه ffmpeg نصب نبود،
    None برمی‌گردونه و فراخوان باید به کاربر پیامِ روشن بده.
    """
    if not _FFMPEG_PATH:
        return None
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            _FFMPEG_PATH, '-y', '-i', 'pipe:0', '-ar', '16000', '-ac', '1', '-f', 'wav', 'pipe:1',
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        wav_bytes, stderr = await asyncio.wait_for(proc.communicate(input=ogg_bytes), timeout=30)
        if proc.returncode != 0 or not wav_bytes:
            logger.warning("ffmpeg transcode شکست خورد: %s", (stderr or b'')[:300])
            return None
        return wav_bytes
    except Exception:
        logger.exception("تبدیلِ صدا با ffmpeg ناموفق بود")
        return None


async def handle_ai_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    ⚠️ قابلیتِ جدید: قبلاً این تابع (به اسمِ handle_ai_photo) فقط عکس
    قبول می‌کرد. الان از همین ساختارِ inline_data که Gemini برای هر نوع
    رسانه‌ای پشتیبانی می‌کنه، برای PDF (جزوه/برگه‌ی اسکن‌شده) و پیامِ
    صوتی/فایلِ صوتی (سوالِ گفتاری) هم استفاده می‌کنیم — بدون تغییری در
    مدلِ هزینه (این‌ها هم جزوِ همون Free Tier هستن).
    """
    uid = update.effective_user.id

    cfg = await get_ai_config()
    if not cfg['enabled']:
        context.user_data.pop('mode', None)
        await update.message.reply_text(cfg.get('disabled_message') or DEFAULT_DISABLED_MSG)
        return

    if await db.ai_is_banned(uid):
        await update.message.reply_text("⛔️ دسترسیِ شما به هوشیار توسط مدیریت مسدود شده.")
        return

    kind = None
    if update.message.photo:
        tg_file = await update.message.photo[-1].get_file()
        mime, kind = 'image/jpeg', 'image'
    elif update.message.voice:
        tg_file = await update.message.voice.get_file()
        mime, kind = (update.message.voice.mime_type or 'audio/ogg'), 'audio'
    elif update.message.audio:
        tg_file = await update.message.audio.get_file()
        mime, kind = (update.message.audio.mime_type or 'audio/mpeg'), 'audio'
    elif update.message.document:
        doc_mime = update.message.document.mime_type or ''
        if doc_mime.startswith('image/'):
            tg_file = await update.message.document.get_file()
            mime, kind = doc_mime, 'image'
        elif doc_mime == 'application/pdf':
            tg_file = await update.message.document.get_file()
            mime, kind = doc_mime, 'pdf'
        else:
            return  # نوع فایل پشتیبانی‌نشده — نادیده گرفته می‌شود
    else:
        return

    # PDF و صدا فقط از طریقِ Gemini کار می‌کنن (OpenRouter برای این
    # نوع‌ها راه‌اندازی نشده)؛ اگه ادمین ارائه‌دهنده رو روی OpenRouter
    # گذاشته، مودبانه بگو فقط عکس/متن پشتیبانی می‌شه.
    if kind != 'image' and cfg['provider'] != 'gemini':
        await update.message.reply_text(
            "⚠️ فعلاً فقط عکس یا متن رو می‌تونم پردازش کنم "
            "(فایلِ PDF/صوتی فقط با ارائه‌دهنده‌ی Gemini کار می‌کنه)."
        )
        return

    if getattr(tg_file, 'file_size', None) and tg_file.file_size > MAX_MEDIA_BYTES:
        await update.message.reply_text(
            f"⚠️ حجمِ فایل بیشتر از {MAX_MEDIA_BYTES // (1024*1024)} مگابایته — "
            "یه نسخه‌ی کوچیک‌تر بفرست."
        )
        return

    caption = (update.message.caption or '').strip() or None
    if caption and len(caption) > MAX_INPUT_CHARS:
        await update.message.reply_text(
            f"✍️ توضیحِ فایل یه‌کم طولانیه (بیشتر از {MAX_INPUT_CHARS} کاراکتر). "
            "لطفاً خلاصه‌ترش کن."
        )
        return

    if uid in _busy_users:
        await update.message.reply_text("⏳ صبر کن جواب سوال قبلی‌ت آماده بشه، بعد این یکی رو بفرست 🙂")
        return

    try:
        media_bytes = bytes(await tg_file.download_as_bytearray())
    except Exception:
        logger.exception("دانلود فایل هوشیار ناموفق بود")
        await update.message.reply_text("⚠️ دانلودِ فایل ناموفق بود — دوباره امتحان کن.")
        return

    # ⚠️ فیکسِ ارورِ ۴۰۰: پیام‌های صوتیِ تلگرام OGG/Opus هستن، ولی Gemini
    # فقط OGG Vorbis رو قبول می‌کنه. قبل از فرستادن (و قبل از مصرفِ
    # سهمیه‌ی روزانه) تبدیلش می‌کنیم — اگه تبدیل شکست بخوره، کاربر
    # سهمیه‌شو الکی از دست نده.
    if kind == 'audio' and 'ogg' in mime.lower():
        wav_bytes = await _transcode_ogg_opus_to_wav(media_bytes)
        if wav_bytes:
            media_bytes, mime = wav_bytes, 'audio/wav'
        else:
            await update.message.reply_text(
                "⚠️ فعلاً امکانِ پردازشِ این پیامِ صوتی نیست (مشکلِ سازگاریِ فرمت). "
                "لطفاً سوالتو تایپ کن یا عکس/PDF بفرست — یا به ادمین اطلاع بده."
            )
            return

    # ⚠️ قابلیتِ جدید: «سندِ مرجعِ فعال» — به‌جای فرستادنِ PDF به‌صورتِ
    # inline (که فقط برای همین یه سوال کار می‌کنه)، آپلودش می‌کنیم روی
    # Gemini Files API (رایگان، ۴۸ ساعت نگه‌داری) و فقط یه اشاره‌گرِ
    # کوچیک ذخیره می‌کنیم. این‌جوری سوالاتِ بعدیِ همین دانشجو هم خودکار
    # به همین سند دسترسی دارن، بدون اینکه دوباره بفرستتش.
    display_name = None
    if update.message.document:
        display_name = update.message.document.file_name
    if kind == 'pdf':
        try:
            file_info = await _gemini_upload_file(cfg['api_key'], media_bytes, mime, display_name or 'جزوه.pdf')
            await db.ai_set_doc(uid, file_info['uri'], file_info.get('mimeType', mime), display_name or 'جزوه')
            media_bytes = None   # دیگه لازم نیست inline بفرستیمش؛ از طریقِ doc reference میره
        except Exception:
            logger.exception("آپلودِ PDF به Gemini Files API ناموفق بود")
            await update.message.reply_text("⚠️ آپلودِ فایل ناموفق بود — دوباره امتحان کن.")
            return

    allowed, used, limit = await check_and_consume_quota(uid)
    if not allowed:
        await update.message.reply_text(
            f"⛔️ سقف روزانه‌ی سوال از هوشیار تموم شده ({used}/{limit}).\n"
            "فردا دوباره امتحان کن."
        )
        return

    labels = {
        'image': "[یک سوال به‌صورت عکس فرستاد]",
        'pdf':   f"[یک فایل PDF فرستاد: {display_name or 'جزوه'} — به‌عنوانِ سندِ مرجع ذخیره شد]",
        'audio': "[یک پیام صوتی فرستاد]",
    }
    question_label = caption or labels.get(kind, "[یک فایل فرستاد]")

    _busy_users.add(uid)
    try:
        history = await _get_history(uid)
        await _answer_with_live_edit(
            update, context,
            ask_ai_stream(text=caption, image_bytes=media_bytes, image_mime=mime, history=history, uid=uid),
            _footer(limit, used), uid, question_label,
        )
    finally:
        _busy_users.discard(uid)


# ══════════════════════════════════════════════════
#  دکمه‌های زیرِ جواب («🆕 گفتگوی جدید» / «🚩 گزارش این جواب») —
#  callback_data با پیشوند aiu: (برای هر کاربری، برخلاف ai: که مخصوص
#  پنل ادمینه).
# ══════════════════════════════════════════════════

async def ai_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    uid    = update.effective_user.id
    parts  = query.data.split(':')
    action = parts[1] if len(parts) > 1 else ''

    if action == 'newchat':
        await _clear_memory(uid)
        await db.ai_clear_doc(uid)
        await query.answer("✅ حافظه‌ی مکالمه (و سندِ مرجعِ فعال، اگه بود) پاک شد؛ از اول شروع کن 🙂", show_alert=True)
        return

    if action == 'fu':
        fu_type = parts[2] if len(parts) > 2 else ''
        prompts = {
            'example': 'یه مثالِ ملموس و کاربردی برای همون چیزی که الان توضیح دادی بزن.',
            'summary': 'همون جوابِ قبلی رو خیلی خلاصه‌تر (در حد ۲ تا ۳ خط) بگو.',
            'similar': 'یه سوالِ چهارگزینه‌ایِ مشابهِ همون موضوع بساز و ازم بپرس.',
        }
        prompt = prompts.get(fu_type)
        if not prompt:
            await query.answer()
            return

        cfg = await get_ai_config()
        if not cfg['enabled']:
            await query.answer(cfg.get('disabled_message') or DEFAULT_DISABLED_MSG, show_alert=True)
            return
        if await db.ai_is_banned(uid):
            await query.answer("⛔️ دسترسیِ شما به هوشیار توسط مدیریت مسدود شده.", show_alert=True)
            return
        if uid in _busy_users:
            await query.answer("⏳ صبر کن جوابِ قبلی آماده بشه.", show_alert=True)
            return
        allowed, used, limit = await check_and_consume_quota(uid)
        if not allowed:
            await query.answer(f"⛔️ سقفِ روزانه تموم شده ({used}/{limit}).", show_alert=True)
            return

        await query.answer()
        _busy_users.add(uid)
        try:
            history = await _get_history(uid)
            await _answer_with_live_edit(
                update, context, ask_ai_stream(text=prompt, history=history, uid=uid),
                _footer(limit, used), uid, prompt,
            )
        finally:
            _busy_users.discard(uid)
        return

    if action == 'report':
        key  = f"{parts[2]}:{parts[3]}" if len(parts) > 3 else ''
        info = _report_cache.get(key)
        if not info:
            await query.answer("⚠️ این پیام قدیمیه و دیگه قابل گزارش نیست.", show_alert=True)
            return
        # ⚠️ فیکس: قبلاً گزارش‌ها فقط توی RAM بودن و با ری‌استارتِ ربات از
        # بین می‌رفتن. حالا در کنار پیامِ فوری به ادمین، توی دیتابیس هم
        # ثبت می‌شه تا از پنل ادمین («📋 گزارش‌های اخیر») همیشه قابل مرور باشه.
        try:
            await db.ai_log_report(info['uid'], info['name'], info['question'], info['answer'])
        except Exception:
            logger.exception("ثبت گزارش هوشیار در دیتابیس ناموفق بود")
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    "🚩 <b>گزارش پاسخ نامناسب هوشیار</b>\n\n"
                    f"👤 کاربر: {_esc(str(info['name']))} (<code>{info['uid']}</code>)\n\n"
                    f"❓ سوال:\n{_esc(info['question'][:800])}\n\n"
                    f"🤖 پاسخ:\n{_esc(info['answer'][:1500])}",
                    parse_mode='HTML',
                )
            except Exception:
                logger.exception("گزارش پاسخ هوشیار به ادمین ارسال نشد")
        await query.answer("✅ گزارش شد، ممنون از دقتت 🙏", show_alert=True)
        return

    await query.answer()

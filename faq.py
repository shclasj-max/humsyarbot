"""
❓ سوالات متداول — با محتوای پیش‌فرض کامل
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes
from database import db

logger = logging.getLogger(__name__)

DEFAULT_FAQS = {
    '🔬 علوم پایه': [
        ('علوم پایه چیه و چطور استفاده کنم؟',
         'بخش علوم پایه شامل محتوای آموزشی دروس ترم ۱ تا ۵ است.\n'
         'مسیر: 📚 منابع ← 🔬 علوم پایه ← ترم ← درس ← جلسه\n'
         'در هر جلسه، محتوا (ویدیو، جزوه، پاورپوینت، ویس استاد و...) قابل دانلود است.\n\n'
         '⚠️ واحدهای هر ترم بر اساس چارت پیشنهادی دانشگاه است.'),
        ('چطور محتوای یک جلسه را پیدا کنم؟',
         'مسیر: منابع ← علوم پایه ← ترم ← نام درس ← شماره جلسه\n'
         'در صفحه جلسه، همه فایل‌ها (ویدیو، پاورپوینت، جزوه PDF، ویس) نمایش داده می‌شود.'),
        ('محتوای جدید کی اضافه میشه؟',
         'ادمین محتوا بعد از هر کلاس آپلود می‌کند.\n'
         'اگر اعلان «منابع جدید» فعال باشد، هنگام آپلود پیام دریافت می‌کنید.\n'
         'تنظیم اعلان: دکمه 🔔 اعلان‌ها'),
        ('تفاوت انواع محتوا چیه؟',
         '🎥 ویدیو کلاس: ضبط ویدیویی کلاس\n'
         '📊 پاورپوینت: اسلایدهای استاد\n'
         '📄 جزوه PDF: جزوه درسی\n'
         '📝 نکات: نکات مهم\n'
         '🧪 تست: سوالات تمرینی\n'
         '🎙 ویس استاد: توضیحات صوتی'),
    ],
    '📚 رفرنس‌ها': [
        ('رفرنس‌ها چی هستن؟',
         'رفرنس‌ها کتاب‌های مرجع درسی به فرمت PDF هستند.\n'
         'برای هر درس، یک یا چند کتاب مرجع فارسی یا لاتین وجود دارد.'),
        ('تفاوت نسخه فارسی و لاتین چیه؟',
         '🌐 نسخه لاتین: کتاب اصلی به انگلیسی\n'
         '🇮🇷 نسخه فارسی: ترجمه فارسی همان کتاب'),
        ('چطور رفرنس مورد نظرم رو پیدا کنم؟',
         'مسیر: 📚 منابع ← 📖 رفرنس‌ها ← نام درس ← نام کتاب ← انتخاب نسخه'),
    ],
    '🧪 بانک سوال': [
        ('بانک سوال چه بخش‌هایی داره؟',
         '📁 بانک فایل: فایل‌های PDF آپلود شده\n'
         '💡 تمرین تستی: سوالات چهارگزینه‌ای تعاملی\n'
         '✏️ طراحی سوال: می‌توانید سوال طراحی کنید\n'
         '🏆 آزمون سفارشی: تعداد و زمان دلخواه'),
        ('چطور سوال طراحی کنم؟',
         'بانک سوال ← ✏️ طراحی سوال\n'
         'درس و مبحث را انتخاب کرده و ۵ مرحله را طی کنید.\n'
         'سوال شما بعد از تأیید ادمین اضافه می‌شود.'),
        ('تمرین تستی چه حالت‌هایی داره؟',
         '• تمرین آزاد: سوال‌های تصادفی\n'
         '• تمرین نقاط ضعف: سوال‌هایی که اشتباه زده‌اید\n'
         '• آزمون سفارشی: تعداد و زمان دلخواه'),
    ],
    '💳 خرید اشتراک': [
        ('چطور اشتراک بخرم؟',
         '۱️⃣ وارد «📚 منابع» یا «🧪 بانک سوال» شوید\n'
         '۲️⃣ یکی از پلن‌ها را انتخاب کنید\n'
         '۳️⃣ مبلغ را به شماره کارت نمایش داده‌شده واریز کنید\n'
         '۴️⃣ فقط عکس رسید/اسکرین‌شات را همان‌جا بفرستید\n'
         '۵️⃣ بعد از تأیید ادمین، اشتراک فوراً فعال می‌شود ✅'),
        ('بعد از ارسال رسید چقدر طول می‌کشه فعال بشه؟',
         'رسید شما توسط ادمین بررسی می‌شود؛ معمولاً همان روز.\n'
         'به‌محض تأیید، یک پیام «اشتراکت فعال شد» با تعداد روز اعتبار دریافت می‌کنید.'),
        ('کد تخفیف دارم، کجا وارد کنم؟',
         'در صفحه‌ی انتخاب پلن، دکمه‌ی «🎟 کد تخفیف دارم» را بزنید و کد را تایپ کنید.\n'
         'قیمت نهایی بعد از اعمال تخفیف نمایش داده می‌شود.'),
        ('چطور بفهمم چند روز از اشتراکم مونده؟',
         'از بخش «👤 پروفایل» خط «💳 اشتراک» تعداد روز باقی‌مانده را نشان می‌دهد.'),
        ('رسیدم رد شد، چیکار کنم؟',
         'دلیل رد برای شما ارسال می‌شود (مثلاً عکس نامشخص بوده).\n'
         'دوباره از «📚 منابع» یا «🧪 بانک سوال» اقدام کرده و رسید جدید بفرستید.'),
    ],
    '⚖️ قوانین و کپی‌رایت': [
        ('آیا می‌تونم فایل‌های ربات رو برای بقیه فوروارد کنم؟',
         '❌ خیر، به‌هیچ‌وجه. تمام محتوای منابع، رفرنس‌ها و بانک سوال فقط برای '
         'استفاده‌ی شخصی شماست. فوروارد کردن، اشتراک‌گذاری یا ارسال آن به هر '
         'شخص دیگه (حتی همکلاسی) به هر شکلی — تلگرام، گروه، فضای مجازی — '
         'ممنوع است.'),
        ('اگه بخوام بخشی از محتوا رو جای دیگه استفاده کنم چی؟',
         'اگه به هر دلیلی بخشی از محتوا رو جای دیگه استفاده کردی، ذکر منبع '
         '(هامزیار) الزامی است.'),
        ('چرا نمی‌تونم بعضی فایل‌ها رو فوروارد یا ذخیره کنم؟',
         'فایل‌ها با قابلیت محافظت تلگرام ارسال می‌شوند و دکمه‌ی فوروارد/ذخیره '
         'در اپ رسمی غیرفعال است. این یک اقدام فنی برای رعایت قانون بالاست، '
         'نه یک باگ.'),
        ('اگه فایلی رو به‌جای دیگه بفرستم چی میشه؟',
         '🚫 هرگونه نقض این قوانین (فوروارد/کپی/انتشار بدون ذکر منبع) = '
         'بن دائم و خودکار از ربات + لغو فوری اشتراک، بدون بازگشت وجه.\n\n'
         'هیچ عذر یا استثنایی («فقط برای یه نفر فرستادم»، «نمی‌دونستم» و '
         'امثالش) پذیرفته نیست و این تصمیم غیرقابل اعتراض است.'),
    ],
    '📅 برنامه و امتحانات': [
        ('برنامه کلاس‌ها چطور نمایش داده میشه؟',
         'در بخش 📅 برنامه می‌توانید ببینید:\n'
         '📖 کلاس‌ها — 📝 امتحانات — 🔄 جبرانی — ⏳ امتحانات نزدیک'),
        ('یادآوری امتحان چطور کار میکنه؟',
         'ربات ۷، ۳ و ۱ روز قبل از هر امتحان پیام یادآوری ارسال می‌کند.\n'
         'برای فعال بودن، اعلان «یادآوری امتحان» باید روشن باشد.\n'
         'تنظیم: 🔔 اعلان‌ها'),
        ('تفاوت گروه ۱ و گروه ۲ در برنامه؟',
         'برنامه کلاس‌ها برای دو گروه متفاوت است.\n'
         'ربات بر اساس گروه ثبت‌نام شما نمایش می‌دهد.\n'
         'تغییر گروه: 👤 پروفایل ← تغییر گروه'),
    ],
    '👤 پروفایل و حساب': [
        ('پروفایل خودم رو کجا ببینم؟',
         'دکمه 👤 پروفایل در کیبورد اصلی.\n'
         'آمار تحصیلی، درصد موفقیت، رتبه و ویرایش اطلاعات.'),
        ('چطور نامم یا گروهم رو تغییر بدم؟',
         '👤 پروفایل ← ✏️ ویرایش نام  یا  👥 تغییر گروه'),
        ('چرا دسترسی ندارم؟',
         'بعد از ثبت‌نام، ادمین باید حساب شما را تأیید کند.\n'
         'معمولاً کمتر از ۲۴ ساعت. اگر بیشتر گذشت تیکت بزنید.'),
    ],
    '🎫 تیکت پشتیبانی': [
        ('چطور تیکت بزنم؟',
         '🎫 پشتیبانی ← ارسال تیکت جدید ← موضوع ← توضیح\n'
         'پاسخ در همین ربات ارسال می‌شود.'),
        ('وضعیت تیکتم رو چطور ببینم؟',
         '🎫 پشتیبانی ← تیکت‌های من\n'
         '🟡 باز  |  🟢 بسته شده'),
    ],
    '⚙️ مشکلات فنی': [
        ('ربات جواب نمیده؟',
         '/start بزنید. اگر ادامه داشت، چند دقیقه صبر کنید.\n'
         'در صورت استمرار، از 🎫 پشتیبانی تیکت بزنید.'),
        ('عملیاتی گیر کرده؟',
         '/cancel را بزنید تا عملیات لغو شود.\n'
         'سپس از دکمه‌های کیبورد استفاده کنید.'),
        ('فایل دانلود نمیشه؟',
         'اینترنت خود را بررسی کنید.\n'
         'فایل‌های بزرگ ممکن است چند ثانیه طول بکشند.\n'
         'اگر حل نشد، از 🎫 پشتیبانی تیکت بزنید.'),
    ],
}


async def _get_faq_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """دریافت FAQ از دیتابیس یا پیش‌فرض"""
    db_faqs = await db.faq_get_all()
    if db_faqs:
        cats: dict = {}
        for f in db_faqs:
            cat = f.get('category', 'عمومی')
            cats.setdefault(cat, []).append((f['question'], f['answer']))
        return cats
    return DEFAULT_FAQS


async def faq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    parts  = query.data.split(':')
    action = parts[1] if len(parts) > 1 else 'main'

    if action in ('main', 'back_cats'):
        await _faq_main(query, context)

    elif action == 'cat' and len(parts) > 2:
        await _faq_list(query, context, int(parts[2]))

    elif action == 'item' and len(parts) > 3:
        await _faq_answer(query, context, int(parts[2]), int(parts[3]))


async def _faq_main(query, context: ContextTypes.DEFAULT_TYPE):
    faq_data = await _get_faq_data(context)
    context.user_data['_faq_data'] = faq_data
    cats     = list(faq_data.keys())
    keyboard = [
        [InlineKeyboardButton(f"{cat} ({len(faq_data[cat])})", callback_data=f'faq:cat:{i}')]
        for i, cat in enumerate(cats)
    ]
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='dashboard:refresh')])
    await query.edit_message_text(
        "❓ <b>سوالات متداول</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "در کدام بخش سوال دارید?",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _faq_list(query, context: ContextTypes.DEFAULT_TYPE, cat_idx: int):
    faq_data = context.user_data.get('_faq_data') or await _get_faq_data(context)
    cats     = list(faq_data.keys())
    if cat_idx >= len(cats):
        await query.answer("❌ دسته‌بندی پیدا نشد!", show_alert=True)
        return
    cat      = cats[cat_idx]
    items    = faq_data[cat]
    keyboard = [
        [InlineKeyboardButton(f"❓ {q[:45]}", callback_data=f'faq:item:{cat_idx}:{i}')]
        for i, (q, _) in enumerate(items)
    ]
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data='faq:back_cats')])
    await query.edit_message_text(
        f"{cat}\n\n━━━━━━━━━━━━━━━━\nروی هر سوال کلیک کنید:",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def _faq_answer(query, context: ContextTypes.DEFAULT_TYPE,
                      cat_idx: int, item_idx: int):
    faq_data = context.user_data.get('_faq_data') or await _get_faq_data(context)
    cats     = list(faq_data.keys())
    if cat_idx >= len(cats):
        await query.answer("❌ خطا!", show_alert=True)
        return
    items = faq_data[cats[cat_idx]]
    if item_idx >= len(items):
        await query.answer("❌ سوال پیدا نشد!", show_alert=True)
        return
    question, answer = items[item_idx]
    await query.edit_message_text(
        f"❓ <b>{question}</b>\n\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"💡 {answer}",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت به سوالات", callback_data=f'faq:cat:{cat_idx}')],
            [InlineKeyboardButton("🏠 همه دسته‌بندی‌ها",  callback_data='faq:back_cats')],
        ])
    )


async def show_faq_main(message: Message):
    """فراخوانی از message_router"""
    db_faqs  = await db.faq_get_all()
    faq_data = {}
    if db_faqs:
        for f in db_faqs:
            cat = f.get('category', 'عمومی')
            faq_data.setdefault(cat, []).append((f['question'], f['answer']))
    else:
        faq_data = DEFAULT_FAQS

    cats     = list(faq_data.keys())
    keyboard = [
        [InlineKeyboardButton(f"{cat} ({len(faq_data[cat])})", callback_data=f'faq:cat:{i}')]
        for i, cat in enumerate(cats)
    ]
    await message.reply_text(
        "❓ <b>سوالات متداول</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "در کدام بخش سوال دارید?",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

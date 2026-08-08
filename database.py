"""
🗄️ Database — نسخه نهایی کامل
  ✅ MONGODB_URI اجباری
  ✅ ensure_indexes برای سرعت
  ✅ مدیریت ورودی‌های دانشجویی (intakes) داخل class
  ✅ weekly_activity، get_leaderboard، search_resources
  ✅ فیکس: متدهای intakes داخل class DB
"""
import os
import logging
import asyncio
import difflib
from datetime import datetime, timedelta
from bson import ObjectId
import motor.motor_asyncio

logger = logging.getLogger(__name__)


class DB:
    def __init__(self):
        uri = os.getenv('MONGODB_URI')
        if not uri:
            raise ValueError("❌ MONGODB_URI در متغیرهای محیطی تنظیم نشده است!")

        self.client = motor.motor_asyncio.AsyncIOMotorClient(
            uri,
            serverSelectionTimeoutMS=30000,
            connectTimeoutMS=20000,
            socketTimeoutMS=45000,
            maxPoolSize=10,
            minPoolSize=1,
            retryWrites=True,
            retryReads=True,
            waitQueueTimeoutMS=10000,
        )
        _db = self.client['medicalbot']

        self.users        = _db['users']
        self.questions    = _db['questions']
        self.qbank_files  = _db['qbank_files']
        self.schedules    = _db['schedules']
        self.stats_col    = _db['stats']
        self.answers      = _db['answers']
        self.bs_lessons   = _db['bs_lessons']
        self.bs_sessions  = _db['bs_sessions']
        self.bs_content   = _db['bs_content']
        self.ref_subjects = _db['ref_subjects']
        self.ref_books    = _db['ref_books']
        self.ref_files    = _db['ref_files']
        self.faq          = _db['faq']
        self.tickets      = _db['tickets']
        self.intakes      = _db['intakes']
        self.settings     = _db['bot_settings']     # تنظیمات کلی + گروه‌های لاگ + maintenance
        self.notif_runs   = _db['notif_runs']       # FIX جدید: لاگ وضعیت ارسال نوتیف‌ها
        self.content_reports = _db['content_reports']  # FIX جدید: گزارش سوال/جزوه
        # 🔔 مرکز اعلان مینی‌اپ (موج ۴.۹۰) — هر رویداد مهم کاربری که در
        # ربات پیام می‌شود، اینجا هم با ساختار یکدست (نوع/عنوان/متن/لینک)
        # ثبت می‌شود تا صندوق اعلان مینی‌اپ بازتاب کاملِ ربات باشد.
        self.user_notifs  = _db['user_notifications']
        # 🧠 موج N1 — صف ارسال DM (Source of Truth مصرف‌کننده‌ی «من»
        # نیست؛ فقط کانال خروجی ربات است — source of truth همیشه Inbox)
        self.bot_notifs   = _db['bot_notifications']
        # 👑 موج P0 Prestige — سفر رنک/نشان/فید (Spec §۸.۲)
        self.prestige_history = _db['prestige_history']
        # 👑 موج P2 — واکنش‌های فید (ضدتکرار داخلی؛ خروجی فقط شمارنده)
        self.feed_reactions  = _db['feed_reactions']
        # 👑 موج P1 — جلسات آزمون (چالش ارتقا روی همین زیرساخت، فلگ promotion)
        self.exam_sessions   = _db['exam_sessions']
        # FIX جدید: بلک‌لیست بلاک کامل — بر اساس آیدی عددی تلگرام (ثابت و
        # غیرقابل تغییر)، برخلاف یوزرنیم که کاربر می‌تواند عوضش کند.
        # کاربر بلاک‌شده هم از دیتابیس حذف می‌شود و هم دیگر نمی‌تواند
        # با همان آیدی دوباره ثبت‌نام کند.
        self.blacklist    = _db['blacklist']
        self.admin_roles  = _db['admin_roles']      # FIX جدید: سطوح دسترسی چندگانه ادمین
        # 🛡 موج RBAC-W1 — RBAC دیتابیس‌محور (قرارداد اجرا §۴):
        # تک‌منبع حقیقت نقش/مجوز. admin_roles/users.role به‌عنواین
        # mirror سازگاری زنده می‌مانند (Improve, Never Replace).
        self.roles        = _db['roles']
        self.user_roles   = _db['user_roles']
        self.perm_catalog = _db['perm_catalog']
        self.migrations   = _db['migrations']        # 🌊 C1 — وضعیت مهاجرت‌ها
        self.audit_logs   = _db['audit_logs']       # FIX جدید: لاگ فعالیت‌های حساس
        # FIX جدید: سیستم اشتراک — پلن‌ها، وضعیت هر کاربر، رسیدهای
        # در انتظار بررسی، و کدهای تخفیف
        self.sub_plans     = _db['sub_plans']
        self.subscriptions = _db['subscriptions']
        self.sub_payments  = _db['sub_payments']
        self.discount_codes = _db['discount_codes']
        # 🎟 موج D1 — کمپین انتشار کد تخفیف: کاربرانِ مصرف‌کننده‌ی هر کد
        # (per_user_limit اتمیک) + تاریخچه‌ی broadcast کمپین‌ها
        self.discount_uses     = _db['discount_uses']
        self.discount_bcasts   = _db['discount_broadcasts']
        self.grades         = _db['grades']  # FIX جدید: سیستم نمرات
        self.ai_reports     = _db['ai_reports']  # FIX جدید: گزارش‌های «پاسخ نامناسب» هوشیار (پایدار، نه فقط RAM)
        # FIX جدید (فاز چت مینی‌اپ): گفت‌وگوهای چندگانه‌ی هوشیار — هر سند یک
        # گفت‌وگو با آرایه‌ی items (سقف‌دار)؛ مسیر قدیمی ai_mem (مشترک با
        # ربات) عیناً حفظ می‌شود.
        self.ai_conversations = _db['ai_conversations']

    # ══════════════════════════════════════════════════
    #  ایندکس‌ها
    # ══════════════════════════════════════════════════

    async def ensure_indexes(self):
        try:
            await asyncio.gather(
                self.users.create_index('user_id', unique=True, background=True),
                self.users.create_index('approved', background=True),
                self.users.create_index('role', background=True),
                self.users.create_index('registered_at', background=True),
                self.users.create_index('intake', background=True),
                self.questions.create_index('approved', background=True),
                self.questions.create_index([('lesson', 1), ('topic', 1)], background=True),
                # 🌊 موج C1 — کوئری داغ ورودی‌محور {(intake,term)} و
                # فیلتر مدیریت سوال {(intake,approved)} و دانشجو
                self.questions.create_index([('intake', 1), ('approved', 1)], background=True),
                self.qbank_files.create_index([('intake', 1), ('lesson', 1)], background=True),
                self.bs_lessons.create_index([('intake', 1), ('term', 1), ('order', 1)], background=True),
                self.ref_subjects.create_index([('intake', 1), ('order', 1)], background=True),
                self.bs_lessons.create_index([('term', 1), ('order', 1)], background=True),
                self.bs_sessions.create_index([('lesson_id', 1), ('number', 1)], background=True),
                self.bs_content.create_index([('session_id', 1), ('order', 1)], background=True),
                self.ref_subjects.create_index('order', background=True),
                self.ref_books.create_index([('subject_id', 1), ('order', 1)], background=True),
                self.ref_files.create_index([('book_id', 1), ('lang', 1), ('volume', 1)], background=True),
                self.schedules.create_index([('date', 1), ('type', 1)], background=True),
                self.stats_col.create_index([('user_id', 1), ('timestamp', -1)], background=True),
                self.tickets.create_index('ticket_id', unique=True, background=True),
                self.tickets.create_index([('user_id', 1), ('status', 1)], background=True),
                self.qbank_files.create_index([('lesson', 1), ('topic', 1)], background=True),
                self.intakes.create_index('code', unique=True, background=True),
                # 🏷 Identity v1 — یکتایی لقب case-insensitive:
                # unique + sparse (فقط اسنادی که فیلد دارند/غیرnull)
                self.users.create_index('nickname_normalized', unique=True, sparse=True, background=True),
                # 🚀 موج ۴.۶۰ — پوشش کوئری‌های داغ پنل اشتراک:
                # فیلتر status + مرتب‌سازی submitted_at/end_date و
                # تاریخچه‌ی پرداخت هر کاربر. بدون این‌ها = Full
                # Collection Scan + SORT در حافظه در هر درخواست پنل.
                self.sub_payments.create_index([('status', 1), ('submitted_at', -1)], background=True),
                self.sub_payments.create_index([('user_id', 1), ('submitted_at', -1)], background=True),
                self.subscriptions.create_index([('status', 1), ('end_date', 1)], background=True),
                # 🔔 موج ۴.۹۰ — کوئری داغ صندوق اعلان: فهرست کاربر به
                # ترتیب زمان + شمارش خوانده‌نشده‌ها
                self.user_notifs.create_index([('user_id', 1), ('created_at', -1)], background=True),
                self.user_notifs.create_index([('user_id', 1), ('read', 1)], background=True),
                # 👑 موج P0 Prestige — قانون یک‌بارهرسؤال + بردها/رقیب + سفر/فید
                self.answers.create_index([('user_id', 1), ('question_id', 1)], background=True),
                self.answers.create_index([('user_id', 1), ('answered_at', 1)], background=True),
                self.users.create_index([('approved', 1), ('effective_xp', -1)], background=True),
                self.users.create_index([('approved', 1), ('intake', 1), ('effective_xp', -1)], background=True),
                self.users.create_index([('approved', 1), ('group', 1), ('effective_xp', -1)], background=True),
                self.users.create_index([('approved', 1), ('weekly_xp', -1)], background=True),
                self.prestige_history.create_index([('uid', 1), ('at', -1)], background=True),
                self.prestige_history.create_index([('at', -1)], background=True),
                self.prestige_history.create_index([('type', 1), ('key', 1)], background=True),
                # 👑 موج P2 — ضدتکرار واکنش فید (هر کاربر یک واکنش per رویداد)
                self.feed_reactions.create_index([('event_id', 1), ('uid', 1)], unique=True, background=True),
                self.feed_reactions.create_index([('uid', 1)], background=True),
                # 👑 موج P1 — جست‌وجوی جلسه‌ی چالش فعال کاربر
                self.exam_sessions.create_index([('user_id', 1), ('promotion', 1), ('status', 1)], background=True),
                # 🎟 موج D1 — یک مصرف از هر کد توسط هر کاربر (ضدتکرار اتمیک)
                self.discount_uses.create_index([('code', 1), ('user_id', 1)], unique=True, background=True),
                self.discount_bcasts.create_index([('code', 1), ('created_at', -1)], background=True),
            )
            logger.info("✅ ایندکس‌های MongoDB ایجاد شدند")
            # 🎟 موج D1 — مهاجرت ایدمپوتنت: کدهای قدیمی فیلدهای جدید را
            # ندارند؛ مقدار پیش‌فرض می‌نشانیم تا schema یکدست شود.
            # اجرای مجدد بی‌ضرر است ($exists در هر دو کوئری).
            try:
                await self.discount_codes.update_many(
                    {'target_plan_ids': {'$exists': False}},
                    {'$set': {'target_plan_ids': []}})
                await self.discount_codes.update_many(
                    {'per_user_limit': {'$exists': False}},
                    {'$set': {'per_user_limit': 0}})
            except Exception as _me:
                logger.warning(f"D1 migration warning: {_me}")
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")

    # ══════════════════════════════════════════════════
    #  کاربران
    # ══════════════════════════════════════════════════

    async def get_user(self, uid: int):
        return await self.users.find_one({'user_id': uid})

    async def create_user(self, uid: int, name: str, student_id: str,
                          group: str, username: str = None, intake: str = ''):
        # FIX طبق سند: مقادیر پیش‌فرض اعلان‌ها از تنظیمات پنل ادمین
        # خوانده می‌شود — قبلاً هاردکد بود و فقط ۴ نوع را داشت
        notif_defaults = await self.get_notif_defaults()
        await self.users.insert_one({
            'user_id':    uid,
            'name':       name,
            'student_id': student_id,
            'group':      group,
            'username':   username,
            'intake':     intake or '',
            'registered_at': datetime.now().isoformat(),
            'approved':   False,
            'role':       'student',
            'notification_settings': dict(notif_defaults),
            'total_answers':   0,
            'correct_answers': 0,
            'weak_topics':     [],
            # 👑 Prestige — پیش‌فرض‌های کامل برای کاربران جدید (کهنه‌ها مهاجرت نرم)
            'prestige_xp': 0, 'decay_penalty': 0, 'decay_blocks': 0,
            'rank_floor_xp': 0, 'effective_xp': 0, 'season_xp': 0,
            'season_key': 'S1-1405',
            'weekly_xp': 0, 'weekly_reset': '', 'monthly_xp': 0, 'monthly_reset': '',
            'ai_conv_days': [], 'submissions_approved': 0, 'reports_resolved': 0,
            'challenge': {'target_rank': '', 'cooldown_until': '',
                          'last_fail_at': '', 'apex': False},
            'last_gain_at': '', 'last_active_day': '', 'shield_answers': 0, 'shield_until': '',
            'daily_xp': {'date': '', 'amount': 0, 'correct': 0},
            'streak_current': 0, 'streak_best': 0,
            'exams_completed': 0, 'downloads_count': 0,
            'records': {'best_acc': 0, 'best_exam_pct': 0, 'top_rank_key': 'rookie',
                        'top_rank_at': '', 'top_div': 3,
                        'top1_weeks_current': 0, 'top1_weeks_best': 0},
            'achievements': {}, 'privacy_public': True, 'showcase': [],
            'prestige_migrated': True,   # کاربر تازه نیازی به Backfill ندارد
        })

    async def update_user(self, uid: int, data: dict):
        await self.users.update_one({'user_id': uid}, {'$set': data})

    async def delete_user(self, uid: int):
        await self.users.delete_one({'user_id': uid})

    async def block_user(self, uid: int, reason: str = '', blocked_by: int = None,
                          blocked_by_name: str = '') -> None:
        """
        FIX جدید — بلاک کامل: برخلاف delete_user که فقط رکورد را پاک
        می‌کند و کاربر می‌تواند فردا دوباره با همان آیدی ثبت‌نام کند،
        این متد هم حذف می‌کند و هم آیدی عددی تلگرام (ثابت، برخلاف
        یوزرنیم) را در بلک‌لیست ثبت می‌کند تا ثبت‌نام مجدد مسدود شود.
        """
        await self.users.delete_one({'user_id': uid})
        await self.blacklist.update_one(
            {'_id': uid},
            {'$set': {
                'blocked_at':      datetime.now().isoformat(),
                'blocked_by':      blocked_by,
                'blocked_by_name': blocked_by_name,
                'reason':          reason,
            }},
            upsert=True,
        )

    async def unblock_user(self, uid: int) -> bool:
        r = await self.blacklist.delete_one({'_id': uid})
        return r.deleted_count > 0

    async def is_blacklisted(self, uid: int) -> bool:
        return await self.blacklist.find_one({'_id': uid}) is not None

    async def get_blacklist(self, limit: int = 200) -> list:
        return await self.blacklist.find({}).sort('blocked_at', -1).to_list(limit)

    async def all_users(self, approved_only: bool = True):
        q = {'approved': True} if approved_only else {}
        # 🐛 قبلاً to_list(5000) بود: یعنی از کاربر شماره‌ی ۵۰۰۱ به بعد
        # اصلاً در broadcast/آمار/فیلترها دیده نمی‌شد (نه ارور، نه لاگ —
        # فقط سکوت). با to_list(length=None) درایور Motor همه‌ی نتایج را
        # صرف‌نظر از تعدادشان برمی‌گرداند.
        return await self.users.find(q).sort('registered_at', -1).to_list(length=None)

    async def pending_users(self):
        return await self.users.find({'approved': False}).to_list(100)

    async def notif_users(self, ntype: str, group: str = None):
        """
        🐛 باگ واقعی که اینجا بود: این متد گروه (۱/۲/هر دو) را اصلاً در
        نظر نمی‌گرفت — یعنی وقتی برنامه‌ی یک کلاس فقط برای «گروه ۱»
        بود و ادمین زمانش را تغییر می‌داد، اعلان به «همه‌ی» کاربرانی
        که نوتیف مربوطه را روشن داشتند فرستاده می‌شد؛ گروه ۲ هم پیام
        نامربوط به کلاسشان را دریافت می‌کرد. حالا پارامتر اختیاری
        group اضافه شده: اگر مقداری غیر از None/'' /'هر دو' بدهی، فقط
        همان گروه فیلتر می‌شود؛ در غیر این صورت رفتار قبلی (همه) حفظ
        می‌شود — کاملاً backward-compatible.
        """
        # 🧠 N1.2 — گارد canonical: اگر کاربر کلید جدید یا قدیمی را خاموش
        # کرده باشد خارج می‌شود؛ سندهای کهنه (فقط کلید قدیمی) دقیقاً همان
        # رفتار دیروز را حفظ می‌کنند، کاربر تازه هم که خاموش کند اثر دارد.
        canon = self.PREF_ALIAS.get(ntype, ntype) or ntype
        query = {'approved': True,
                 f'notification_settings.{canon}': {'$ne': False},
                 f'notification_settings.{ntype}': {'$ne': False}}
        if group and str(group).strip() not in ('', 'هر دو', 'هردو', 'all'):
            query['group'] = str(group)
        return await self.users.find(query).to_list(length=None)

    async def get_content_admins(self):
        return await self.users.find(
            {'role': 'content_admin', 'approved': True}
        ).to_list(100)

    async def is_content_admin(self, uid: int) -> bool:
        if uid == int(os.getenv('ADMIN_ID', '0')):
            return True
        u = await self.get_user(uid)
        if u and u.get('role') in ('content_admin', 'admin'):
            return True
        # FIX جدید: نقش content_scoped (مدیر محتوای محدود به یک ورودی)
        # هم باید بتواند وارد پنل محتوا شود — فقط با محدودیت ورودی
        role_doc = await self.get_admin_role(uid)
        if role_doc and role_doc.get('role') == 'content_scoped':
            return True
        # 🛡 RBAC-W1 (افزایشی — مسیرهای بالا دست‌نخورده‌اند): نقش‌های
        # دیتابیس‌محور با مجوز content.* هم پنل محتوا را باز می‌کنند.
        return (
            await self.has_perm(uid, 'content.manage')
            or await self.has_perm(uid, 'content.scoped')
        )

    @staticmethod
    def build_user_search_query(query_text: str) -> dict:
        """
        🔎 قرارداد سراسری جست‌وجوی کاربر — «منبع واحد حقیقت».
        هر سه الگو با هم پشتیبانی می‌شوند:
          ۱) آیدی عددی تلگرام (مثلاً 123456789) — تطبیق دقیق، نه substring
          ۲) یوزرنیم، با یا بدون @ (مثلاً @ali_r یا ali_r)
          ۳) نام ثبت‌شده در ربات + شماره دانشجویی
        ربات (admin/ai_admin/subscription_admin/…)، پنل وب (مدیریت
        کاربران)، و پنل اشتراک (اعطای دستی/مشترکین/رسیدها) همه از
        همین سازنده استفاده می‌کنند تا رفتار جست‌وجو در کل سیستم
        یکپارچه بماند. خروجی خالی یعنی «بدون فیلتر».
        """
        import re
        raw = (query_text or '').strip()
        if not raw:
            return {}

        or_clauses = []

        # ۱) آیدی عددی تلگرام — تطبیق دقیق (نه substring)
        if raw.lstrip('+-').isdigit():
            try:
                or_clauses.append({'user_id': int(raw)})
            except (ValueError, OverflowError):
                pass

        # ۲) یوزرنیم — پشتیبانی از هر دو حالت با/بدون @
        uname = raw.lstrip('@').strip()
        if uname:
            or_clauses.append({'username': {'$regex': re.escape(uname), '$options': 'i'}})

        # ۳) اسم ثبت‌شده در ربات + شماره دانشجویی (مثل قبل)
        regex = {'$regex': re.escape(raw), '$options': 'i'}
        or_clauses.append({'name': regex})
        or_clauses.append({'student_id': regex})

        # ۴) 🏷 Identity v1 — جست‌وجو هم‌زمان روی لقب:
        # هم substring روی خود لقب، هم تطبیق case-insensitive روی
        # نرمال‌شده (برای پیدا‌کردن دقیق یک لقب)
        or_clauses.append({'nickname': regex})
        or_clauses.append({'nickname_normalized': {
            '$regex': re.escape(raw.lower()), '$options': 'i'}})

        return {'$or': or_clauses}

    async def search_users(self, query_text: str, limit: int = 20):
        """جست‌وجوی کاربر روی قرارداد مشترک build_user_search_query —
        FIX مهم تاریخی: قبلاً user_id عددی اصلاً توی کوئری نبود."""
        query = self.build_user_search_query(query_text)
        if not query:
            return []
        return await self.users.find(query).to_list(limit)

    async def get_leaderboard(self, limit: int = 10):
        return await self.users.find(
            {'approved': True, 'total_answers': {'$gt': 0}}
        ).sort('correct_answers', -1).limit(limit).to_list(limit)

    # ══════════════════════════════════════════════════
    #  مدیریت ورودی‌های دانشجویی
    # ══════════════════════════════════════════════════

    async def get_active_intakes(self) -> list:
        return await self.intakes.find(
            {'active': True}
        ).sort('created_at', -1).to_list(50)

    async def get_all_intakes(self) -> list:
        return await self.intakes.find({}).sort('created_at', -1).to_list(100)

    async def add_intake(self, code: str, label: str) -> bool:
        exists = await self.intakes.find_one({'code': code})
        if exists:
            return False
        await self.intakes.insert_one({
            'code':       code,
            'label':      label,
            'active':     True,
            'created_at': datetime.now().isoformat(),
        })
        return True

    async def toggle_intake(self, code: str) -> bool:
        doc = await self.intakes.find_one({'code': code})
        if not doc:
            return False
        new_state = not doc.get('active', True)
        await self.intakes.update_one({'code': code}, {'$set': {'active': new_state}})
        return new_state

    async def delete_intake(self, code: str):
        await self.intakes.delete_one({'code': code})

    async def get_users_by_intake(self, intake_code: str) -> list:
        return await self.users.find(
            {'intake': intake_code, 'approved': True}
        ).to_list(500)

    async def intake_stats(self, intake_code: str) -> dict:
        users  = await self.get_users_by_intake(intake_code)
        total  = len(users)
        groups = {}
        for u in users:
            g = u.get('group', 'نامشخص')
            groups[g] = groups.get(g, 0) + 1
        return {'total': total, 'groups': groups, 'users': users}

    async def notif_users_by_intake(self, intake_code: str, ntype: str) -> list:
        users = await self.get_users_by_intake(intake_code)
        # 🧠 N1.2 — canonical با fallback به مقدار قدیمی ذخیره‌شده
        return [
            u for u in users
            if self.notif_pref_on(u.get('notification_settings', {}), ntype)
        ]

    # ══════════════════════════════════════════════════
    #  علوم پایه — درس‌ها
    # ══════════════════════════════════════════════════

    @staticmethod
    def _intake_q(intake):
        """🌊 C1 — ساخت فیلتر intake: None=بدون فیلتر (رفتار قدیمی)،
        str=دقیقاً همان scope، list=هرکدام (مسیر دانشجو: خودش+سراسری)."""
        if intake is None:
            return {}
        if isinstance(intake, (list, tuple, set)):
            return {'intake': {'$in': list(intake)}}
        return {'intake': intake or ''}

    async def bs_get_lessons(self, term: str, intake=None):
        q = {'term': term}
        q.update(self._intake_q(intake))
        return await self.bs_lessons.find(q).sort('order', 1).to_list(50)

    async def bs_add_lesson(self, term: str, name: str, teacher: str = '',
                            intake: str = ''):
        intake = intake or ''
        if await self.bs_lessons.find_one(
                {'term': term, 'name': name, 'intake': intake}):
            return None
        count = await self.bs_lessons.count_documents(
            {'term': term, 'intake': intake})
        r = await self.bs_lessons.insert_one({
            'term': term, 'name': name, 'teacher': teacher,
            'intake': intake,
            'order': count, 'created_at': datetime.now().isoformat(),
        })
        return r.inserted_id

    async def bs_get_lesson(self, lesson_id: str):
        try:
            return await self.bs_lessons.find_one({'_id': ObjectId(lesson_id)})
        except Exception:
            return None

    async def bs_update_lesson(self, lesson_id: str, data: dict) -> bool:
        try:
            await self.bs_lessons.update_one({'_id': ObjectId(lesson_id)}, {'$set': data})
            return True
        except Exception:
            return False

    async def bs_delete_lesson(self, lesson_id: str):
        try:
            await self.bs_lessons.delete_one({'_id': ObjectId(lesson_id)})
            sessions = await self.bs_sessions.find({'lesson_id': lesson_id}).to_list(200)
            for s in sessions:
                await self.bs_content.delete_many({'session_id': str(s['_id'])})
            await self.bs_sessions.delete_many({'lesson_id': lesson_id})
        except Exception as e:
            logger.warning(f"bs_delete_lesson: {e}")

    # ══════════════════════════════════════════════════
    #  علوم پایه — جلسات
    # ══════════════════════════════════════════════════

    async def bs_get_sessions(self, lesson_id: str):
        return await self.bs_sessions.find({'lesson_id': lesson_id}).sort('number', 1).to_list(200)

    async def bs_add_session(self, lesson_id: str, number: int, topic: str, teacher: str):
        existing = await self.bs_sessions.find_one({'lesson_id': lesson_id, 'number': number})
        if existing:
            await self.bs_sessions.update_one(
                {'_id': existing['_id']},
                {'$set': {'topic': topic, 'teacher': teacher}}
            )
            return str(existing['_id'])
        r = await self.bs_sessions.insert_one({
            'lesson_id': lesson_id, 'number': number, 'topic': topic,
            'teacher': teacher, 'created_at': datetime.now().isoformat(),
        })
        return str(r.inserted_id)

    async def bs_get_session(self, sid: str):
        try:
            return await self.bs_sessions.find_one({'_id': ObjectId(sid)})
        except Exception:
            return None

    async def bs_update_session(self, session_id: str, data: dict) -> bool:
        try:
            await self.bs_sessions.update_one({'_id': ObjectId(session_id)}, {'$set': data})
            return True
        except Exception:
            return False

    async def bs_delete_session(self, sid: str):
        try:
            await self.bs_sessions.delete_one({'_id': ObjectId(sid)})
            await self.bs_content.delete_many({'session_id': sid})
        except Exception as e:
            logger.warning(f"bs_delete_session: {e}")

    # ══════════════════════════════════════════════════
    #  علوم پایه — محتوا
    # ══════════════════════════════════════════════════

    async def bs_get_content(self, session_id: str):
        return await self.bs_content.find({'session_id': session_id}).sort('order', 1).to_list(50)

    async def bs_add_content(self, session_id: str, ctype: str, file_id: str,
                             description: str = '', extra_info: str = ''):
        count = await self.bs_content.count_documents({'session_id': session_id})
        r = await self.bs_content.insert_one({
            'session_id': session_id, 'type': ctype, 'file_id': file_id,
            'description': description, 'extra_info': extra_info,
            'order': count, 'uploaded_at': datetime.now().isoformat(), 'downloads': 0,
            'notif_sent': False,   # FIX جدید: برای batch نوتیف منابع جدید
        })
        return r.inserted_id

    # ══════════════════════════════════════════════════
    #  FIX جدید: نوتیف دسته‌ای منابع جدید (هر N ساعت)
    # ══════════════════════════════════════════════════

    async def get_unnotified_resources(self) -> list:
        """
        محتوای جدیدی که هنوز برای آن نوتیف ارسال نشده.
        FIX جدید: علاوه بر bs_content (منابع علوم‌پایه)، فایل‌های
        رفرنس (ref_files) هم اضافه شدند — طبق تصمیم صریح ادمین.
        بانک سوال (qbank_files) عمداً اضافه نشده و وارد این سیستم
        نمی‌شود. هر آیتم با کلید داخلی '_source' مشخص می‌شود که از
        کدام کالکشن آمده، تا هم متن نوتیف و هم علامت‌گذاری نهایی
        بدانند با کدام کالکشن طرفند.
        """
        bs_items = await self.bs_content.find({'notif_sent': {'$ne': True}}).to_list(200)
        for it in bs_items:
            it['_source'] = 'bs_content'

        ref_items = await self.ref_files.find({'notif_sent': {'$ne': True}}).to_list(200)
        for it in ref_items:
            it['_source'] = 'ref_files'

        return bs_items + ref_items

    async def mark_resources_notified(self, content_ids: list):
        """علامت‌گذاری محتوای علوم‌پایه ارسال‌شده تا دوباره اعلام نشود"""
        if not content_ids:
            return
        await self.bs_content.update_many(
            {'_id': {'$in': [ObjectId(c) if isinstance(c, str) else c for c in content_ids]}},
            {'$set': {'notif_sent': True}}
        )

    async def mark_ref_files_notified(self, file_ids: list):
        """FIX جدید: علامت‌گذاری فایل‌های رفرنس ارسال‌شده — موازی و
        مستقل از mark_resources_notified، تا هیچ تغییری روی منطق
        فعلی bs_content اعمال نشود."""
        if not file_ids:
            return
        await self.ref_files.update_many(
            {'_id': {'$in': [ObjectId(c) if isinstance(c, str) else c for c in file_ids]}},
            {'$set': {'notif_sent': True}}
        )

    async def migrate_mark_existing_ref_files_notified(self):
        """
        FIX جدید (یک‌بار در post_init اجرا می‌شود، idempotent):
        رفرنس‌هایی که از قبل توی دیتابیس بودند و فیلد notif_sent
        ندارند، به‌عنوان «قبلاً دیده‌شده» علامت می‌خورند — تا اولین
        اجرای job بعد از این آپدیت، یک‌جا سیل نوتیف قدیمی نفرستد.
        فقط رفرنس‌هایی که از این به بعد آپلود/جایگزین می‌شوند وارد
        صف نوتیف واقعی می‌شوند.
        """
        already_done = await self.get_setting('ref_notif_migration_done', False)
        if already_done:
            return
        result = await self.ref_files.update_many(
            {'notif_sent': {'$exists': False}},
            {'$set': {'notif_sent': True}}
        )
        await self.set_setting('ref_notif_migration_done', True)
        logger.info(
            f"📖 مهاجرت یک‌باره نوتیف رفرنس‌ها: {result.modified_count} فایل قدیمی "
            f"به‌عنوان قبلاً-دیده‌شده علامت خورد"
        )

    async def bs_get_content_item(self, cid: str):
        try:
            return await self.bs_content.find_one({'_id': ObjectId(cid)})
        except Exception:
            return None

    async def bs_get_content_full_path(self, cid: str) -> dict:
        """
        FIX جدید: زنجیره کامل یک فایل محتوا — درس، ترم، مبحث، استاد.
        برای گزارش ایراد دقیق و نوتیف منابع جدید استفاده می‌شود.
        """
        item = await self.bs_get_content_item(cid)
        if not item:
            return {}
        session = await self.bs_get_session(item.get('session_id', ''))
        lesson  = await self.bs_get_lesson(session.get('lesson_id', '')) if session else None
        return {
            'content':     item,
            'session':     session or {},
            'lesson':      lesson or {},
            'lesson_name': lesson.get('name', '') if lesson else '',
            'term':        lesson.get('term', '') if lesson else '',
            'topic':       session.get('topic', '') if session else '',
            'teacher':     session.get('teacher', '') or (lesson.get('teacher', '') if lesson else ''),
            'content_type': item.get('type', ''),
            'description':  item.get('description', ''),
        }

    async def bs_delete_content(self, cid: str):
        try:
            await self.bs_content.delete_one({'_id': ObjectId(cid)})
        except Exception:
            pass

    async def bs_inc_download(self, cid: str, uid: int):
        try:
            await self.bs_content.update_one({'_id': ObjectId(cid)}, {'$inc': {'downloads': 1}})
        except Exception:
            pass
        # 👑 P1 — رویداد پرستیژ دانلود در تک‌منبع DB (پوشش بات+API):
        # اولین‌بار (pre-check شمارش لاگ) + تکمیل همه‌ی محتوای یک جلسه
        first_time = False
        lesson_done = False
        try:
            first_time = (await self.stats_col.count_documents(
                {'user_id': uid, 'action': 'bs_download',
                 'data.content_id': str(cid)})) == 0
        except Exception:
            pass
        await self.log(uid, 'bs_download', {'content_id': cid})
        try:
            content = await self.bs_content.find_one({'_id': ObjectId(cid)})
            sid = (content or {}).get('session_id')
            if sid:
                sess_docs = await self.bs_content.find({'session_id': sid}).to_list(500)
                sess_ids = {str(d.get('_id')) for d in sess_docs}
                mine = await self.stats_col.find(
                    {'user_id': uid, 'action': 'bs_download'}).to_list(2000)
                got = {str((m.get('data') or {}).get('content_id') or '')
                       for m in mine}
                lesson_done = bool(sess_ids) and sess_ids.issubset(got)
        except Exception:
            pass
        try:
            await self.prestige_event(uid, 'file_download',
                {'first_time': first_time, 'lesson_done': lesson_done})
        except Exception:
            pass

    async def search_resources(self, query_text: str):
        """
        FIX جدید: قبلاً هر آیتم فقط '_session' (شامل topic/teacher) داشت
        ولی اسم درس (lesson name) روی خود session نیست، روی bs_lessons
        است — و search.py با فرض غلط r.get('lesson','') می‌خواند که
        همیشه خالی برمی‌گشت. حالا '_lesson' هم (با کش ساده در همین
        اجرا، چون چند session می‌توانند lesson_id مشترک داشته باشند)
        به هر نتیجه اضافه می‌شود.
        """
        import re
        regex = {'$regex': re.escape(query_text), '$options': 'i'}
        sessions = await self.bs_sessions.find(
            {'$or': [{'topic': regex}, {'teacher': regex}]}
        ).to_list(20)
        result = []
        lesson_cache: dict = {}

        async def _lesson_for(lesson_id: str) -> dict:
            if not lesson_id:
                return {}
            if lesson_id not in lesson_cache:
                lesson_cache[lesson_id] = await self.bs_get_lesson(lesson_id) or {}
            return lesson_cache[lesson_id]

        for s in sessions:
            sid = str(s['_id'])
            contents = await self.bs_content.find({'session_id': sid}).to_list(10)
            for c in contents:
                c['_session'] = s
                c['_lesson']  = await _lesson_for(s.get('lesson_id', ''))
                result.append(c)
        direct = await self.bs_content.find({'description': regex}).to_list(10)
        existing_ids = {str(r['_id']) for r in result}
        for c in direct:
            if str(c['_id']) not in existing_ids:
                try:
                    sess = await self.bs_get_session(c.get('session_id', '')) or {}
                except Exception:
                    sess = {}
                c['_session'] = sess
                c['_lesson']  = await _lesson_for(sess.get('lesson_id', ''))
                result.append(c)
        return result[:15]

    # ══════════════════════════════════════════════════
    #  ترتیب‌بندی
    # ══════════════════════════════════════════════════

    async def _normalize_order(self, col, query_filter: dict):
        items = await col.find(query_filter).to_list(1000)
        items.sort(key=lambda x: (x.get('order', 99999), str(x['_id'])))
        updates = []
        for i, item in enumerate(items):
            if item.get('order') != i:
                updates.append(col.update_one({'_id': item['_id']}, {'$set': {'order': i}}))
                item['order'] = i
        if updates:
            await asyncio.gather(*updates)
        return items

    async def reorder_up(self, collection: str, doc_id: str, query_filter: dict) -> bool:
        try:
            col = getattr(self, collection)
            items = await self._normalize_order(col, query_filter)
            ids = [str(it['_id']) for it in items]
            if doc_id not in ids: return False
            idx = ids.index(doc_id)
            if idx == 0: return False
            await asyncio.gather(
                col.update_one({'_id': items[idx]['_id']},     {'$set': {'order': idx - 1}}),
                col.update_one({'_id': items[idx - 1]['_id']}, {'$set': {'order': idx}}),
            )
            return True
        except Exception as e:
            logger.warning(f"reorder_up: {e}")
            return False

    async def reorder_down(self, collection: str, doc_id: str, query_filter: dict) -> bool:
        try:
            col = getattr(self, collection)
            items = await self._normalize_order(col, query_filter)
            ids = [str(it['_id']) for it in items]
            if doc_id not in ids: return False
            idx = ids.index(doc_id)
            if idx >= len(items) - 1: return False
            await asyncio.gather(
                col.update_one({'_id': items[idx]['_id']},     {'$set': {'order': idx + 1}}),
                col.update_one({'_id': items[idx + 1]['_id']}, {'$set': {'order': idx}}),
            )
            return True
        except Exception as e:
            logger.warning(f"reorder_down: {e}")
            return False

    async def reorder_content_up(self, content_id: str, session_id: str) -> bool:
        try:
            items = await self._normalize_order(self.bs_content, {'session_id': session_id})
            ids = [str(it['_id']) for it in items]
            if content_id not in ids: return False
            idx = ids.index(content_id)
            if idx == 0: return False
            await asyncio.gather(
                self.bs_content.update_one({'_id': items[idx]['_id']},     {'$set': {'order': idx - 1}}),
                self.bs_content.update_one({'_id': items[idx - 1]['_id']}, {'$set': {'order': idx}}),
            )
            return True
        except Exception:
            return False

    async def reorder_content_down(self, content_id: str, session_id: str) -> bool:
        try:
            items = await self._normalize_order(self.bs_content, {'session_id': session_id})
            ids = [str(it['_id']) for it in items]
            if content_id not in ids: return False
            idx = ids.index(content_id)
            if idx >= len(items) - 1: return False
            await asyncio.gather(
                self.bs_content.update_one({'_id': items[idx]['_id']},     {'$set': {'order': idx + 1}}),
                self.bs_content.update_one({'_id': items[idx + 1]['_id']}, {'$set': {'order': idx}}),
            )
            return True
        except Exception:
            return False

    # ══════════════════════════════════════════════════
    #  رفرنس‌ها
    # ══════════════════════════════════════════════════

    async def ref_get_subjects(self, intake=None):
        q = self._intake_q(intake)
        return await self.ref_subjects.find(q).sort('order', 1).to_list(100)

    async def ref_add_subject(self, name: str, intake: str = ''):
        intake = intake or ''
        if await self.ref_subjects.find_one({'name': name, 'intake': intake}):
            return None
        count = await self.ref_subjects.count_documents({'intake': intake})
        r = await self.ref_subjects.insert_one({
            'name': name, 'intake': intake,
            'order': count, 'created_at': datetime.now().isoformat(),
        })
        return r.inserted_id

    async def ref_get_subject(self, sid: str):
        try:
            return await self.ref_subjects.find_one({'_id': ObjectId(sid)})
        except Exception:
            return None

    async def ref_update_subject(self, subject_id: str, data: dict) -> bool:
        try:
            await self.ref_subjects.update_one({'_id': ObjectId(subject_id)}, {'$set': data})
            return True
        except Exception:
            return False

    async def ref_delete_subject(self, sid: str):
        try:
            await self.ref_subjects.delete_one({'_id': ObjectId(sid)})
            books = await self.ref_books.find({'subject_id': sid}).to_list(100)
            for b in books:
                await self.ref_files.delete_many({'book_id': str(b['_id'])})
            await self.ref_books.delete_many({'subject_id': sid})
        except Exception as e:
            logger.warning(f"ref_delete_subject: {e}")

    async def ref_get_books(self, subject_id: str):
        return await self.ref_books.find({'subject_id': subject_id}).sort('order', 1).to_list(50)

    async def ref_add_book(self, subject_id: str, name: str):
        count = await self.ref_books.count_documents({'subject_id': subject_id})
        r = await self.ref_books.insert_one({
            'subject_id': subject_id, 'name': name,
            'order': count, 'created_at': datetime.now().isoformat(),
        })
        return r.inserted_id

    async def ref_get_book(self, bid: str):
        try:
            return await self.ref_books.find_one({'_id': ObjectId(bid)})
        except Exception:
            return None

    async def ref_update_book(self, book_id: str, data: dict) -> bool:
        try:
            await self.ref_books.update_one({'_id': ObjectId(book_id)}, {'$set': data})
            return True
        except Exception:
            return False

    async def ref_delete_book(self, bid: str):
        try:
            await self.ref_books.delete_one({'_id': ObjectId(bid)})
            await self.ref_files.delete_many({'book_id': bid})
        except Exception as e:
            logger.warning(f"ref_delete_book: {e}")

    async def ref_get_files(self, book_id: str):
        return await self.ref_files.find({'book_id': book_id}).sort('order', 1).to_list(20)

    async def ref_add_file(self, book_id: str, lang: str, file_id: str,
                           volume: int = 1, description: str = ''):
        # FIX جدید: notif_sent اضافه شد تا این فایل وارد صف نوتیف
        # «منابع جدید» (همون jobـی که برای bs_content کار می‌کند) بشود.
        # چه فایل کاملاً جدید باشد چه جایگزین‌شدن یک جلد/زبان موجود،
        # از نظر دانشجو محتوای تازه است و باید در صف قرار بگیرد.
        existing = await self.ref_files.find_one({'book_id': book_id, 'lang': lang, 'volume': volume})
        if existing:
            await self.ref_files.update_one({'_id': existing['_id']}, {'$set': {
                'file_id': file_id, 'description': description,
                'uploaded_at': datetime.now().isoformat(),
                'notif_sent': False,
            }})
            return str(existing['_id'])
        count = await self.ref_files.count_documents({'book_id': book_id})
        r = await self.ref_files.insert_one({
            'book_id': book_id, 'lang': lang, 'volume': volume,
            'description': description, 'file_id': file_id,
            'uploaded_at': datetime.now().isoformat(), 'downloads': 0, 'order': count,
            'notif_sent': False,
        })
        return str(r.inserted_id)

    async def ref_get_file_full_path(self, fid: str) -> dict:
        """
        FIX جدید: زنجیره‌ی کامل یک فایل رفرنس — موضوع، کتاب، جلد، زبان.
        دقیقاً هم‌الگو با bs_get_content_full_path؛ برای نوتیف «منابع
        جدید» استفاده می‌شود تا فایل‌های رفرنس هم بتوانند گروه‌بندی و
        نمایش داده شوند.
        """
        item = await self.ref_get_file(fid)
        if not item:
            return {}
        book = await self.ref_get_book(item.get('book_id', ''))
        subject = await self.ref_get_subject(book.get('subject_id', '')) if book else None
        lang_label = '🇮🇷 فارسی' if item.get('lang') == 'fa' else '🌐 لاتین'
        vol = item.get('volume', 1)
        return {
            'content':      item,
            'book':         book or {},
            'subject':      subject or {},
            'lesson_name':  subject.get('name', '') if subject else '',
            'topic':        book.get('name', '') if book else '',
            'content_type': 'ref',
            'description':  item.get('description') or f"{book.get('name','') if book else ''} — جلد {vol} — {lang_label}",
        }

    async def ref_get_file(self, fid: str):
        try:
            return await self.ref_files.find_one({'_id': ObjectId(fid)})
        except Exception:
            return None

    async def ref_inc_download(self, fid: str, uid: int):
        try:
            await self.ref_files.update_one({'_id': ObjectId(fid)}, {'$inc': {'downloads': 1}})
        except Exception:
            pass
        first_time = False
        try:
            first_time = (await self.stats_col.count_documents(
                {'user_id': uid, 'action': 'ref_download',
                 'data.file_id': str(fid)})) == 0
        except Exception:
            pass
        await self.log(uid, 'ref_download', {'file_id': fid})
        try:
            await self.prestige_event(uid, 'file_download',
                                      {'first_time': first_time})
        except Exception:
            pass

    async def ref_delete_file(self, fid: str):
        try:
            await self.ref_files.delete_one({'_id': ObjectId(fid)})
        except Exception:
            pass

    # ══════════════════════════════════════════════════
    #  بانک سوال
    # ══════════════════════════════════════════════════

    async def add_qbank_file(self, lesson: str, topic: str, file_id: str,
                             description: str, file_type: str = 'document',
                             intake: str = ''):
        r = await self.qbank_files.insert_one({
            'lesson': lesson, 'topic': topic, 'file_id': file_id,
            'file_type': file_type, 'description': description,
            'intake': intake or '',
            'upload_date': datetime.now().isoformat(), 'downloads': 0,
        })
        return r.inserted_id

    async def get_qbank_files(self, lesson: str = None, topic: str = None,
                              intake=None):
        q = {}
        if lesson: q['lesson'] = lesson
        if topic:  q['topic']  = topic
        q.update(self._intake_q(intake))
        return await self.qbank_files.find(q).sort('upload_date', -1).to_list(100)

    async def get_qbank_file(self, fid: str):
        try:
            return await self.qbank_files.find_one({'_id': ObjectId(fid)})
        except Exception:
            return None

    async def inc_qbank_download(self, fid: str, uid: int):
        try:
            await self.qbank_files.update_one({'_id': ObjectId(fid)}, {'$inc': {'downloads': 1}})
        except Exception:
            pass
        first_time = False
        try:
            first_time = (await self.stats_col.count_documents(
                {'user_id': uid, 'action': 'qbank_download',
                 'data.file_id': str(fid)})) == 0
        except Exception:
            pass
        await self.log(uid, 'qbank_download', {'file_id': fid})
        try:
            await self.prestige_event(uid, 'file_download',
                                      {'first_time': first_time})
        except Exception:
            pass

    async def delete_qbank_file(self, fid: str):
        try:
            await self.qbank_files.delete_one({'_id': ObjectId(fid)})
        except Exception:
            pass

    # ══════════════════════════════════════════════════
    #  سوالات تستی
    # ══════════════════════════════════════════════════

    async def add_question(self, lesson: str, topic: str, difficulty: str,
                           question: str, options: list, correct: int,
                           explanation: str, creator: int, auto_approve: bool = False,
                           chapter: str = '', tags: list = None,
                           question_image: str = None, answer_image: str = None,
                           intake: str = ''):
        """
        FIX/بهبود (بانک سوالات حرفه‌ای): فیلدهای جدید و اختیاری اضافه شد —
        chapter (فصل)، tags (تگ‌ها)، question_image/answer_image (شناسه
        فایل تصویر در تلگرام). همه‌ی این‌ها اختیاری و ۱۰۰٪ سازگار با
        نسخه‌ی قبلی هستند: هر فراخوانی قدیمی add_question بدون این
        آرگومان‌ها دقیقاً مثل قبل کار می‌کند.
        """
        r = await self.questions.insert_one({
            'lesson': lesson, 'topic': topic, 'difficulty': difficulty,
            'chapter': chapter or '', 'tags': tags or [],
            'question': question, 'options': options, 'correct_answer': correct,
            'explanation': explanation, 'creator_id': creator,
            'question_image': question_image, 'answer_image': answer_image,
            'intake': intake or '',
            'approved': auto_approve, 'created_at': datetime.now().isoformat(),
            'attempt_count': 0, 'correct_count': 0,
        })
        return r.inserted_id

    async def get_questions(self, lesson: str = None, topic: str = None,
                            difficulty: str = None, limit: int = 1,
                            exclude: list = None, intake=None):
        q = {'approved': True}
        if lesson:    q['lesson'] = lesson
        if topic and topic != 'همه': q['topic'] = topic
        if difficulty: q['difficulty'] = difficulty
        q.update(self._intake_q(intake))
        if exclude:
            try: q['_id'] = {'$nin': [ObjectId(i) for i in exclude]}
            except Exception: pass
        return await self.questions.find(q).limit(limit).to_list(limit)

    async def search_questions_text(self, query_text: str, limit: int = 10) -> list:
        """جستجوی آزادِ متنی (نه فیلترِ درس/موضوع) — برای Function Callingِ هوشیار."""
        if not query_text:
            return []
        rx = {'$regex': query_text, '$options': 'i'}
        return await self.questions.find(
            {'approved': True, '$or': [{'question': rx}, {'explanation': rx}]}
        ).limit(limit).to_list(limit)

    # ══════════════════════════════════════════════════
    #  ⚠️ قابلیتِ جدید: تشخیصِ سوالِ تکراری قبل از ثبت. عمداً بدونِ هوش
    #  مصنوعی پیاده شده (فقط شباهتِ متنیِ محلی با difflib) — چون این یه
    #  چکِ کیفیِ مهمه که نباید هیچ‌وقت به دردسترس‌بودنِ AI وابسته باشه؛
    #  حتی اگه سرویسِ AI کاملاً قطع باشه، این قابلیت بدونِ کم‌وکاستی کار
    #  می‌کنه.
    # ══════════════════════════════════════════════════

    async def find_similar_questions(self, lesson: str, topic: str, text: str,
                                      threshold: float = 0.72, limit: int = 3) -> list:
        if not text:
            return []
        candidates = await self.questions.find(
            {'lesson': lesson, 'topic': topic}, {'question': 1, 'options': 1, 'correct_answer': 1}
        ).to_list(500)
        scored = []
        norm = text.strip().lower()
        for c in candidates:
            other = (c.get('question') or '').strip().lower()
            if not other:
                continue
            ratio = difflib.SequenceMatcher(None, norm, other).ratio()
            if ratio >= threshold:
                scored.append((ratio, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{'ratio': r, **c} for r, c in scored[:limit]]

    async def get_weak_questions(self, uid: int, limit: int = 1):
        user = await self.get_user(uid)
        weak = user.get('weak_topics', []) if user else []
        # 🌊 C1 — حتی سوالات ضعف هم در همان scope ورودی دانشجو هستند
        sf = self._intake_q(self.student_intake_filter(
            (user or {}).get('intake', '')))
        if not weak: return await self.get_questions(
            limit=limit, intake=self.student_intake_filter(
                (user or {}).get('intake', '')))
        q = {'approved': True, 'topic': {'$in': weak}}
        q.update(sf)
        return await self.questions.find(q
        ).limit(limit).to_list(limit)

    async def get_question_by_id(self, qid: str):
        try:
            return await self.questions.find_one({'_id': ObjectId(qid)})
        except Exception:
            return None

    async def get_daily_rotation_question(self):
        """
        FIX جدید — باگ قبلی: daily_question_job همیشه یک سوال ثابت
        می‌فرستاد (اولین نتیجه بدون sort). حالا بر اساس قدیمی‌ترین
        last_daily_sent چرخشی انتخاب می‌شود — یعنی واقعاً هر روز سوال
        عوض می‌شود و یک دور کامل بانک سوال طی می‌شود.
        """
        q = await self.questions.find(
            {'approved': True}
        ).sort('last_daily_sent', 1).limit(1).to_list(1)
        if not q:
            return None
        chosen = q[0]
        await self.questions.update_one(
            {'_id': chosen['_id']},
            {'$set': {'last_daily_sent': datetime.now().isoformat()}}
        )
        return chosen

    # ══════════════════════════════════════════════════
    #  بانک سوالات — لایه‌ی Query برای سیستم تولید آزمون PDF
    #  (جدا از منطق تولید PDF؛ فقط دیتابیس را می‌شناسد)
    # ══════════════════════════════════════════════════

    async def get_qbank_lessons(self) -> list:
        """درس‌هایی که واقعاً در بانک سوالِ تأییدشده سوال دارند"""
        return sorted([l for l in await self.questions.distinct('lesson', {'approved': True}) if l])

    async def get_qbank_chapters(self, lesson: str) -> list:
        """
        فصل‌های موجود برای یک درس — فقط فصل‌هایی که واقعاً سوال دارند.
        اگه هیچ سوالی فصل نداشته باشه (چون هنوز این فیلد پر نشده)
        لیست خالی برمی‌گرده و ربات این مرحله رو خودکار رد می‌کنه —
        کاملاً سازگار با سوالات قدیمی که فیلد chapter ندارند.
        """
        chapters = await self.questions.distinct(
            'chapter', {'approved': True, 'lesson': lesson, 'chapter': {'$nin': [None, '']}}
        )
        return sorted([c for c in chapters if c])

    async def get_qbank_topics(self, lesson: str, chapter: str = None) -> list:
        """مباحث موجود برای درس (و در صورت انتخاب، فصل) — فقط مباحث دارای سوال"""
        match = {'approved': True, 'lesson': lesson}
        if chapter:
            match['chapter'] = chapter
        topics = await self.questions.distinct('topic', match)
        return sorted([t for t in topics if t])

    async def get_qbank_difficulties(self, lesson: str, chapter: str = None, topic: str = None) -> list:
        """سطوح سختیِ واقعاً موجود برای این فیلتر (برای مرحله‌ی اختیاری انتخاب سختی)"""
        match = {'approved': True, 'lesson': lesson}
        if chapter: match['chapter'] = chapter
        if topic and topic != 'همه': match['topic'] = topic
        diffs = await self.questions.distinct('difficulty', match)
        return [d for d in diffs if d]

    async def count_qbank_questions(self, lesson: str, chapter: str = None,
                                     topic: str = None, difficulty: str = None,
                                     tags: list = None) -> int:
        """تعداد سوالات موجود برای یک فیلتر — برای نمایش قبل از تولید PDF"""
        match = self._exam_match(lesson, chapter, topic, difficulty, tags)
        return await self.questions.count_documents(match)

    def _exam_match(self, lesson, chapter=None, topic=None, difficulty=None,
                     tags=None, exclude_ids=None) -> dict:
        match = {'approved': True, 'lesson': lesson}
        if chapter: match['chapter'] = chapter
        if topic and topic != 'همه': match['topic'] = topic
        if difficulty: match['difficulty'] = difficulty
        if tags: match['tags'] = {'$in': tags}
        if exclude_ids:
            try:
                match['_id'] = {'$nin': [ObjectId(i) for i in exclude_ids]}
            except Exception:
                pass
        return match

    async def get_exam_questions(self, lesson: str, chapter: str = None, topic: str = None,
                                  difficulty: str = None, tags: list = None, count: int = 20,
                                  randomize: bool = True, exclude_ids: list = None) -> list:
        """
        هسته‌ی «Randomizer + Query» برای تولید آزمون:
        - فیلتر بر اساس درس/فصل/مبحث/سختی/تگ (هر کدام اختیاری)
        - randomize=True → انتخاب تصادفی با $sample (بدون تکرار داخل
          همان خروجی، چون $sample به‌طور طبیعی سندهای یکتا برمی‌گرداند)
        - randomize=False → ترتیب سیستماتیک بر اساس تاریخ ثبت (قدیمی‌ترین اول)
        - exclude_ids: هوک آماده برای قابلیت آینده‌ی «جلوگیری از تکرار
          سوالات بین آزمون‌های مختلف یک دانشجو» — کافیست شناسه‌ی
          سوالاتی که قبلاً دریافت کرده به این پارامتر داده شود.
        """
        match = self._exam_match(lesson, chapter, topic, difficulty, tags, exclude_ids)
        if randomize:
            pipeline = [{'$match': match}, {'$sample': {'size': count}}]
            return await self.questions.aggregate(pipeline).to_list(count)
        return await self.questions.find(match).sort('created_at', 1).to_list(count)

    async def get_users_map(self, uids: list) -> dict:
        """
        نگاشت {user_id: نام} برای نمایش «طراح سوال» در PDF — یک کوئری
        دسته‌ای به‌جای N کوئری جدا برای هر سوال.
        """
        if not uids:
            return {}
        docs = await self.users.find({'user_id': {'$in': list(set(uids))}}).to_list(len(set(uids)))
        return {d['user_id']: d.get('name', '') for d in docs}

    async def pending_questions(self):
        return await self.questions.find({'approved': False}).to_list(50)

    async def approve_question(self, qid: str):
        qdoc = None
        try:
            qdoc = await self.questions.find_one({'_id': ObjectId(qid)})
            was_approved = bool((qdoc or {}).get('approved'))
            await self.questions.update_one({'_id': ObjectId(qid)}, {'$set': {'approved': True}})
        except Exception:
            was_approved = True
        # 👑 P1 — پاداش طراح سؤال (فقط کاربر واقعی و فقط در گذار اول به تأیید)
        # 🧠 N1.2 — سینک‌فیکس: رویداد موجود، اما خبر کاربری نداشت (نه DM
        # نه Inbox). خبر + پاداش از همین تک‌گذار خارج می‌شود (تک‌منبع).
        try:
            creator = (qdoc or {}).get('creator_id')
            ctype = (qdoc or {}).get('creator_type') or ''
            if not was_approved and creator and ctype not in ('bot', 'ai'):
                await self.prestige_event(int(creator), 'question_approved',
                                          {'qid': str(qid)})
        except Exception:
            pass
        # 🧠 N1.2 — خبر در try جدا: شکست XP نباید اعلان را ببلعد
        try:
            creator = (qdoc or {}).get('creator_id')
            ctype = (qdoc or {}).get('creator_type') or ''
            if not was_approved and creator and ctype not in ('bot', 'ai'):
                qlink = f'/learn/my-questions?hl={qid}'
                await self.notify_user(int(creator), 'question_approved',
                    title='✍️ سؤالت تأیید شد!',
                    body='سؤال پیشنهادیت به بانک سؤال اضافه شد '
                         '— از مشارکتت ممنونیم 💚',
                    link=qlink,
                    dm=('✍️ <b>سؤالت تأیید شد!</b>\n\n'
                        'سؤال پیشنهادیت به بانک سؤال اضافه شد '
                        '— از مشارکتت ممنونیم 💚'))
        except Exception:
            pass

    async def delete_question(self, qid: str):
        try:
            await self.questions.delete_one({'_id': ObjectId(qid)})
        except Exception: pass

    async def save_answer(self, uid: int, qid: str, selected: int, is_correct: bool):
        await self.answers.insert_one({
            'user_id': uid, 'question_id': qid,
            'selected': selected, 'is_correct': is_correct,
            'answered_at': datetime.now().isoformat(),
        })
        inc = {'total_answers': 1}
        if is_correct: inc['correct_answers'] = 1
        await self.users.update_one({'user_id': uid}, {'$inc': inc})
        try:
            await self.questions.update_one(
                {'_id': ObjectId(qid)},
                {'$inc': {'attempt_count': 1, 'correct_count': 1 if is_correct else 0}}
            )
        except Exception: pass
        if not is_correct:
            try:
                q_doc = await self.questions.find_one({'_id': ObjectId(qid)})
                if q_doc:
                    await self.users.update_one(
                        {'user_id': uid}, {'$addToSet': {'weak_topics': q_doc['topic']}}
                    )
            except Exception: pass
        await self.log(uid, 'answer', {'qid': qid, 'correct': is_correct})

    # ══════════════════════════════════════════════════
    #  👑 Prestige Engine — Competitive Identity (v3 LOCKED · موج P0)
    #  تک‌منبعِ XP/رنک/دیویژن/سپر/Decay/State — بات و API فقط caller‌اند.
    #  (قرارداد §د: هیچ منطق موازی در روتر/بات تکرار نمی‌شود)
    # ══════════════════════════════════════════════════

    # ───── ثابت‌ها (Spec §۲/§۳ — قفل‌شده، بدون تغییر مگر با تأیید مالک)
    XP_WRONG_FIRST    = 1     # غلطِ اولین‌بار هر سؤال
    XP_DAILY_STREAK   = 10    # اولین فعالیت معتبر روز (خارج از سقف)
    XP_EXAM_COMPLETE  = 20    # تکمیل آزمون ≥۱۰ سؤالی
    XP_EXAM_ACC_BONUS = 10    # بونوس دقت ≥۸۰٪
    XP_EXAM_PERFECT   = 20    # بونوس ۱۰۰٪ (جایگزین قبلی)
    DAILY_ANSWER_CAP  = 120   # سقف روزانه‌ی XPِ پاسخ‌محور
    DIMINISH_AFTER    = 40    # بعد از این تعداد صحیح در روز: ×۰٫۵
    SHIELD_ANSWERS    = 30    # سپر ارتقا: ۳۰ پاسخ
    SHIELD_DAYS       = 10    # یا ۱۰ روز (هرکدام زودتر)
    DECAY_IDLE_DAYS   = 10    # هر ۱۰ روز رکود = −۱ دیویژن (کفِ رنک)
    ACTIVE_WINDOW_DAYS = 90   # تعریف Active User (§۳.۵)
    PC_CACHE_TTL_SEC  = 600   # کش total_active — ۱۰ دقیقه

    # جدول آستانه‌ها (Spec §۱.۱ — key, title, icon, start_xp, color, gradient)
    PRESTIGE_RANKS = [
        ('rookie',    'تازه‌وارد',      '🌱', 0,     '#94A3B8', 'linear-gradient(135deg,#94A3B8,#CBD5E1)'),
        ('student',   'دانشجوی کوشا',   '📚', 300,   '#34D399', 'linear-gradient(135deg,#34D399,#6EE7B7)'),
        ('scholar',   'پژوهنده',        '🧠', 750,   '#60A5FA', 'linear-gradient(135deg,#60A5FA,#93C5FD)'),
        ('apprentice','کارآموز پزشکی', '⚕️', 1500,  '#38BDF8', 'linear-gradient(135deg,#38BDF8,#67E8F9)'),
        ('resident',  'رزیدنت',         '🏥', 2400,  '#A78BFA', 'linear-gradient(135deg,#A78BFA,#C4B5FD)'),
        ('elite',     'مدیک نخبه',      '⭐', 3900,  '#FBBF24', 'linear-gradient(135deg,#FBBF24,#FDE68A)'),
        ('expert',    'متخصص بالینی',  '💎', 6000,  '#22D3EE', 'linear-gradient(135deg,#22D3EE,#A5F3FC)'),
        ('master',    'استاد پزشکی',   '👑', 8700,  '#F59E0B', 'linear-gradient(135deg,#F59E0B,#FBBF24)'),
        ('grand',     'استاد بزرگ',    '🏆', 12000, '#FB923C', 'linear-gradient(135deg,#FB923C,#FDBA74)'),
        ('legend',    'شفابخش افسانه‌ای','🌌', 16500,'#E879F9', 'linear-gradient(135deg,#E879F9,#C084FC,#818CF8)'),
    ]
    CHALLENGE_FROM_IDX = 4          # ورود به رنک ۵ (resident) به بعد نیازمند چالش است
    ROMAN = {3: 'III', 2: 'II', 1: 'I'}
    DIV_STARS = {3: '⭐', 2: '⭐⭐', 1: '⭐⭐⭐'}

    @staticmethod
    def _diff_key(raw) -> str:
        """نگاشت متن difficulty سؤال به کلید XP (Spec §۳.۱ — الگوی متن)."""
        t = str(raw or '')
        if 'آسان' in t: return 'easy'
        if 'سخت' in t: return 'hard'
        if 'متوسط' in t: return 'medium'
        return 'unknown'

    XP_BY_DIFF = {'easy': 5, 'medium': 10, 'hard': 15, 'unknown': 8}

    # ── منابع XP وسیع‌تر (Spec §۲.۱ — جدول قفل‌شده)
    XP_FILE_DOWNLOAD  = 8     # اولین دانلود هر فایل
    XP_AI_DAILY       = 5     # اولین گفت‌وگوی هوشیار در روز
    XP_Q_APPROVED     = 25    # تأیید سؤال طراحی‌شده
    XP_REPORT_USEFUL  = 15    # گزارش مفید (resolve)
    XP_CHALLENGE_WIN  = 50    # برد چالش ارتقا (رنک ۵..۹)
    XP_APEX_WIN       = 200   # برد چالش Apex (یک‌بار در عمر حساب)
    XP_WEEKLY_CHAMPION = 100  # صدر جدول هفتگی (جاب بستن هفته)

    # ── قوانین چالش ارتقا (Spec §۳.۱ — قفل‌شده)
    CH_COUNT            = 20    # سؤال چالش عادی
    CH_APEX_COUNT       = 30    # سؤال چالش Apex (باس‌فایت)
    CH_PASS_PCT         = 80    # شرط قبولی چالش عادی
    CH_APEX_PASS_PCT    = 90    # شرط قبولی Apex
    CH_TTL_HOURS        = 24    # TTL جلسه — Resume پس از انقضا ممنوع
    CH_COOLDOWN_H       = 12    # کول‌داون شکست عادی
    CH_APEX_COOLDOWN_H  = 48    # کول‌داون شکست Apex
    CH_EXCLUDE_RECENT   = 200   # حذف ۲۰۰ پاسخ اخیر از استخر
    CH_EXCLUDE_FALLBACK = [150, 100, 50]   # پنجره‌های جایگزین به ترتیب
    CH_MIX_MIN_HARDMED  = 0.4   # حداقل ۴۰٪ متوسط+سخت
    CH_APEX_STREAK_REQ  = 45    # پیش‌شرط اجتماعی Apex: بهترین استریک
    CH_APEX_CONTRIB_REQ = 5     # پیش‌شرط اجتماعی Apex: مشارکت تأییدشده

    # ── جدول Rarity نشان‌ها (Spec §۴.۱ — label/color/پاداش پیش‌فرض)
    BADGE_RARITY = {
        'common':    ('معمولی',    '#94A3B8', 15),
        'rare':      ('کمیاب',     '#60A5FA', 30),
        'epic':      ('حماسی',     '#A78BFA', 60),
        'legendary': ('افسانه‌ای', '#F59E0B', 120),
        'mythic':    ('اسطوره‌ای', '#E879F9', 300),
        'ancient':   ('باستانی',   '#D6A35C', 500),
        'founder':   ('بنیان‌گذار', '#FFD700', 0),
    }

    # ── پنج نشان تکاملی (Spec §۴.۱ب — مقادیر قطعی)
    # key: (icon, title, counter, tiers=[(target, rarity, xp), ...])
    BADGES_PROG = {
        'p_qmaster': ('🏹', 'استاد سؤال', 'total_answers',
                      [(10, 'common', 15), (100, 'rare', 30), (500, 'epic', 60),
                       (1000, 'legendary', 120), (2500, 'mythic', 300)]),
        'p_flame': ('🔥', 'شعله‌ی پایدار', 'streak_best',
                    [(3, 'common', 15), (7, 'rare', 30), (30, 'epic', 60),
                     (90, 'legendary', 120), (180, 'mythic', 300)]),
        'p_exam': ('⚔️', 'فرمانده‌ی آزمون', 'exams_completed',
                   [(1, 'common', 15), (10, 'rare', 30), (30, 'epic', 60),
                    (150, 'ancient', 500)]),
        'p_companion': ('🤝', 'هم‌گوی هوشیار', 'ai_conv_days',
                        [(1, 'common', 15), (10, 'rare', 30), (50, 'epic', 60)]),
        'p_librarian': ('📚', 'کتابدار', 'downloads_count',
                        [(1, 'common', 15), (10, 'rare', 30), (50, 'epic', 60)]),
    }

    # ── نشان‌های تک‌نسخه‌ی كاتالوگ (Spec §۴.۱ب/§۴.۳)
    # key: dict(icon,title,desc,rarity,xp,kind,secret?,hint?)
    BADGES_SINGLE = {
        # لحظه‌ای‌های احساسی (کاملاً جدا از پله‌ها)
        'q_first': dict(icon='🌱', title='نخستین پاسخ', desc='اولین پاسخ ثبت‌شده‌ات',
                        rarity='common', xp=15, kind='lifetime'),
        'e_first': dict(icon='📝', title='نخستین آزمون', desc='اولین آزمون تکمیل‌شده',
                        rarity='common', xp=15, kind='lifetime'),
        'ai_first': dict(icon='🤖', title='نخستین گفت‌وگو با هوشیار',
                         desc='اولین روز گفت‌وگو با هوشیار',
                         rarity='common', xp=15, kind='lifetime'),
        'e_pass20': dict(icon='🎖', title='گذرنده‌ی آزمون بزرگ',
                         desc='تکمیل آزمون ≥۲۰ سؤالی با دقت ≥۸۰٪',
                         rarity='rare', xp=30, kind='exam'),
        'exam_perfect': dict(icon='🎯', title='برگ کامل',
                             desc='آزمون ≥۱۰ سؤالی با دقت ۱۰۰٪',
                             rarity='epic', xp=60, kind='exam'),
        'lesson_done': dict(icon='📚', title='یک درس، تمام‌شده',
                            desc='دانلود تمام محتوای یک درس علوم‌پایه',
                            rarity='rare', xp=30, kind='resource'),
        'ai_image': dict(icon='🖼', title='چشم‌عقابی',
                         desc='نخستین حل تصویری با هوشیار',
                         rarity='common', xp=15, kind='ai'),
        'ai_pdf': dict(icon='📄', title='خوانش‌گر',
                       desc='نخستین تحلیل PDF با هوشیار',
                       rarity='common', xp=15, kind='ai'),
        # Accuracy ۳ (حداقل ۱۰۰ پاسخ — هم‌ریشه با تب دقت لیدربرد)
        'acc70': dict(icon='🎯', title='تیرانداز مطمئن', desc='دقت کلی ≥۷۰٪ (با ≥۱۰۰ پاسخ)',
                      rarity='common', xp=15, kind='accuracy'),
        'acc80': dict(icon='🏹', title='نشانه‌رو حرفه‌ای', desc='دقت کلی ≥۸۰٪ (با ≥۱۰۰ پاسخ)',
                      rarity='rare', xp=30, kind='accuracy'),
        'acc90': dict(icon='💎', title='چشم‌عقابیِ دقت', desc='دقت کلی ≥۹۰٪ (با ≥۱۰۰ پاسخ)',
                      rarity='epic', xp=60, kind='accuracy'),
        # Community ۴
        'c_first_design': dict(icon='✍️', title='نخستین طرح تأییدشده',
                               desc='اولین سؤال طراحی‌شده‌ی تأییدشده‌ات',
                               rarity='common', xp=15, kind='community'),
        'c_first10': dict(icon='🏛', title='ستون بانک سؤال',
                          desc='۱۰ سؤال تأییدشده در بانک',
                          rarity='legendary', xp=120, kind='community'),
        'c_first_report': dict(icon='🕵️', title='مراقب کیفیت',
                               desc='اولین گزارش مفید تأییدشده',
                               rarity='common', xp=15, kind='community'),
        'c_reports10': dict(icon='🛡', title='نگهبان کیفیت',
                            desc='۱۰ گزارش مفید تأییدشده',
                            rarity='rare', xp=30, kind='community'),
        # Secret ۵ (نمایش مبهم تا زمان باز شدن)
        'x_owl': dict(icon='🦉', title='جغد شب‌زنده‌دار',
                      desc='فعالیت بین ۰۰ تا ۰۳ بامداد',
                      rarity='rare', xp=30, kind='secret', secret=True,
                      hint='بعضی‌ها وقتی همه خوابند…'),
        'x_lark': dict(icon='🐦', title='مرغ سحرخیز',
                       desc='فعالیت بین ۰۵ تا ۰۷ صبح',
                       rarity='rare', xp=30, kind='secret', secret=True,
                       hint='صبح که طلایه‌دار شد…'),
        'x_30day': dict(icon='🧠', title='روز مغز',
                        desc='۳۰ پاسخ صحیح در یک روز',
                        rarity='rare', xp=30, kind='secret', secret=True,
                        hint='یک روز خیلی جدی'),
        'x_comeback': dict(icon='🫶', title='بازگشت قهرمان',
                           desc='برگشتن بعد از ≥۱۴ روز دوری',
                           rarity='rare', xp=30, kind='secret', secret=True,
                           hint='گاهی باید رفت تا برگشت'),
        'x_week300': dict(icon='⚡', title='هفته‌ی برق‌آسا',
                          desc='۳۰۰+ XP در یک هفته',
                          rarity='rare', xp=30, kind='secret', secret=True,
                          hint='یک هفته‌ی تمام‌نشدنی'),
        # Ancient (فرازمانی — سال‌ها)
        'a_q5000': dict(icon='🏺', title='پانزده‌خزان سؤال',
                        desc='۵٬۰۰۰ پاسخ ثبت‌شده',
                        rarity='ancient', xp=500, kind='ancient'),
        'a_s365': dict(icon='🕯', title='شمع جاودان',
                       desc='استریک ۳۶۵ روزه',
                       rarity='ancient', xp=500, kind='ancient'),
        # Founder / Competition
        'f_founder': dict(icon='🏛', title='بنیان‌گذار هامزیار',
                          desc='از نخستین اعضای پلتفرم — دیگر قابل دریافت نیست',
                          rarity='founder', xp=0, kind='founder'),
        'c_top1_week': dict(icon='👑', title='صدرنشین هفته',
                            desc='قهرمان جدول هفتگی',
                            rarity='legendary', xp=120, kind='competition'),
    }

    SHOWCASE_MAX = 3                   # سقف نشان پین‌شده (Spec §۴.۴)
    AI_DAYS_KEEP = 365                 # سقف نگه‌داری روزهای گفت‌وگوی هوشیار

    def _div_width(self, idx: int) -> int:
        """پهنای هر دیویژن درون رنک (تمام بازه‌ها بر ۳ بخش‌پذیرند — Spec §۱.۱)"""
        if idx >= len(self.PRESTIGE_RANKS) - 1:
            return 0
        return (self.PRESTIGE_RANKS[idx + 1][3] - self.PRESTIGE_RANKS[idx][3]) // 3

    def _rank_for(self, xp: int):
        """رنک خام از روی XP: بازگشت (idx, div) — div: 3=III ... 1=I (Apex همیشه 1)"""
        idx = 0
        for i, r in enumerate(self.PRESTIGE_RANKS):
            if xp >= r[3]:
                idx = i
        if idx >= len(self.PRESTIGE_RANKS) - 1:
            return idx, 1
        start = self.PRESTIGE_RANKS[idx][3]
        w = self._div_width(idx)
        off = xp - start
        if off < w:
            return idx, 3
        if off < 2 * w:
            return idx, 2
        return idx, 1

    @staticmethod
    def _puser(u: dict) -> dict:
        """مهاجرت نرم: فیلدهای Prestige کاربرهای کهنه با پیش‌فرض درون‌حافظه‌ای پر می‌شوند.
        (قرارداد: فقط افزایشی — در خودِ سند چیزی حذف نمی‌شود؛ نوشتن با رویداد بعدی)"""
        d = dict(u or {})
        d.setdefault('prestige_xp', 0)
        d.setdefault('decay_penalty', 0)
        d.setdefault('decay_blocks', 0)
        d.setdefault('rank_floor_xp', 0)
        d.setdefault('effective_xp', 0)
        d.setdefault('season_xp', 0)
        d.setdefault('season_key', 'S1-1405')
        d.setdefault('weekly_xp', 0)
        d.setdefault('weekly_reset', '')
        d.setdefault('monthly_xp', 0)          # 👑 P2 — بازه‌ی ماه لیدربرد
        d.setdefault('monthly_reset', '')
        d.setdefault('ai_conv_days', [])       # 👑 P1 — روزهای گفت‌وگوی هوشیار
        d.setdefault('submissions_approved', 0)
        d.setdefault('reports_resolved', 0)
        ch = d.get('challenge') or {}
        if not isinstance(ch, dict):
            ch = {}
        ch.setdefault('target_rank', '')
        ch.setdefault('cooldown_until', '')
        ch.setdefault('last_fail_at', '')
        ch.setdefault('apex', False)
        d['challenge'] = ch
        d.setdefault('last_gain_at', '')
        d.setdefault('last_active_day', '')
        d.setdefault('shield_answers', 0)
        d.setdefault('shield_until', '')
        d.setdefault('daily_xp', {'date': '', 'amount': 0, 'correct': 0})
        if not isinstance(d['daily_xp'], dict):
            d['daily_xp'] = {'date': '', 'amount': 0, 'correct': 0}
        d['daily_xp'].setdefault('correct', 0)
        d.setdefault('streak_current', 0)
        d.setdefault('streak_best', 0)
        d.setdefault('exams_completed', 0)
        d.setdefault('downloads_count', 0)
        rec = d.get('records') or {}
        rec.setdefault('best_acc', 0)
        rec.setdefault('best_exam_pct', 0)
        rec.setdefault('top_rank_key', 'rookie')
        rec.setdefault('top_rank_at', '')
        rec.setdefault('top_div', 3)
        rec.setdefault('top1_weeks_current', 0)
        rec.setdefault('top1_weeks_best', 0)
        rec.setdefault('apex_wins', 0)         # 👑 P1 — تعداد بردهای Apex (رکورد ابدی)
        d['records'] = rec
        d.setdefault('achievements', {})
        if not isinstance(d['achievements'], dict):
            d['achievements'] = {}
        d.setdefault('privacy_public', True)
        d.setdefault('showcase', [])
        return d

    @staticmethod
    def _tehran_today() -> str:
        from utils import now_tehran
        return now_tehran().date().isoformat()

    async def _history_add(self, uid: int, etype: str, key: str = '', detail: dict = None) -> None:
        """ثبت رویداد در prestige_history (نمایش سفر/فید — Spec §۸.۲)"""
        try:
            await self.prestige_history.insert_one({
                'uid': uid, 'type': etype, 'key': key,
                'detail': detail or {}, 'at': datetime.now().isoformat(),
                'reactions': {'clap': 0, 'fire': 0, 'crown': 0},
            })
        except Exception:
            pass

    async def _claim_global_first(self, key: str, uid: int) -> bool:
        """ادعای اتمیک نشان جهانی (Spec §۴.۲ — race غیرممکن با findOneAndUpdate)"""
        try:
            from pymongo import ReturnDocument
            doc = await self.settings.find_one_and_update(
                {'_id': 'global_firsts', f'claims.{key}': {'$exists': False}},
                {'$set': {f'claims.{key}': {'uid': uid, 'at': datetime.now().isoformat()}}},
                upsert=True, return_document=ReturnDocument.AFTER,
            )
            return bool(doc) and (doc.get('claims', {}).get(key, {}).get('uid') == uid)
        except Exception:
            return False

    def _next_info(self, idx: int, div: int, eff: int, challenge_locked: bool) -> dict:
        """هدف بعدی (دیویژن یا چالش) + مقدار لازم — قلب خط «هدف فعلی» (Spec §۵).
        have/span همیشه پر می‌شوند (پیشرفت درون بازه‌ی فعلی) تا نوار پیشرفت
        کلاینت بدون دانستن آستانه‌ها رسم شود — تک‌منبع اعداد همین‌جاست."""
        start = self.PRESTIGE_RANKS[idx][3]
        if idx >= len(self.PRESTIGE_RANKS) - 1:
            return {'kind': 'none', 'needed': 0, 'have': 1, 'span': 1,
                    'label': 'شما در اوج هستید 🌌'}
        w = self._div_width(idx)
        next_start = self.PRESTIGE_RANKS[idx + 1][3]
        if not challenge_locked and div > 1:
            nxt_div = div - 1
            boundary = start + (3 - (div - 1)) * w  # آستانه‌ی شروع div بعدی
            need = max(0, boundary - eff)
            return {'kind': 'div', 'needed': need, 'have': w - need,
                    'span': w, 'to_div': nxt_div,
                    'label': f"فقط {need} XP تا {self.PRESTIGE_RANKS[idx][1]} {self.ROMAN[nxt_div]}"}
        # مرز رنک بعد — نوار = پیشرفت در کل بازه‌ی رنک فعلی
        nxt = self.PRESTIGE_RANKS[idx + 1]
        need = max(0, next_start - eff)
        have = max(0, eff - start)
        span = max(1, next_start - start)
        if idx + 1 >= self.CHALLENGE_FROM_IDX:
            return {'kind': 'challenge', 'needed': need,
                    'have': have, 'span': span,
                    'to_rank': nxt[0], 'ready': need == 0,
                    'label': (f"⭐ چالش ارتقا آماده است — برای {nxt[2]} {nxt[1]}"
                              if need == 0 else
                              f"{need} XP تا چالش {nxt[2]} {nxt[1]}")}
        return {'kind': 'rank', 'needed': need,
                'have': have, 'span': span,
                'to_rank': nxt[0],
                'label': f"فقط {need} XP تا {nxt[2]} {nxt[1]}"}

    async def prestige_event(self, uid: int, kind: str, meta: dict = None) -> dict:
        """قلب موتور (Event-Based — Spec §۵.۱).
        kind: 'answer' (meta: is_correct, difficulty, first_time) |
              'exam_complete' (meta: pct, total)
        خروجی: خلاصه‌ی XP + رویدادها برای caller (بات→پیام، API→payload)."""
        meta = meta or {}
        raw = await self.users.find_one({'user_id': uid})
        if not raw or not raw.get('approved'):
            return {'ignored': True}
        u = self._puser(raw)
        # 👑 P3 — اوررایدهای زنده‌ی تعادل (کش ۶۰ثانیه؛ پیش‌فرض = ثابت‌های کلاس)
        cfg = await self._pcfg()
        n = lambda k, d: self._cnum(cfg, k, d)
        XP_DIFF = {'easy': n('xp_easy', self.XP_BY_DIFF['easy']),
                   'medium': n('xp_medium', self.XP_BY_DIFF['medium']),
                   'hard': n('xp_hard', self.XP_BY_DIFF['hard']),
                   'unknown': n('xp_unknown', self.XP_BY_DIFF['unknown'])}
        today = self._tehran_today()
        bdown = []                       # breakdown فارسی برای نمایش
        inc = {}                         # شمارنده‌های $inc
        sets = {}                        # فیلدهای $set
        gain = 0
        badge_awards = []                # 👑 P1 — نشان‌های بازشده در همین رویداد

        # ── rollover هفته (lazy، idempotent — Spec §۸.۱ weekly_reset)
        iso_week = f"{today[:4]}-W{datetime.fromisoformat(today).isocalendar().week:02d}"
        if u['weekly_reset'] != iso_week:
            sets['weekly_xp'] = 0
            sets['weekly_reset'] = iso_week

        # 👑 P2 — rollover ماه (تماماً هم‌الگوی هفته؛ برای بازه‌ی «ماه» لیدربرد)
        iso_month = today[:7]
        if u['monthly_reset'] != iso_month:
            sets['monthly_xp'] = 0
            sets['monthly_reset'] = iso_month

        # 👑 P2 — rollover سيزن (All-Time هرگز ریست نمی‌شود — Spec §۱۶)
        season_now = await self._season_key()
        if u.get('season_key') != season_now:
            sets['season_key'] = season_now
            sets['season_xp'] = 0

        return_idle_days = 0              # برای نشان مخفی «بازگشت قهرمان»

        # ── خوش‌آمدِ بازگشت: پاک‌سازی جریمه‌ی Decay (Spec §۳.۳)
        demoted = None
        if u['decay_penalty'] > 0 and u['last_active_day'] != today:
            sets['decay_penalty'] = 0
            sets['decay_blocks'] = 0
            sets['shield_until'] = today      # سپر روزِ برگشت (۱ روز)
            try:
                return_idle_days = (datetime.fromisoformat(today)
                                    - datetime.fromisoformat(u['last_active_day'])).days
            except Exception:
                return_idle_days = 0
            await self._history_add(uid, 'return', detail={'cleared': u['decay_penalty']})
            try:
                await self.inbox_add(uid, 'return', '🫶 خوش برگشتی',
                    'جریمه‌ی رکود پاک شد؛ امروز سپر داری. بریم ادامه بدیم 💪',
                    '/me/profile')
            except Exception:
                pass

        # ── Decay lazy روی کاربرِ در حال رکود (idempotent با decay_blocks)
        demoted = await self._apply_lazy_decay(u, today, sets)

        # ── XP بر اساس نوع رویداد (قوانین §۲.۱/§۳)
        daily = dict(u['daily_xp'])
        if daily.get('date') != today:
            daily = {'date': today, 'amount': 0, 'correct': 0}

        if kind == 'answer':
            first_time = bool(meta.get('first_time'))
            ok = bool(meta.get('is_correct'))
            if first_time:
                if ok:
                    base = XP_DIFF[self._diff_key(meta.get('difficulty'))]
                    if daily['correct'] >= n('diminish_after', self.DIMINISH_AFTER):
                        base = max(1, base // 2)     # diminishing ۵۰٪ (§۳.۳)
                    diff_fa = {'easy': 'آسان', 'medium': 'متوسط',
                               'hard': 'سخت', 'unknown': 'سؤال'}[self._diff_key(meta.get('difficulty'))]
                    bdown.append((f'پاسخ صحیح · {diff_fa}', base))
                else:
                    base = n('xp_wrong_first', self.XP_WRONG_FIRST)
                    bdown.append(('تلاش (پاسخ اولین‌بار)', base))
                room = max(0, n('daily_cap', self.DAILY_ANSWER_CAP) - daily['amount'])
                add = min(base, room)                # سقف روزانه‌ی ۱۲۰ (§۳.۲)
                gain += add
                daily['amount'] += add
                if bdown and add < bdown[-1][1]:
                    bdown[-1] = (bdown[-1][0] + ' (سقف روزانه)', add)
            if ok:
                daily['correct'] += 1
        elif kind == 'exam_complete':
            total = int(meta.get('total') or 0)
            pct = float(meta.get('pct') or 0)
            inc['exams_completed'] = 1
            if pct > (u['records'].get('best_exam_pct') or 0):
                sets['records.best_exam_pct'] = pct
            if total >= 10:
                xp_exam = n('xp_exam_complete', self.XP_EXAM_COMPLETE)
                base = xp_exam
                bdown.append(('تکمیل آزمون', base))
                if pct >= 100:
                    xp_pf = n('xp_exam_perfect', self.XP_EXAM_PERFECT)
                    base += xp_pf
                    bdown.append(('بونوس برگ کامل 🎯', xp_pf))
                elif pct >= 80:
                    xp_ac = n('xp_exam_acc80', self.XP_EXAM_ACC_BONUS)
                    base += xp_ac
                    bdown.append(('بونوس دقت بالا', xp_ac))
                gain += base               # آزمون خارج از سقف روزانه (§۳.۲)
        elif kind == 'file_download':
            # 👑 P1 — اولین دانلود هر فایل (تک‌بار — Spec §۲.۱)
            first_time = bool(meta.get('first_time'))
            if first_time:
                inc['downloads_count'] = 1
                bdown.append(('منبع جدید 📚', n('xp_file_download', self.XP_FILE_DOWNLOAD)))
                gain += n('xp_file_download', self.XP_FILE_DOWNLOAD)
        elif kind == 'ai_daily':
            # 👑 P1 — اولین گفت‌وگوی هوشیار در روز (یک‌بار/روز — Spec §۲.۱)
            days = list(u.get('ai_conv_days') or [])
            if today not in days:
                days.append(today)
                sets['ai_conv_days'] = days[-self.AI_DAYS_KEEP:]
                bdown.append(('همراهی روزانه با هوشیار 🤖', n('xp_ai_daily', self.XP_AI_DAILY)))
                gain += n('xp_ai_daily', self.XP_AI_DAILY)
        elif kind == 'question_approved':
            # 👑 P1 — تأیید سؤال طراحی‌شده‌ی کاربر (+۲۵ به طراح)
            inc['submissions_approved'] = 1
            bdown.append(('سؤال تأییدشده ✍️', n('xp_question_approved', self.XP_Q_APPROVED)))
            gain += n('xp_question_approved', self.XP_Q_APPROVED)
        elif kind == 'report_useful':
            # 👑 P1 — گزارش مفید (باگِ واقعی گزارش‌شده که resolve شد)
            inc['reports_resolved'] = 1
            bdown.append(('گزارش مفید 🕵️', n('xp_report_useful', self.XP_REPORT_USEFUL)))
            gain += n('xp_report_useful', self.XP_REPORT_USEFUL)
        elif kind == 'challenge_win':
            # 👑 P1 — برد چالش ارتقا (Spec §۳.۱: نتیجه سرورمحور)
            target_idx = int(meta.get('target_idx') or 0)
            apex = bool(meta.get('apex'))
            target_idx = max(0, min(target_idx, len(self.PRESTIGE_RANKS) - 1))
            r_t = self.PRESTIGE_RANKS[target_idx]
            reward = (n('xp_apex_win', self.XP_APEX_WIN) if apex
                      else n('xp_challenge_win', self.XP_CHALLENGE_WIN))
            bdown.append((f"برد چالش ارتقا {r_t[2]} {r_t[1]}", reward))
            gain += reward
            # کفِ رنک بالا می‌رود ⇒ قفل چالش باز و overflow آزاد می‌شود
            sets['rank_floor_xp'] = max(u['rank_floor_xp'], r_t[3])
            sets['challenge'] = {'target_rank': '', 'cooldown_until': '',
                                 'last_fail_at': '', 'apex': False}
            if apex:
                inc['records.apex_wins'] = 1
            await self._history_add(uid, 'challenge_win', r_t[0],
                                    {'apex': apex, 'pct': meta.get('pct')})
            try:
                await self.inbox_add(uid, 'challenge_win',
                    f"⚔️ برد چالش: {r_t[2]} {r_t[1]}",
                    f"آزمون با {meta.get('pct') or 0}٪ پاس شد و رسمی شدی. "
                    f"{reward}+ XP جایزه‌ی چالش + سپر ارتقا فعال شد 🛡",
                    '/me/profile')
            except Exception:
                pass
        elif kind == 'weekly_champion':
            # 👑 P2 — صدر جدول هفتگی (فقط از جاب بستن هفته — Spec §۶.۱)
            wk_str = str(meta.get('week') or '')
            bdown.append(('صدر جدول هفتگی 👑', n('xp_weekly_champion', self.XP_WEEKLY_CHAMPION)))
            gain += n('xp_weekly_champion', self.XP_WEEKLY_CHAMPION)
            prev_ct = int((u.get('achievements') or {}).get('c_top1_week', {}).get('count', 0) or 0)
            new_ct = prev_ct + 1
            sets['achievements.c_top1_week'] = {'at': datetime.now().isoformat(),
                                                'count': new_ct, 'last_week': wk_str}
            cur1 = int(u['records'].get('top1_weeks_current', 0) or 0) + 1
            sets['records.top1_weeks_current'] = cur1
            sets['records.top1_weeks_best'] = max(int(u['records'].get('top1_weeks_best', 0) or 0), cur1)
            badge_awards.append({'key': 'c_top1_week',
                                 **{k: self.BADGES_SINGLE['c_top1_week'][k]
                                    for k in ('icon', 'title', 'rarity', 'xp')},
                                 'count': new_ct})
            # XP خودِ نشان صدرنشینی (legendary +۱۲۰) هم پرداخت می‌شود
            _bxp = int(self.BADGES_SINGLE['c_top1_week']['xp'])
            bdown.append(('نشان صدرنشینی 👑', _bxp))
            gain += _bxp
            await self._history_add(uid, 'weekly_champion', wk_str, {'count': new_ct})
            try:
                await self.inbox_add(uid, 'weekly_champion', '👑 صدر هفته مال تو بود',
                    f"قهرمان جدول هفتگی شدی {'(×' + str(new_ct) + ')' if new_ct > 1 else ''} "
                    f"— {n('xp_weekly_champion', self.XP_WEEKLY_CHAMPION)}+ XP و نشان صدرنشینی 🏅",
                    '/leaderboard')
            except Exception:
                pass
        sets['daily_xp'] = daily

        # ── استریک روز (اولین فعالیت معتبر روز — تهران)
        streak_new = False
        if u['last_active_day'] != today:
            y = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
            cur = (u['streak_current'] + 1) if u['last_active_day'] == y else 1
            best = max(cur, u['streak_best'])
            sets['streak_current'] = cur
            sets['streak_best'] = best
            sets['last_active_day'] = today
            gain += n('xp_streak_day', self.XP_DAILY_STREAK)
            bdown.append(('فعالیت روزانه 🔥', n('xp_streak_day', self.XP_DAILY_STREAK)))
            streak_new = True
            u['streak_current'], u['streak_best'] = cur, best

        # ── بهترین دقت (رکورد — روی شمارنده‌های تازه‌ی legacy که save_answer زد)
        total_a = int(raw.get('total_answers', 0) or 0)
        corr_a = int(raw.get('correct_answers', 0) or 0)
        acc = round(corr_a / total_a * 100) if total_a else 0
        if acc > (u['records'].get('best_acc') or 0):
            sets['records.best_acc'] = acc

        # 👑 P1 — جاروی نشان‌ها (تکاملی ۵تایی + تک‌نسخه‌ها + جهانی‌های جدید)
        # XP نشان خارج از سقف روزانه است؛ قبل از نوشتن اصلی اعمال می‌شود.
        # ⭐ بونوس نشان/جهانی از xp_gained پاسخ جدا می‌ماند (قرارداد P0:
        # xp_gained = فقط XP رویداد اصلی) اما در DB و رنک کاملاً لحاظ می‌شود.
        bonus_xp = 0
        try:
            weekly_after = float(sets.get('weekly_xp', u['weekly_xp']) or 0) + gain
            bonus_xp += await self._badge_scan(uid, u, raw, inc, sets, bdown, badge_awards,
                {'kind': kind, 'meta': meta, 'daily': dict(daily),
                 'return_idle_days': return_idle_days,
                 'weekly_xp_after': weekly_after})
        except Exception:
            pass

        # ── جمع‌بندی XP
        total_gain = gain + bonus_xp
        if total_gain > 0:
            inc['prestige_xp'] = total_gain
            inc['season_xp'] = total_gain
            inc['weekly_xp'] = total_gain
            inc['monthly_xp'] = total_gain
            sets['last_gain_at'] = datetime.now().isoformat()
        if inc or sets:
            upd = {}
            if inc: upd['$inc'] = inc
            if sets: upd['$set'] = sets
            try:
                await self.users.update_one({'user_id': uid}, upd)
            except Exception:
                return {'ignored': True}

        # ── سپر: مصرف پاسخی
        shield_active = (u['shield_answers'] > 0) or (u['shield_until'] and u['shield_until'] >= today)
        if kind == 'answer' and u['shield_answers'] > 0:
            left = u['shield_answers'] - 1
            await self.users.update_one({'user_id': uid}, {'$set': {'shield_answers': left}})
            u['shield_answers'] = left
            shield_active = left > 0 or (u['shield_until'] and u['shield_until'] >= today)

        # ── محاسبه‌ی رنک/دیویژن جدید (با کلمپ چالش — Spec §۳.۱)
        new_xp = u['prestige_xp'] + total_gain
        penalty = sets.get('decay_penalty', u['decay_penalty'])
        floor = max(u['rank_floor_xp'], int(sets.get('rank_floor_xp', 0) or 0))
        eff = max(new_xp - penalty, floor)
        # مقایسه بر مبنای رنکِ «نمایشیِ» قبلی (کلمپ با کفِ پیشین) — وگرنه بردِ
        # چالش روی overflow انباشته هیچ رخداد rank_up‌ای نمی‌ساخت و جشن گم می‌شد
        old_idx_raw, _ = self._rank_for(u['effective_xp'])
        cap_old = max(self.CHALLENGE_FROM_IDX - 1,
                      self._rank_for(u['rank_floor_xp'])[0])
        old_idx = min(old_idx_raw, cap_old)
        old_div = int(u.get('prestige_div', 3) or 3) if old_idx == old_idx_raw else 1
        new_idx, new_div = self._rank_for(eff)
        # کلمپ: فراتر از کفِ رنک (و آستانه‌ی چالش) رنک صادر نمی‌شود؛
        # رویداد challenge_win کف را بالا می‌برد پس کلمپ هم همراهش باز می‌شود
        cap_idx = max(self.CHALLENGE_FROM_IDX - 1, self._rank_for(floor)[0])
        clamped_idx = min(new_idx, cap_idx)
        if clamped_idx < new_idx:
            new_div = 1                                # در سقف رنک آزاد می‌ایستد
        challenge_ready = new_idx > clamped_idx
        new_idx = clamped_idx
        overflow = (eff - self.PRESTIGE_RANKS[self.CHALLENGE_FROM_IDX][3]) if challenge_ready else 0
        upd2 = {'effective_xp': eff, 'prestige_div': new_div,
                'prestige_rank': self.PRESTIGE_RANKS[new_idx][0]}
        upd2['overflow_xp'] = overflow if overflow > 0 else 0
        await self.users.update_one({'user_id': uid}, {'$set': upd2})

        # ── رویدادهای ارتقا/رکورد/نشان
        events = {'streak_new_day': streak_new, 'challenge_ready': challenge_ready}
        if badge_awards:
            events['badges'] = badge_awards      # 👑 P1 — بازشدن نشان در این رویداد
        awarded_up = (new_idx > old_idx) or (new_idx == old_idx and new_div < old_div)
        if awarded_up:
            sh_a = int(n('shield_answers', self.SHIELD_ANSWERS))
            sets2 = {'shield_answers': sh_a,
                     'shield_until': (datetime.fromisoformat(today) + timedelta(days=int(n('shield_days', self.SHIELD_DAYS)))).date().isoformat()}
            await self.users.update_one({'user_id': uid}, {'$set': sets2})
            u['shield_answers'] = sh_a
            u['shield_until'] = sets2['shield_until']
            shield_active = True                     # سپرِ تازه‌ِ اهدا شده در خروجی هم دیده شود
        if new_idx > old_idx:
            r_old, r_new = self.PRESTIGE_RANKS[old_idx], self.PRESTIGE_RANKS[new_idx]
            await self.users.update_one({'user_id': uid}, {'$set': {
                'rank_floor_xp': r_new[3], 'records.top_rank_key': r_new[0],
                'records.top_rank_at': today, 'records.top_div': new_div}})
            events['rank_up'] = {'from': r_old[1], 'to': r_new[1], 'icon': r_new[2], 'key': r_new[0]}
            await self._history_add(uid, 'rank_up', r_new[0], {'from': r_old[0], 'div': new_div})
            try:
                await self.inbox_add(uid, 'rank_up', f"🎉 ارتقای رنک: {r_new[2]} {r_new[1]}",
                    f'تبریک! به رنک {r_new[2]} {r_new[1]} رسیدی. سپر ارتقا فعال شد (۳۰ پاسخ).',
                    '/me/profile')
            except Exception:
                pass
            # نشان جهانی: اولین نفری که به این رنک برسد (اتمیک — §۴.۲)
            if await self._claim_global_first(f'first_rank_{r_new[0]}', uid):
                await self.users.update_one({'user_id': uid},
                    {'$set': {f'achievements.g_first_{r_new[0]}': {'at': datetime.now().isoformat()}}})
                events['global_first'] = {'key': f'first_rank_{r_new[0]}', 'rank': r_new[1]}
                bonus_xp += await self._global_first_xp(uid, bdown)
                await self._history_add(uid, 'global_first', f'first_rank_{r_new[0]}', {'rank': r_new[1]})
                try:
                    await self.inbox_add(uid, 'global_first', '🏆 نشان جهانی تک‌نسخه!',
                        f'تو اولین نفری در تاریخ هامزیار هستی که به {r_new[2]} {r_new[1]} رسید!',
                        '/me/badges')
                except Exception:
                    pass
        elif new_idx == old_idx and new_div < old_div:
            r = self.PRESTIGE_RANKS[new_idx]
            # اوج دیویژن هم به‌روز می‌شود اگر در رنک برتر فعلی‌اش باشد
            if new_idx == self._rank_idx(u['records']['top_rank_key']) and new_div < u['records']['top_div']:
                await self.users.update_one({'user_id': uid},
                    {'$set': {'records.top_div': new_div}})
            events['div_up'] = {'rank': r[1], 'roman': self.ROMAN[new_div], 'icon': r[2]}
            await self._history_add(uid, 'div_up', r[0], {'div': new_div})
            try:
                await self.inbox_add(uid, 'div_up', f"⭐ ارتقای دسته: {r[2]} {r[1]} {self.ROMAN[new_div]}",
                    f'حالا {r[1]} {self.ROMAN[new_div]} هستی. سپر ارتقا فعال شد (۳۰ پاسخ).',
                    '/me/profile')
            except Exception:
                pass

        # ── مایل‌استون‌های استریک + نشان جهانی مرتبط
        cur_streak = u['streak_current']
        milestones = {3: 'ستریک سه‌روزه', 7: 'یک هفته‌ی پیاپی', 30: 'یک‌ماه آتشین',
                      90: 'فصل پیاپی', 180: 'نیم‌سال آتشین', 365: 'یک‌سال کامل'}
        if streak_new and cur_streak in milestones:
            await self._history_add(uid, 'streak', str(cur_streak), {})
            events['streak_milestone'] = cur_streak
            try:
                await self.inbox_add(uid, 'streak', f"🔥 استریک {cur_streak} روزه!",
                    f'{milestones[cur_streak]} — همین‌طور ادامه بده، زنجیره رو نشکن!',
                    '/me/profile')
            except Exception:
                pass
        if cur_streak >= 365 and await self._claim_global_first('first_streak365', uid):
            await self.users.update_one({'user_id': uid},
                {'$set': {'achievements.g_first_streak365': {'at': datetime.now().isoformat()}}})
            events['global_first'] = {'key': 'first_streak365'}
            bonus_xp += await self._global_first_xp(uid, bdown)
            try:
                await self.inbox_add(uid, 'global_first', '🏆 نشان جهانی تک‌نسخه!',
                    'تو اولین صاحب استریک ۳۶۵ روزه در تاریخ هامزیار هستی!', '/me/badges')
            except Exception:
                pass
        if total_a >= 10000 and await self._claim_global_first('first_q10000', uid):
            await self.users.update_one({'user_id': uid},
                {'$set': {'achievements.g_first_q10000': {'at': datetime.now().isoformat()}}})
            events['global_first'] = {'key': 'first_q10000'}
            bonus_xp += await self._global_first_xp(uid, bdown)
            try:
                await self.inbox_add(uid, 'global_first', '🏆 نشان جهانی تک‌نسخه!',
                    'تو اولین نفری هستی که مرز ۱۰٬۰۰۰ پاسخ را رد کرد!', '/me/badges')
            except Exception:
                pass

        if demoted:
            events['demote'] = demoted

        r = self.PRESTIGE_RANKS[new_idx]
        return {
            'ignored': False, 'kind': kind,
            'xp_gained': gain, 'bonus_xp': bonus_xp,
            'breakdown': [{'label': l, 'xp': x} for l, x in bdown if x > 0],
            'events': events,
            'streak': {'current': u['streak_current'], 'best': u['streak_best']},
            'shield': {'active': shield_active, 'answers_left': u['shield_answers']},
            'display': {'rank_key': r[0], 'title': r[1], 'icon': r[2], 'color': r[4],
                        'gradient': r[5],
                        'div': new_div, 'roman': self.ROMAN[new_div], 'stars': self.DIV_STARS[new_div]},
        }

    def _rank_idx(self, key: str) -> int:
        for i, r in enumerate(self.PRESTIGE_RANKS):
            if r[0] == key:
                return i
        return 0

    async def _apply_lazy_decay(self, u: dict, today: str, sets: dict):
        """Decay نرم درون‌رنکی (Spec §۳.۳) — idempotent با decay_blocks.
        فقط در غیاب سپر فعال؛ خروجی: dict رویداد demote یا None."""
        if not u['last_active_day']:
            return None
        if u['shield_answers'] > 0:
            return None
        idle_from = u['last_active_day']
        if u['shield_until'] and u['shield_until'] > idle_from:
            idle_from = u['shield_until']            # پنجره‌ی امنیت سپر لحاظ می‌شود
        try:
            days = (datetime.fromisoformat(today) - datetime.fromisoformat(idle_from)).days
        except Exception:
            return None
        # 👑 P3 — پنجره‌ی رکود قابل‌تنظیم زنده است (بدون ری‌دیپلوی)
        cfg = await self._pcfg()
        idle_days = int(self._cnum(cfg, 'decay_idle_days', self.DECAY_IDLE_DAYS))
        if days < idle_days:
            return None
        blocks = days // idle_days
        delta = blocks - u['decay_blocks']
        if delta <= 0:
            return None
        eff = u['prestige_xp'] - u['decay_penalty']
        floor = u['rank_floor_xp']
        from_idx, from_div = self._rank_for(max(eff, floor))
        to_idx, to_div = from_idx, from_div
        for _ in range(delta):
            if to_idx >= len(self.PRESTIGE_RANKS) - 1:
                break                                  # Apex ریزش نمی‌کند
            if to_div == 1:
                to_div = 2
            elif to_div == 2:
                to_div = 3
            else:
                break                                  # از III پایین‌تر نمی‌رویم
        start = self.PRESTIGE_RANKS[to_idx][3]
        w = self._div_width(to_idx)
        new_eff = max(start + (3 - to_div) * w, floor)
        win = eff - new_eff
        if win <= 0:
            sets['decay_blocks'] = blocks
            return None
        sets['decay_penalty'] = u['decay_penalty'] + win
        sets['decay_blocks'] = blocks
        sets['effective_xp'] = new_eff
        sets['prestige_div'] = to_div
        r = self.PRESTIGE_RANKS[to_idx]
        await self._history_add(u['user_id'], 'demote', r[0],
                                {'from_div': from_div, 'to_div': to_div, 'blocks': delta})
        try:
            await self.inbox_add(u['user_id'], 'demote', 'دیویژنت یک پله افتاد',
                f'به‌خاطر رکود اخیر، حالا {r[2]} {r[1]} {self.ROMAN[to_div]} هستی. '
                'رنکت محفوظ است — با چند سؤال برگرد 💪', '/me/profile')
        except Exception:
            pass
        return {'rank': r[1], 'icon': r[2], 'to_div': to_div,
                'roman': self.ROMAN[to_div], 'blocks': delta}

    async def _pc_total_active(self) -> int:
        """تعداد Active Users با کش ۱۰دقیقه‌ای (Spec §۳.۵/§۱۳ — per-request هرگز)"""
        try:
            doc = await self.settings.find_one({'_id': 'pc_cache'})
            now = datetime.now().timestamp()
            if doc and (now - float(doc.get('computed_at', 0))) < self.PC_CACHE_TTL_SEC:
                return int(doc.get('total_active', 0))
            cutoff = (datetime.fromisoformat(self._tehran_today())
                      - timedelta(days=self.ACTIVE_WINDOW_DAYS)).date().isoformat()
            total = await self.users.count_documents(
                {'approved': True, 'last_active_day': {'$gte': cutoff}})
            await self.settings.update_one(
                {'_id': 'pc_cache'},
                {'$set': {'total_active': total, 'computed_at': now}},
                upsert=True)
            return total
        except Exception:
            return 0

    async def prestige_state(self, uid: int, lite: bool = False) -> dict:
        """خواندن وضعیت نمایشی یکتا (Spec §۳.۴/§۳.۵/§۵) — بات/API/FE از همین می‌خورند.
        lite=True: بدون رقیب/رتبه‌ی عددی (مسیرهای ارزان مثل داشبورد بات)."""
        raw = await self.users.find_one({'user_id': uid})
        if not raw:
            return None
        u = self._puser(raw)
        today = self._tehran_today()
        sets = {}
        demoted = await self._apply_lazy_decay(u, today, sets)
        if sets:
            try:
                await self.users.update_one({'user_id': uid}, {'$set': sets})
            except Exception:
                pass
            u.update(sets)
        eff = max(u['prestige_xp'] - u['decay_penalty'], u['rank_floor_xp'])
        idx, div = self._rank_for(eff)
        # کلمپ چالش با کفِ رنک به‌دست‌آمده (سازگار با P1: برد چالش، کف را بالا می‌برد)
        floor_idx, _ = self._rank_for(u['rank_floor_xp'])
        cap = max(self.CHALLENGE_FROM_IDX - 1, floor_idx)
        challenge_locked = idx > cap
        if challenge_locked:
            idx, div = cap, 1
        r = self.PRESTIGE_RANKS[idx]
        state = {
            'rank_key': r[0], 'rank_idx': idx, 'title': r[1], 'icon': r[2],
            'color': r[4], 'gradient': r[5],
            'div': div, 'roman': self.ROMAN[div], 'stars': self.DIV_STARS[div],
            'apex': idx == len(self.PRESTIGE_RANKS) - 1,
            'effective_xp': eff, 'prestige_xp': u['prestige_xp'],
            'next': self._next_info(idx, div, eff, challenge_locked),
            'shield': {'active': (u['shield_answers'] > 0) or
                                 (u['shield_until'] and u['shield_until'] >= today),
                       'answers_left': u['shield_answers'], 'until': u['shield_until']},
            'streak': {'current': u['streak_current'], 'best': u['streak_best']},
            'records': u['records'],
            'demoted': demoted,
        }
        start_next = (self.PRESTIGE_RANKS[idx + 1][3]
                      if idx < len(self.PRESTIGE_RANKS) - 1 else None)
        if not lite:
            total_active = await self._pc_total_active()
            state['total_active'] = total_active
            try:
                better = await self.users.count_documents({
                    'approved': True,
                    'last_active_day': {'$gte': (datetime.fromisoformat(today)
                                                 - timedelta(days=self.ACTIVE_WINDOW_DAYS)).date().isoformat()},
                    'effective_xp': {'$gt': eff},
                })
            except Exception:
                better = 0
            state['rank_number'] = (better + 1) if total_active else None
            # Top% = ceil(rank/total*100) — Spec §۳.۵ (نورماتیو، نه round)
            rn = state['rank_number']
            state['top_pct'] = (max(1, (rn * 100 + total_active - 1) // total_active)
                                if total_active and rn else None)
            # رقیب بالا/پایین — با effective_xp (Spec §۳.۵/نکته‌ی ۸)
            async def _rival(cond, sort):
                try:
                    cur = self.users.find(
                        {'approved': True, 'user_id': {'$ne': uid}, **cond}
                    ).sort('effective_xp', sort).limit(1)
                    arr = await cur.to_list(1)
                    if not arr:
                        return None
                    v = arr[0]
                    gap = abs(int(v.get('effective_xp', 0) or 0) - eff)
                    return {'name': (v.get('name') or 'کاربر')
                                    if v.get('privacy_public', True) else 'یک دانشجو',
                            'gap': gap, 'icon': self.PRESTIGE_RANKS[
                                self._rank_for(int(v.get('effective_xp', 0) or 0))[0]][2]}
                except Exception:
                    return None
            state['rival_above'] = await _rival({'effective_xp': {'$gt': eff}}, 1)
            state['rival_below'] = await _rival({'effective_xp': {'$lt': eff}}, -1)
        if start_next and challenge_locked:
            state['overflow_xp'] = max(0, eff - start_next)
        # 👑 P1/P2 — نمای چالش (none/pending/ready/cooldown/locked) و شوکیس
        # در همان خروجی یکتای state تا بات/API/FE چیزی نسازند
        try:
            state['challenge'] = self._challenge_state_view(u, eff, today)
        except Exception:
            state['challenge'] = {'mode': 'none'}
        state['showcase_meta'] = self._showcase_meta(u)
        return state

    def _badge_seed_entries(self, ctx: dict) -> dict:
        """👑 P1 — بازنشانی سکوت نشان‌ها در Backfill (Spec §۱۴):
        نشان‌های قابل‌استناد از تاریخچه بدون **هیچ XP عقب‌گرد** ثبت می‌شوند
        (تعادل اقتصادی — ریپلای فقط XP پاسخ/آزمون است). از این لحظه به بعد
        موتور زنده، پله‌های بعدی را خودش باز می‌کند."""
        out = {}
        at = ctx.get('at') or datetime.now().isoformat()
        for bkey, (icon, title, cname, tiers) in self.BADGES_PROG.items():
            try:
                value = int(ctx.get(cname, 0) or 0)
            except Exception:
                value = 0
            reached = 0
            for i, (target, _r, _x) in enumerate(tiers, 1):
                if value >= target:
                    reached = i
                else:
                    break
            if reached:
                out[bkey] = {'tier': reached, 'at': at, 'value': value,
                             'target': tiers[reached - 1][0]}
        for bkey, ok in (ctx.get('singles') or {}).items():
            if ok and bkey in self.BADGES_SINGLE:
                out[bkey] = {'at': at}
        return out

    async def prestige_backfill(self, pause: float = 0.02) -> dict:
        """P0 — محاسبه‌ی اولیه‌ی یک‌باره‌ی Prestige از تاریخچه (Spec §۱۴).
        Idempotent (prestige_migrated)؛ replay زمانی answers + آزمون‌های تمام‌شده
        + دانلودها؛ اعطای Founder؛ claim اتمیک Global Firsts؛ ریپورت فارسی.
        قانون ویژه‌ی Backfill: کاربران قدیمی رنک‌ها را **بدون چالش** می‌گیرند
        (grandfather — چالش قانون جدیدی است و نباید عطف‌به‌ماسبق شود)."""
        from utils import now_tehran
        today = now_tehran().date().isoformat()
        iso_week = f"{today[:4]}-W{datetime.fromisoformat(today).isocalendar().week:02d}"
        rep = {'scanned': 0, 'migrated': 0, 'founders': 0, 'firsts': [], 'errors': 0}
        sessions_coll = self.client['medicalbot']['exam_sessions']
        migrated = []
        try:
            cursor = self.users.find({'approved': True,
                                      'prestige_migrated': {'$ne': True}})
            users = await cursor.to_list(100000)
        except Exception as e:
            return {**rep, 'fatal': str(e)}
        for u in users:
            rep['scanned'] += 1
            uid = u.get('user_id')
            try:
                # ── replay زمانی پاسخ‌ها (تک‌پاس؛ ترتیب answered_at حفظ می‌شود)
                ans = await self.answers.find({'user_id': uid}).sort(
                    'answered_at', 1).to_list(100000)
                seen_q = set()
                rows = []             # [(date, qid, okc)] فقط پاسخ‌های «اولین‌بار»
                dates = set()         # هر تاریخ فعالیت (حتی تکراری → استریک)
                for a in ans:
                    qid = str(a.get('question_id') or '')
                    dstr = str(a.get('answered_at') or '')[:10]
                    if dstr:
                        dates.add(dstr)
                    if not qid or qid in seen_q:
                        continue
                    seen_q.add(qid)
                    rows.append((dstr, qid, bool(a.get('is_correct'))))
                # نقشه‌ی سختی سؤال‌ها (chunk ۲۰۰)
                diff_map = {}
                uniq_q = list({r[1] for r in rows})
                for i in range(0, len(uniq_q), 200):
                    oids = []
                    for q in uniq_q[i:i + 200]:
                        try:
                            oids.append(ObjectId(q))
                        except Exception:
                            pass
                    if not oids:
                        continue
                    docs = await self.questions.find({'_id': {'$in': oids}}).to_list(200)
                    for qd in docs:
                        diff_map[str(qd.get('_id'))] = qd.get('difficulty', '')
                # پاس دوم: قوانین روزانه (cap ۱۲۰ · diminishing ×۰٫۵ از ۴۰اُم صحیح)
                daily = {}            # date → {'amount','correct'}
                day_gain = {}
                for dstr, qid, okc in rows:
                    ent = daily.setdefault(dstr, {'amount': 0, 'correct': 0})
                    if okc:
                        base = self.XP_BY_DIFF[self._diff_key(diff_map.get(qid, ''))]
                        if ent['correct'] >= self.DIMINISH_AFTER:
                            base = max(1, base // 2)
                        ent['correct'] += 1
                    else:
                        base = self.XP_WRONG_FIRST
                    add = min(base, max(0, self.DAILY_ANSWER_CAP - ent['amount']))
                    ent['amount'] += add
                    day_gain[dstr] = day_gain.get(dstr, 0) + add
                for dstr in daily:     # +۱۰ فعالیت روزانه برای هر روز دارای پاسخ
                    day_gain[dstr] = day_gain.get(dstr, 0) + self.XP_DAILY_STREAK
                xp = sum(day_gain.values())
                # ── آزمون‌های تمام‌شده
                exams_completed = 0
                best_exam_pct = 0.0
                has_perfect = False
                has_pass20 = False
                try:
                    sess = await sessions_coll.find(
                        {'user_id': uid, 'status': 'finished'}).to_list(10000)
                except Exception:
                    sess = []
                for s in sess:
                    qs = s.get('question_ids') or []
                    total = len(qs)
                    cor = int(s.get('correct', 0) or 0)
                    answered = int(s.get('answered', total) or 0)
                    pct = round(cor / answered * 100, 1) if answered else 0
                    best_exam_pct = max(best_exam_pct, pct)
                    exams_completed += 1
                    if total >= 10 and pct >= 100:
                        has_perfect = True
                    if total >= 20 and pct >= 80:
                        has_pass20 = True
                    if total >= 10:
                        g = self.XP_EXAM_COMPLETE
                        if pct >= 100:
                            g += self.XP_EXAM_PERFECT
                        elif pct >= 80:
                            g += self.XP_EXAM_ACC_BONUS
                        fdate = str(s.get('finished_at') or '')[:10]
                        day_gain[fdate] = day_gain.get(fdate, 0) + g
                        xp += g
                        if fdate:
                            dates.add(fdate)
                # ── دانلودها
                try:
                    downloads = await self.stats_col.count_documents({
                        'user_id': uid,
                        'action': {'$in': ['bs_download', 'ref_download', 'qbank_download']}})
                except Exception:
                    downloads = 0
                # 👑 P1 — شمارنده‌های مشارکت (طرح سؤال تأییدشده / گزارش مفید)
                try:
                    subs_ok = await self.questions.count_documents(
                        {'creator_id': uid, 'approved': True})
                except Exception:
                    subs_ok = 0
                try:
                    reps_ok = await self.content_reports.count_documents(
                        {'reporter_id': uid, 'status': 'resolved'})
                except Exception:
                    reps_ok = 0
                # ── استریک از روزهای فعال (متوالی‌ترین دنباله + دنباله‌ی پایانی)
                sorted_days = sorted(d for d in dates if d)
                best_run = 0
                run = 0
                prev = None
                for d in sorted_days:
                    if prev and (datetime.fromisoformat(d) - datetime.fromisoformat(prev)).days == 1:
                        run += 1
                    else:
                        run = 1
                    best_run = max(best_run, run)
                    prev = d
                tail = 0
                if sorted_days:
                    last = sorted_days[-1]
                    if last >= (now_tehran().date() - timedelta(days=1)).isoformat():
                        tail = 1
                        for i in range(len(sorted_days) - 1, 0, -1):
                            if (datetime.fromisoformat(sorted_days[i])
                                    - datetime.fromisoformat(sorted_days[i - 1])).days == 1:
                                tail += 1
                            else:
                                break
                # ── رنک بدون چالش (grandfather)
                idx, div = self._rank_for(xp)
                floor = self.PRESTIGE_RANKS[idx][3]
                week_gain = sum(g for d, g in day_gain.items()
                                if d and d[:4] == today[:4]
                                and f"{d[:4]}-W{datetime.fromisoformat(d).isocalendar().week:02d}" == iso_week) if day_gain else 0
                total_a = int(u.get('total_answers', 0) or 0)
                corr_a = int(u.get('correct_answers', 0) or 0)
                acc = round(corr_a / total_a * 100) if total_a else 0
                reg = str(u.get('registered_at') or '')[:10]
                last_gain = max(sorted_days) if sorted_days else ''
                founder_at = f"{reg}T00:00:00" if reg else datetime.now().isoformat()
                # 👑 P1 — بازنشانی نشان‌ها از شواهد تاریخی (بدون XP عقب‌گرد)
                any_day30 = any(int(e.get('correct', 0) or 0) >= 30
                                for e in daily.values())
                seeded = self._badge_seed_entries({
                    'at': founder_at,
                    'total_answers': total_a, 'streak_best': best_run,
                    'exams_completed': exams_completed,
                    'downloads_count': downloads, 'ai_conv_days': 0,
                    'singles': {
                        'q_first': total_a >= 1,
                        'e_first': exams_completed >= 1,
                        'e_pass20': has_pass20, 'exam_perfect': has_perfect,
                        'acc70': total_a >= 100 and corr_a * 100 >= total_a * 70,
                        'acc80': total_a >= 100 and corr_a * 100 >= total_a * 80,
                        'acc90': total_a >= 100 and corr_a * 100 >= total_a * 90,
                        'c_first_design': subs_ok >= 1,
                        'c_first10': subs_ok >= 10,
                        'c_first_report': reps_ok >= 1,
                        'c_reports10': reps_ok >= 10,
                        'a_q5000': total_a >= 5000,
                        'a_s365': best_run >= 365,
                        'x_30day': any_day30, 'x_week300': week_gain >= 300,
                    },
                })
                await self.users.update_one({'user_id': uid}, {'$set': {
                    'prestige_xp': xp, 'season_xp': xp, 'weekly_xp': week_gain,
                    'weekly_reset': iso_week, 'effective_xp': xp,
                    'prestige_rank': self.PRESTIGE_RANKS[idx][0], 'prestige_div': div,
                    'rank_floor_xp': floor, 'decay_penalty': 0, 'decay_blocks': 0,
                    'overflow_xp': 0,
                    'daily_xp': {'date': today, 'amount': 0, 'correct': 0},
                    'last_active_day': last_gain, 'last_gain_at': last_gain,
                    'streak_current': tail, 'streak_best': best_run,
                    'exams_completed': exams_completed, 'downloads_count': downloads,
                    'submissions_approved': subs_ok, 'reports_resolved': reps_ok,
                    'records': {'best_acc': acc, 'best_exam_pct': best_exam_pct,
                                'top_rank_key': self.PRESTIGE_RANKS[idx][0],
                                'top_rank_at': today, 'top_div': div,
                                'top1_weeks_current': 0, 'top1_weeks_best': 0},
                    'achievements': {**(u.get('achievements') or {}),
                                     'f_founder': {'at': founder_at}, **seeded},
                    'privacy_public': u.get('privacy_public', True),
                    'showcase': u.get('showcase', []),
                    'shield_answers': 0, 'shield_until': '',
                    'prestige_migrated': True,
                }})
                await self._history_add(uid, 'founder', 'f_founder',
                                        {'rank': self.PRESTIGE_RANKS[idx][0], 'xp': xp})
                try:
                    await self.inbox_add(uid, 'founder', '🏛 نشان بنیان‌گذار هامزیار',
                        f'از نخستین اعضای پلتفرمی! نشان ابدی بنیان‌گذار ثبت شد. '
                        f'رنک اولیه‌ت: {self.PRESTIGE_RANKS[idx][2]} {self.PRESTIGE_RANKS[idx][1]} '
                        f'({xp} XP از تاریخچه‌ی فعالیتت)', '/me/badges')
                except Exception:
                    pass
                rep['founders'] += 1
                rep['migrated'] += 1
                migrated.append({'uid': uid, 'xp': xp, 'idx': idx, 'reg': reg,
                                 'total_answers': total_a, 'streak_best': best_run})
                if pause:
                    await asyncio.sleep(pause)
            except Exception:
                rep['errors'] += 1
        # ── Global Firsts: بای اس تاریخی تقریبی (زودترین عضو واجد شرط)
        def _claim_of(cands, key):
            if not cands:
                return None
            win = min(cands, key=lambda c: (c['reg'] or '9999', c['uid']))
            return key, win
        first_defs = []
        for i, r in enumerate(self.PRESTIGE_RANKS):
            if i == 0:
                continue  # rookie برای همه است — «اولین rookie» معنایی ندارد
            cand = [m for m in migrated if m['xp'] >= r[3]]
            if cand:
                first_defs.append(_claim_of(cand, f'first_rank_{r[0]}'))
        q10 = [m for m in migrated if m['total_answers'] >= 10000]
        if q10:
            first_defs.append(_claim_of(q10, 'first_q10000'))
        st365 = [m for m in migrated if m['streak_best'] >= 365]
        if st365:
            first_defs.append(_claim_of(st365, 'first_streak365'))
        for item in first_defs:
            if not item:
                continue
            key, win = item
            if await self._claim_global_first(key, win['uid']):
                await self.users.update_one({'user_id': win['uid']},
                    {'$set': {f'achievements.g_first_{key.replace("first_rank_", "")}':
                              {'at': datetime.now().isoformat()}}})
                await self._history_add(win['uid'], 'global_first', key, {})
                rep['firsts'].append({'key': key, 'uid': win['uid']})
        return rep

    # ══════════════════════════════════════════════════
    #  👑 Prestige P1/P2 — نشان‌ها/چالش/لیدربرد/فید/هفته
    #  (همچنان تک‌موتور؛ همه‌ی قوانین از ثابت‌های بالای کلاس)
    # ══════════════════════════════════════════════════

    async def _season_key(self) -> str:
        """کلید سيزن فعلی از settings (کش پردازه‌ای ۶۰ ثانیه‌ای)"""
        import time as _t
        c = getattr(self, '_skc', None)
        if c and _t.time() - c['at'] < 60:
            return c['key']
        try:
            doc = await self.settings.find_one({'_id': 'season'})
            key = (doc or {}).get('key') or 'S1-1405'
        except Exception:
            key = 'S1-1405'
        self._skc = {'key': key, 'at': _t.time()}
        return key

    async def _season_info(self) -> dict:
        key = await self._season_key()
        try:
            doc = await self.settings.find_one({'_id': 'season'})
        except Exception:
            doc = None
        return {'key': key,
                'label': (doc or {}).get('label') or 'سیزن ۱ · ۱۴۰۵',
                'active': bool((doc or {}).get('active', True))}

    # ─── 👑 P3 — تنظیمات زنده‌ی تعادل (بدون ری‌دیپلوی — Spec §۱۷) ───

    async def _pcfg(self) -> dict:
        """اوررایدهای prestige_config از settings (کش پردازه‌ای ۶۰ ثانیه).
        فقط مقادیر XP/سقف/کول‌داون/سپر — آستانه‌ی رنک‌ها هرگز قابل‌اورراید نیست."""
        import time as _t
        c = getattr(self, '_pcfgc', None)
        if c and _t.time() - c['at'] < 60:
            return c['cfg']
        try:
            doc = await self.settings.find_one({'_id': 'prestige_config'})
            ov = (doc or {}).get('values') or {}
            if not isinstance(ov, dict):
                ov = {}
        except Exception:
            ov = {}
        self._pcfgc = {'cfg': ov, 'at': _t.time()}
        return ov

    @staticmethod
    def _cnum(cfg: dict, key: str, default):
        """خواندن عددی امن از اوررایدها؛ مقدار بد/ناموجود ⇒ پیش‌فرض کلاس"""
        try:
            v = cfg.get(key)
            if v is None:
                return default
            return float(v)
        except Exception:
            return default

    async def prestige_challenge_stats(self) -> dict:
        """👑 P3 — پایش چالش (پنل ادمین): شروع/برد/شکست امروز + در جریان"""
        today = self._tehran_today()
        try:
            started = await self.exam_sessions.count_documents(
                {'promotion': True, 'started_at': {'$gte': today}})
        except Exception:
            started = 0
        try:
            wins = await self.prestige_history.count_documents(
                {'type': 'challenge_win', 'at': {'$gte': today}})
        except Exception:
            wins = 0
        try:
            fails = await self.prestige_history.count_documents(
                {'type': 'challenge_fail', 'at': {'$gte': today}})
        except Exception:
            fails = 0
        try:
            pending = await self.exam_sessions.count_documents(
                {'promotion': True, 'status': 'active'})
        except Exception:
            pending = 0
        return {'started_today': started, 'wins_today': wins,
                'fails_today': fails, 'pending_now': pending}

    async def _global_first_xp(self, uid: int, bdown: list) -> int:
        """اعطای XP باستانی نشان جهانی (۵۰۰) رخ-بعداز-نوشت اصلی — جبران $inc"""
        xp = self.BADGE_RARITY['ancient'][2]
        try:
            await self.users.update_one({'user_id': uid},
                {'$inc': {'prestige_xp': xp, 'season_xp': xp,
                          'weekly_xp': xp, 'monthly_xp': xp}})
            bdown.append(('نشان جهانی تک‌نسخه 🏆', xp))
        except Exception:
            return 0
        return xp

    async def _award_global(self, uid: int, key: str, sets: dict,
                            bdown: list, badge_awards: list, label: str) -> int:
        """ادعای اتمیک + اعطای نشان جهانی جدید (داخل پنجره‌ی پیش‌از-نوشت رویداد)"""
        if not await self._claim_global_first(key, uid):
            return 0
        xp = self.BADGE_RARITY['ancient'][2]
        sets[f'achievements.g_first_{key.replace("first_", "")}'] = \
            {'at': datetime.now().isoformat()}
        bdown.append((f"🏆 نشان جهانی: {label}", xp))
        badge_awards.append({'key': f'g_first_{key.replace("first_", "")}',
                             'icon': '🏆', 'title': label,
                             'rarity': 'ancient', 'xp': xp})
        await self._history_add(uid, 'global_first', key, {'label': label})
        try:
            await self.inbox_add(uid, 'global_first', '🏆 نشان جهانی تک‌نسخه!',
                f'تو اولین نفری در تاریخ هامزیار هستی که به «{label}» رسید!',
                '/me/badges')
        except Exception:
            pass
        return xp

    async def _badge_scan(self, uid: int, u: dict, raw: dict, inc: dict,
                          sets: dict, bdown: list, badge_awards: list,
                          ctx: dict) -> int:
        """جاروی نشان‌ها — خروجی: جمع XP اعطایی (خارج از سقف).
        پله‌ها یک‌در هر رویداد جلو می‌روند (ضدسیل)، تک‌نسخه‌ها هم‌زمان."""
        xp_total = 0
        ach = u.get('achievements') or {}
        # پاسخِ در‌حالِ ثبت (prestige_event پیش از save_answer صدا زده می‌شود)
        # در شمارنده‌های نشان لحاظ می‌شود تا آستانه‌ها off-by-one نشوند
        kind = ctx.get('kind')
        meta = ctx.get('meta') or {}
        inflight = 1 if kind == 'answer' else 0
        total_a = int(raw.get('total_answers', 0) or 0) + inflight
        corr_a = int(raw.get('correct_answers', 0) or 0) + \
            (inflight if meta.get('is_correct') else 0)
        counters = {
            'total_answers': total_a,
            'streak_best': int(sets.get('streak_best', u.get('streak_best', 0) or 0)),
            'exams_completed': int(u.get('exams_completed', 0) or 0)
                               + int(inc.get('exams_completed', 0) or 0),
            'downloads_count': int(u.get('downloads_count', 0) or 0)
                               + int(inc.get('downloads_count', 0) or 0),
            'ai_conv_days': len(sets.get('ai_conv_days', u.get('ai_conv_days') or [])),
            'submissions': int(u.get('submissions_approved', 0) or 0)
                           + int(inc.get('submissions_approved', 0) or 0),
            'reports': int(u.get('reports_resolved', 0) or 0)
                       + int(inc.get('reports_resolved', 0) or 0),
        }
        now_iso = datetime.now().isoformat()

        # ── ۵ نشان تکاملی (فقط یک پله‌ی جلو در هر رویداد)
        for bkey, (icon, title, cname, tiers) in self.BADGES_PROG.items():
            cur_tier = int((ach.get(bkey) or {}).get('tier', 0) or 0)
            value = counters.get(cname, 0)
            reached = 0
            for i, (target, _r, _x) in enumerate(tiers, 1):
                if value >= target:
                    reached = i
                else:
                    break
            if reached <= cur_tier or cur_tier >= len(tiers):
                continue
            nxt = cur_tier + 1
            target, rarity, xp = tiers[nxt - 1]
            sets[f'achievements.{bkey}'] = {'tier': nxt, 'at': now_iso,
                                            'value': value, 'target': target}
            bdown.append((f"نشان {icon} {title} · پله {nxt}", xp))
            xp_total += xp
            badge_awards.append({'key': bkey, 'icon': icon, 'title': title,
                                 'rarity': rarity, 'xp': xp, 'tier': nxt,
                                 'tiers_count': len(tiers)})
            await self._history_add(uid, 'achievement', bkey,
                                    {'tier': nxt, 'rarity': rarity, 'value': value})
            try:
                await self.inbox_add(uid, 'achievement',
                    f"{icon} نشان جدید: {title} — پله {nxt}",
                    f"پله {nxt} از {len(tiers)} ({self.BADGE_RARITY[rarity][0]}) باز شد؛ {xp}+ XP 🎉",
                    '/me/badges')
            except Exception:
                pass

        # ── تک‌نسخه‌های مشروط (kind/meta از ابتدای جارو)
        daily = ctx.get('daily') or {}
        exam_total = int(meta.get('total') or 0)
        exam_pct = float(meta.get('pct') or 0)
        from utils import now_tehran
        hour = now_tehran().hour
        weekly_after = float(ctx.get('weekly_xp_after') or 0)
        conds = {
            'q_first': total_a >= 1,
            'e_first': counters['exams_completed'] >= 1,
            'ai_first': counters['ai_conv_days'] >= 1,
            'e_pass20': kind == 'exam_complete' and exam_total >= 20 and exam_pct >= 80,
            'exam_perfect': kind == 'exam_complete' and exam_total >= 10 and exam_pct >= 100,
            'lesson_done': kind == 'file_download' and bool(meta.get('lesson_done')),
            'ai_image': kind == 'ai_feature' and meta.get('feature') == 'image',
            'ai_pdf': kind == 'ai_feature' and meta.get('feature') == 'pdf',
            'acc70': total_a >= 100 and corr_a * 100 >= total_a * 70,
            'acc80': total_a >= 100 and corr_a * 100 >= total_a * 80,
            'acc90': total_a >= 100 and corr_a * 100 >= total_a * 90,
            'c_first_design': counters['submissions'] >= 1,
            'c_first10': counters['submissions'] >= 10,
            'c_first_report': counters['reports'] >= 1,
            'c_reports10': counters['reports'] >= 10,
            'x_owl': 0 <= hour <= 3,
            'x_lark': 5 <= hour <= 7,
            'x_30day': int(daily.get('correct', 0) or 0) >= 30,
            'x_comeback': int(ctx.get('return_idle_days') or 0) >= 14,
            'x_week300': weekly_after >= 300,
            'a_q5000': total_a >= 5000,
            'a_s365': counters['streak_best'] >= 365,
        }
        for bkey, ok in conds.items():
            if not ok or bkey in ach:
                continue
            info = self.BADGES_SINGLE[bkey]
            sets[f'achievements.{bkey}'] = {'at': now_iso}
            xp = int(info['xp'])
            if xp > 0:
                bdown.append((f"نشان {info['icon']} {info['title']}", xp))
            xp_total += xp
            badge_awards.append({'key': bkey,
                                 **{k: info[k] for k in ('icon', 'title', 'rarity', 'xp')}})
            await self._history_add(uid, 'achievement', bkey, {'rarity': info['rarity']})
            try:
                await self.inbox_add(uid, 'achievement',
                    f"{info['icon']} نشان جدید: {info['title']}",
                    f"{info['desc']} — {xp}+ XP 🎉" if xp > 0 else info['desc'],
                    '/me/badges')
            except Exception:
                pass

        # ── جهانی‌های جدید (اتمیک — Spec §۴.۲)
        if kind == 'exam_complete' and exam_total >= 10 and exam_pct >= 100:
            xp_total += await self._award_global(
                uid, 'first_perfect', sets, bdown, badge_awards,
                'اولین آزمون برگ‌کامل')
        if counters['submissions'] >= 10:
            xp_total += await self._award_global(
                uid, 'first_contrib10', sets, bdown, badge_awards,
                'اولین ۱۰ مشارکت تأییدشده')
        return xp_total

    # ───────── چالش ارتقا (Spec §۳.۱) ─────────

    def _challenge_state_view(self, u: dict, eff: int, today: str) -> dict:
        """وضعیت چالش کاربر — none|pending|ready|cooldown|locked (Spec §۳.۴)"""
        floor_idx = self._rank_for(u['rank_floor_xp'])[0]
        target_idx = floor_idx + 1
        if target_idx >= len(self.PRESTIGE_RANKS):
            return {'mode': 'none'}
        if target_idx < self.CHALLENGE_FROM_IDX:
            return {'mode': 'none'}               # سه رنک اول بدون چالش
        r = self.PRESTIGE_RANKS[target_idx]
        apex = target_idx == len(self.PRESTIGE_RANKS) - 1
        start = r[3]
        base = {'target_rank': r[0], 'title': r[1], 'icon': r[2],
                'apex': apex, 'start': start}
        if eff < start:
            return {'mode': 'pending', **base, 'needed_xp': start - eff}
        ch = u.get('challenge') or {}
        cd_until = ch.get('cooldown_until') or ''
        now_iso = datetime.now().isoformat()
        if cd_until and cd_until > now_iso:
            return {'mode': 'cooldown', **base,
                    'cooldown_until': cd_until, 'overflow_xp': max(0, eff - start)}
        if apex:
            streak_ok = int(u.get('streak_best', 0) or 0) >= self.CH_APEX_STREAK_REQ
            contrib_ok = int(u.get('submissions_approved', 0) or 0) >= self.CH_APEX_CONTRIB_REQ
            if not (streak_ok and contrib_ok):
                return {'mode': 'locked', **base,
                        'overflow_xp': max(0, eff - start),
                        'need': {'streak_best': self.CH_APEX_STREAK_REQ,
                                 'contrib': self.CH_APEX_CONTRIB_REQ},
                        'have': {'streak_best': int(u.get('streak_best', 0) or 0),
                                 'contrib': int(u.get('submissions_approved', 0) or 0)}}
        return {'mode': 'ready', **base, 'overflow_xp': max(0, eff - start)}

    async def challenge_pool(self, uid: int, apex: bool = False):
        """استخر سؤال چالش — pool-200 + fallback پنجره‌ها + mixin ≥۴۰٪ (Spec §۳.۱)"""
        import random
        need = self.CH_APEX_COUNT if apex else self.CH_COUNT
        cur = self.answers.find({'user_id': uid}).sort('answered_at', -1) \
            .limit(self.CH_EXCLUDE_RECENT)
        ans = await cur.to_list(self.CH_EXCLUDE_RECENT)
        recent = []
        seen = set()
        for a in ans:
            q = str(a.get('question_id') or '')
            if q and q not in seen:
                seen.add(q)
                recent.append(q)
        windows = [self.CH_EXCLUDE_RECENT] + list(self.CH_EXCLUDE_FALLBACK)
        selected = None
        used_window = windows[-1]
        for w in windows:
            excluded = set(recent[:w])
            docs = await self.questions.find({'approved': True}).to_list(5000)
            pool = [d for d in docs if str(d.get('_id')) not in excluded]
            if len(pool) >= need:
                selected = pool
                used_window = w
                break
        if selected is None:
            logger.warning(f"challenge_pool: استخر ناکافی برای {uid} "
                           f"(حتی با پنجره‌ی {used_window})")
            return None, {'window': used_window}
        buckets = {'easy': [], 'medium': [], 'hard': [], 'unknown': []}
        for d in selected:
            buckets[self._diff_key(d.get('difficulty'))].append(d)
        for b in buckets.values():
            random.shuffle(b)
        # سقف‌گذاری به بالا: حداقل ۴۰٪ متوسط+سخت (ceilِ امن)
        mix_min = max(1, int(round(need * self.CH_MIX_MIN_HARDMED + 0.4999)))
        mix = buckets['medium'] + buckets['hard']
        random.shuffle(mix)
        take = mix[:mix_min]
        taken_ids = {str(d.get('_id')) for d in take}
        rest = [d for d in (buckets['easy'] + buckets['unknown'] +
                            buckets['medium'] + buckets['hard'])
                if str(d.get('_id')) not in taken_ids]
        random.shuffle(rest)
        chosen = take + rest[:need - len(take)]
        random.shuffle(chosen)
        fallback_hit = used_window != self.CH_EXCLUDE_RECENT
        if fallback_hit:
            logger.warning(f"challenge_pool fallback: window {used_window} برای {uid}")
        return [str(d.get('_id')) for d in chosen], \
            {'window': used_window, 'mix_hardmed': min(len(take), need),
             'fallback': fallback_hit}

    async def challenge_start_check(self, uid: int) -> dict:
        """واجد‌شرط‌بودن شروع چالش — خروجی dict برای روتر (قرارداد §۱۵/§۱۲)"""
        raw = await self.users.find_one({'user_id': uid})
        if not raw or not raw.get('approved'):
            return {'ok': False, 'code': 'not_approved'}
        u = self._puser(raw)
        today = self._tehran_today()
        sets = {}
        await self._apply_lazy_decay(u, today, sets)
        if sets:
            try:
                await self.users.update_one({'user_id': uid}, {'$set': sets})
            except Exception:
                pass
            u.update(sets)
        eff = max(u['prestige_xp'] - u['decay_penalty'], u['rank_floor_xp'])
        view = self._challenge_state_view(u, eff, today)
        mode = view['mode']
        if mode != 'ready':
            out = {'ok': False, 'code': mode, 'view': view}
            if mode == 'cooldown':
                try:
                    rem = datetime.fromisoformat(view['cooldown_until']) - datetime.now()
                    out['hours_left'] = max(1, int(-(-rem.total_seconds() // 3600)))
                except Exception:
                    out['hours_left'] = None
            return out
        sess = await self.exam_sessions.find_one(
            {'user_id': uid, 'promotion': True, 'status': 'active'})
        if sess:
            # چک TTL: جلسه‌ی منقضی = Fail خودکار + کول‌داون (ضدتقلب)؛
            # ⚠️ بلافاصله کول‌داون برگردان — اجازه‌ی شروع تازه در همان نفس نیست
            exp = sess.get('expires_ts')
            if exp and int(datetime.now().timestamp()) >= int(exp):
                await self.challenge_expire_session(sess)
                raw2 = await self.users.find_one({'user_id': uid}) or {}
                until = str((raw2.get('challenge') or {}).get('cooldown_until') or '')
                out = {'ok': False, 'code': 'cooldown', 'expired_ttl': True,
                       'cooldown_until': until, 'view': view}
                try:
                    rem = datetime.fromisoformat(until) - datetime.now()
                    out['hours_left'] = max(1, int(-(-rem.total_seconds() // 3600)))
                except Exception:
                    out['hours_left'] = None
                return out
            return {'ok': True, 'resume': True,
                    'session_id': sess.get('session_id'), 'view': view}
        apex = bool(view.get('apex'))
        pool, pmeta = await self.challenge_pool(uid, apex)
        need = self.CH_APEX_COUNT if apex else self.CH_COUNT
        if not pool or len(pool) < need:
            return {'ok': False, 'code': 'insufficient_pool', 'view': view,
                    'pool_meta': pmeta}
        return {'ok': True, 'resume': False, 'pool': pool, 'view': view,
                'pool_meta': pmeta, 'apex': apex}

    async def challenge_expire_session(self, sess: dict) -> None:
        """TTL/رهاکردن چالش = Fail + کول‌داون (ضدتقلب — Spec §۳.۱)"""
        try:
            await self.exam_sessions.update_one(
                {'_id': sess['_id']},
                {'$set': {'status': 'failed',
                          'finished_at': datetime.now().isoformat()}})
        except Exception:
            pass
        uid = sess.get('user_id')
        answered = int(sess.get('answered', 0) or 0)
        correct = int(sess.get('correct', 0) or 0)
        pct = round(correct / answered * 100, 1) if answered else 0
        await self.challenge_resolve(uid, sess, False, pct)

    async def challenge_resolve(self, uid: int, session: dict,
                                won: bool, pct: float) -> dict:
        """نتیجه‌ی سرورمحور چالش (Spec §۱۵ — کلاینت فقط state می‌خواند)"""
        target_key = session.get('target_rank') or ''
        apex = bool(session.get('apex'))
        target_idx = self._rank_idx(target_key)
        if won:
            ev = await self.prestige_event(uid, 'challenge_win',
                                           {'target_idx': target_idx,
                                            'apex': apex, 'pct': pct})
            return {'win': True, 'pct': pct, 'event': ev,
                    'celebration': (ev.get('events') or {}).get('rank_up')}
        # 👑 P3 — کول‌داون قابل‌تنظیم زنده (پیش‌فرض: ۱۲عادی / ۴۸Apex)
        _cfgc = await self._pcfg()
        cooldown_h = (int(self._cnum(_cfgc, 'challenge_cooldown_apex_h',
                                     self.CH_APEX_COOLDOWN_H)) if apex
                      else int(self._cnum(_cfgc, 'challenge_cooldown_h',
                                          self.CH_COOLDOWN_H)))
        until = (datetime.now() + timedelta(hours=cooldown_h)).isoformat()
        await self.users.update_one({'user_id': uid}, {'$set': {
            'challenge.target_rank': target_key, 'challenge.apex': apex,
            'challenge.cooldown_until': until,
            'challenge.last_fail_at': datetime.now().isoformat()}})
        await self._history_add(uid, 'challenge_fail', target_key,
                                {'pct': pct, 'cooldown_h': cooldown_h})
        try:
            await self.inbox_add(uid, 'challenge_fail', 'نزدیک بود 💪',
                f'این بار نشد ({pct}٪). هیچ جریمه‌ای نیست — '
                f'{cooldown_h} ساعت دیگر دوباره می‌تونی.', '/learn/exams?promo=1')
        except Exception:
            pass
        return {'win': False, 'pct': pct,
                'cooldown_until': until, 'cooldown_h': cooldown_h}

    # ───────── کلکسیون نشان‌ها (Spec §۴) ─────────

    def _badge_meta(self, key: str, u: dict):
        ach = (u or {}).get('achievements') or {}
        if key in self.BADGES_PROG:
            icon, title, _c, tiers = self.BADGES_PROG[key]
            tier = int((ach.get(key) or {}).get('tier', 0) or 0)
            rarity = tiers[tier - 1][1] if tier else 'common'
            return {'key': key, 'icon': icon, 'title': title, 'rarity': rarity,
                    'tier': tier, 'tiers_count': len(tiers),
                    'color': self.BADGE_RARITY[rarity][1]}
        if key in self.BADGES_SINGLE:
            info = self.BADGES_SINGLE[key]
            return {'key': key,
                    **{k: info[k] for k in ('icon', 'title', 'rarity')},
                    'color': self.BADGE_RARITY[info['rarity']][1]}
        if key.startswith('g_first'):
            labels = {'g_first_q10000': ('🏆', 'اولین ۱۰٬۰۰۰ پاسخ'),
                      'g_first_streak365': ('🕯', 'اولین استریک ۳۶۵'),
                      'g_first_perfect': ('🎯', 'اولین آزمون برگ‌کامل'),
                      'g_first_contrib10': ('🏛', 'اولین ۱۰ مشارکت'),
                      'g_first_founder': ('🏛', 'بنیان‌گذار جهانی')}
            if key in labels:
                icon, title = labels[key]
            else:
                rk = key.replace('g_first_', '')
                idx = self._rank_idx(rk)
                r = self.PRESTIGE_RANKS[idx]
                icon, title = r[2], f'اولین {r[1]}'
            return {'key': key, 'icon': icon, 'title': title,
                    'rarity': 'ancient', 'color': self.BADGE_RARITY['ancient'][1]}
        return None

    def _showcase_meta(self, u: dict) -> list:
        out = []
        for key in (u.get('showcase') or [])[:self.SHOWCASE_MAX]:
            m = self._badge_meta(key, u)
            if m:
                out.append(m)
        return out

    async def prestige_showcase_set(self, uid: int, keys: list) -> dict:
        """📌 پین حداکثر ۳ نشان بازشده (Spec §۴.۴) — اعتبارسنجی سروری"""
        raw = await self.users.find_one({'user_id': uid})
        if not raw:
            return {'ok': False, 'code': 'not_found'}
        u = self._puser(raw)
        ach = u.get('achievements') or {}
        clean, rejected = [], []
        for k in (keys or [])[:self.SHOWCASE_MAX]:
            k = str(k).strip()
            if k and k in ach and self._badge_meta(k, u):
                clean.append(k)
            else:
                rejected.append(k)
        await self.users.update_one({'user_id': uid},
                                    {'$set': {'showcase': clean}})
        return {'ok': True, 'showcase': self._showcase_meta({**u, 'showcase': clean}),
                'rejected': rejected}

    async def prestige_badges(self, uid: int) -> dict:
        """کلکسیون کامل برای صفحه‌ی نشان‌ها (Spec §۴.۳)"""
        raw = await self.users.find_one({'user_id': uid})
        if not raw:
            return None
        u = self._puser(raw)
        ach = u.get('achievements') or {}
        counters = {
            'total_answers': int(raw.get('total_answers', 0) or 0),
            'streak_best': int(u.get('streak_best', 0) or 0),
            'exams_completed': int(u.get('exams_completed', 0) or 0),
            'ai_conv_days': len(u.get('ai_conv_days') or []),
            'downloads_count': int(u.get('downloads_count', 0) or 0),
        }
        progressive = []
        for bkey, (icon, title, cname, tiers) in self.BADGES_PROG.items():
            cur_tier = int((ach.get(bkey) or {}).get('tier', 0) or 0)
            value = counters.get(cname, 0)
            nxt = tiers[cur_tier] if cur_tier < len(tiers) else None
            rarity = tiers[cur_tier - 1][1] if cur_tier else 'common'
            progressive.append({
                'key': bkey, 'icon': icon, 'title': title,
                'tier': cur_tier, 'tiers_count': len(tiers),
                'rarity': rarity, 'color': self.BADGE_RARITY[rarity][1],
                'value': value,
                'next_target': nxt[0] if nxt else None,
                'next_xp': nxt[2] if nxt else None,
                'tiers': [{'target': t, 'rarity': r, 'xp': x} for t, r, x in tiers],
            })
        singles = []
        for bkey, info in self.BADGES_SINGLE.items():
            if bkey == 'f_founder':
                secret_locked = False
            else:
                secret_locked = info.get('secret') and bkey not in ach
            item = {
                'key': bkey, 'kind': info['kind'],
                'rarity': info['rarity'], 'xp': info['xp'],
                'color': self.BADGE_RARITY[info['rarity']][1],
            }
            if secret_locked:
                item.update({'icon': '❔', 'title': 'نشان مخفی',
                             'desc': info.get('hint') or '؟؟؟', 'secret': True,
                             'earned': False})
            else:
                item.update({'icon': info['icon'], 'title': info['title'],
                             'desc': info['desc'], 'secret': False,
                             'earned': bkey in ach,
                             'at': (ach.get(bkey) or {}).get('at', '')})
            if bkey == 'c_top1_week' and bkey in ach:
                item['count'] = int(ach[bkey].get('count', 1) or 1)
            singles.append(item)
        # جهانی‌ها — صاحب هر کلید (privacy-aware)
        claims = {}
        try:
            doc = await self.settings.find_one({'_id': 'global_firsts'})
            claims = (doc or {}).get('claims', {}) or {}
        except Exception:
            pass
        globals_list = []
        owner_uids = list({v.get('uid') for v in claims.values() if v.get('uid')})
        names = {}
        if owner_uids:
            try:
                docs = await self.users.find({'user_id': {'$in': owner_uids}},
                                             {'user_id': 1, 'name': 1,
                                              'privacy_public': 1}).to_list(len(owner_uids))
                names = {d['user_id']:
                         ((d.get('name') or 'کاربر') if d.get('privacy_public', True)
                          else 'یک دانشجو') for d in docs}
            except Exception:
                pass
        rank_first_keys = [f'first_rank_{r[0]}' for r in self.PRESTIGE_RANKS[1:]] + \
                          ['first_q10000', 'first_streak365',
                           'first_perfect', 'first_contrib10']
        for gk in rank_first_keys:
            claim = claims.get(gk)
            if gk.startswith('first_rank_'):
                rk = gk.replace('first_rank_', '')
                idx = self._rank_idx(rk)
                r = self.PRESTIGE_RANKS[idx]
                icon, title = r[2], f'اولین {r[1]}'
            else:
                icon, title = {
                    'first_q10000': ('🏆', 'اولین ۱۰٬۰۰۰ پاسخ'),
                    'first_streak365': ('🕯', 'اولین استریک ۳۶۵'),
                    'first_perfect': ('🎯', 'اولین آزمون برگ‌کامل'),
                    'first_contrib10': ('🏛', 'اولین ۱۰ مشارکت'),
                }[gk]
            globals_list.append({
                'key': gk, 'icon': icon, 'title': title,
                'rarity': 'ancient', 'color': self.BADGE_RARITY['ancient'][1],
                'claimed': bool(claim),
                'owner_name': (names.get(claim.get('uid'), '؟')
                               if claim else None),
                'owned_by_me': bool(claim and claim.get('uid') == uid),
                'owner_uid': (claim or {}).get('uid'),
            })
        return {'progressive': progressive, 'singles': singles,
                'global': globals_list,
                'showcase': (u.get('showcase') or [])[:self.SHOWCASE_MAX]}

    async def prestige_history_list(self, uid: int, limit: int = 30) -> list:
        """📜 سفر من — تایم‌لاین رنک/نشان/چالش با تاریخ جلالی (Spec §۵)"""
        from utils import fmt_jalali_dt
        rows = await self.prestige_history.find({'uid': uid}) \
            .sort('at', -1).limit(limit).to_list(limit)
        type_labels = {'rank_up': '⬆️ ارتقای رنک', 'div_up': '⭐ ارتقای دسته',
                       'demote': '⬇️ افت دسته', 'achievement': '🏅 نشان',
                       'streak': '🔥 مایل‌استون استریک', 'global_first': '🏆 نشان جهانی',
                       'challenge_win': '⚔️ برد چالش', 'challenge_fail': '💔 شکست چالش',
                       'weekly_champion': '👑 صدر هفته', 'founder': '🏛 بنیان‌گذار',
                       'return': '🫶 بازگشت'}
        out = []
        for r in rows:
            detail = r.get('detail') or {}
            title = type_labels.get(r.get('type'), r.get('type', ''))
            try:
                at_jalali = fmt_jalali_dt(str(r.get('at', '')))
            except Exception:
                at_jalali = str(r.get('at', ''))[:16].replace('T', ' ')
            out.append({'type': r.get('type'), 'key': r.get('key', ''),
                        'title': title, 'detail': detail,
                        'at': r.get('at'), 'at_jalali': at_jalali})
        return out

    # ───────── Leaderboard (Spec §۶.۱) ─────────

    def _lb_metric(self, u: dict, raw: dict, tab: str, range_: str):
        if tab == 'acc':
            total = int(raw.get('total_answers', 0) or 0)
            if total < 100:
                return None
            return round(int(raw.get('correct_answers', 0) or 0) / total * 1000) / 10
        if tab == 'exam':
            return int(u.get('exams_completed', 0) or 0)
        if tab == 'contrib':
            return int(u.get('submissions_approved', 0) or 0)
        # xp با بازه
        if range_ == 'month':
            return int(u.get('monthly_xp', 0) or 0)
        if range_ == 'season':
            return int(u.get('season_xp', 0) or 0)
        if range_ == 'all':
            return int(u.get('effective_xp', 0) or 0)
        return int(u.get('weekly_xp', 0) or 0)

    async def prestige_leaderboard(self, me_uid: int, range_: str = 'week',
                                   scope: str = 'all', tab: str = 'xp',
                                   limit: int = 50) -> dict:
        """ماتریس بازه×دامنه×تب + dense rank + Jump + رقبا (Spec §۶.۱/§۳.۵)"""
        me_raw = await self.users.find_one({'user_id': me_uid}) or {}
        intake = str(me_raw.get('intake') or '')
        group = str(me_raw.get('group') or '')
        scope_filter = {}
        scope_key = scope
        if scope == 'intake' and intake:
            scope_filter['intake'] = intake
            scope_key = f"intake:{intake}"
        elif scope == 'group' and group:
            scope_filter['group'] = group
            scope_key = f"group:{group}"
        elif scope in ('intake', 'group'):
            scope = 'all'
            scope_key = 'all'
        cache_id = f"lb_cache:{range_}:{scope_key}:{tab}:{limit}"
        cached = None
        try:
            doc = await self.settings.find_one({'_id': cache_id})
            if doc and (datetime.now().timestamp()
                        - float(doc.get('computed_at', 0))) < self.PC_CACHE_TTL_SEC:
                cached = doc.get('payload')
        except Exception:
            cached = None
        if cached is None:
            docs = await self.users.find({'approved': True, **scope_filter}) \
                .to_list(100000)
            rows = []
            for raw2 in docs:
                uu = self._puser(raw2)
                v = self._lb_metric(uu, raw2, tab, range_)
                if v is None:
                    continue
                if v <= 0 and range_ in ('week', 'month', 'season') and tab == 'xp':
                    continue
                rows.append({
                    'uid': int(raw2.get('user_id', 0) or 0),
                    # 🏷 Identity v1 — display_name + حفظ privacy
                    # قدیمی (privacy_public=False ⇒ ناشناس، دست‌نخورده)
                    'name': self.display_name_of(raw2)
                            if uu.get('privacy_public', True) else 'یک دانشجو',
                    'privacy': bool(uu.get('privacy_public', True)),
                    'value': v,
                    'streak': int(uu.get('streak_current', 0) or 0),
                    'last_gain_at': uu.get('last_gain_at') or '9999',
                    'registered_at': str(raw2.get('registered_at') or '9999'),
                    'rank_key': uu.get('prestige_rank') or 'rookie',
                    'div': int(raw2.get('prestige_div', 3) or 3),
                    'icon': self.PRESTIGE_RANKS[self._rank_idx(uu.get('prestige_rank') or 'rookie')][2],
                    'title': self.PRESTIGE_RANKS[self._rank_idx(uu.get('prestige_rank') or 'rookie')][1],
                    'color': self.PRESTIGE_RANKS[self._rank_idx(uu.get('prestige_rank') or 'rookie')][4],
                    'roman': self.ROMAN[int(raw2.get('prestige_div', 3) or 3)],
                    'stars': self.DIV_STARS[int(raw2.get('prestige_div', 3) or 3)],
                })
            rows.sort(key=lambda r: (-r['value'], -r['streak'],
                                     r['last_gain_at'], r['registered_at']))
            # dense rank (Spec §۳.۵ب) + Jump از snapshot (فقط week+xp)
            snap = {}
            if range_ == 'week' and tab == 'xp':
                try:
                    sdoc = await self.settings.find_one({'_id': 'lb_snapshot_week'})
                    snap = (sdoc or {}).get('positions', {}) or {}
                except Exception:
                    snap = {}
            prev_val = None
            dense = 0
            for r in rows:
                # dense rank بدون شکاف (۱٬۱٬۲) — هم‌قاعده با rank_number/Top% در state
                if prev_val is None or r['value'] < prev_val:
                    dense += 1
                    prev_val = r['value']
                r['rank'] = dense
                old_pos = snap.get(str(r['uid']), snap.get(r['uid']))
                r['jump'] = (int(old_pos) - dense) if old_pos else None
            # ردیف «من» حتی اگر بیرون از برش limit باشد (ردیف چسبان FE)
            me_full = next((r for r in rows if r['uid'] == me_uid), None)
            top_rows = rows[:limit]
            cached = {'rows': top_rows, 'total': len(rows), 'me': me_full}
            try:
                await self.settings.update_one({'_id': cache_id},
                    {'$set': {'payload': cached,
                              'computed_at': datetime.now().timestamp()}},
                    upsert=True)
            except Exception:
                pass
        rows_out = [dict(r, is_me=(r['uid'] == me_uid)) for r in cached['rows']]
        me_row = (dict(cached['me'], is_me=True) if cached.get('me') else None)
        # رقیب بالا/پایین با effective_xp (§۳.۵) — تک‌منبع با state
        eff_mc = max(int(me_raw.get('prestige_xp', 0) or 0)
                     - int(me_raw.get('decay_penalty', 0) or 0),
                     int(me_raw.get('rank_floor_xp', 0) or 0))
        rival_above = await self._rival_row(me_uid, {'effective_xp': {'$gt': eff_mc}}, 1, eff_mc)
        rival_below = await self._rival_row(me_uid, {'effective_xp': {'$lt': eff_mc}}, -1, eff_mc)
        season = await self._season_info()
        return {'range': range_, 'scope': scope, 'tab': tab,
                'rows': rows_out, 'me': me_row, 'total_users': cached['total'],
                'rival_above': rival_above, 'rival_below': rival_below,
                'season': season}

    async def _rival_row(self, uid: int, cond: dict, sort_dir: int, my_eff: int):
        try:
            cur = self.users.find({'approved': True, 'user_id': {'$ne': uid}, **cond}) \
                .sort('effective_xp', sort_dir).limit(1)
            arr = await cur.to_list(1)
            if not arr:
                return None
            v = arr[0]
            gap = abs(int(v.get('effective_xp', 0) or 0) - my_eff)
            return {'name': (v.get('name') or 'کاربر')
                            if v.get('privacy_public', True) else 'یک دانشجو',
                    'gap': gap,
                    'icon': self.PRESTIGE_RANKS[
                        self._rank_for(int(v.get('effective_xp', 0) or 0))[0]][2]}
        except Exception:
            return None

    # ───────── Daily Feed + Reactions (Spec §۶.۳) ─────────

    FEED_WINDOW_H = 48

    def _feed_label(self, doc: dict, name: str) -> str:
        t = doc.get('type')
        key = str(doc.get('key') or '')
        detail = doc.get('detail') or {}
        if t == 'rank_up':
            idx = self._rank_idx(key)
            r = self.PRESTIGE_RANKS[idx]
            return f"🔥 {name} به {r[2]} {r[1]} رسید"
        if t == 'achievement':
            meta = (self.BADGES_SINGLE.get(key) or {})
            icon = meta.get('icon') or '🏅'
            title = meta.get('title') or (self.BADGES_PROG.get(key, ('🏅', key, '', []))[1])
            return f"🏅 {name} نشان {icon} {title} را گرفت"
        if t == 'global_first':
            return f"🏆 {name} اولین نفر در تاریخ هامزیار شد"
        if t == 'weekly_champion':
            return f"👑 صدر هفته: {name}"
        if t == 'streak':
            return f"🔥 استریک {key} روزه‌ی {name}"
        return f"✨ {name}"

    def _feed_is_public(self, doc: dict) -> bool:
        t = doc.get('type')
        if t == 'rank_up':
            return self._rank_idx(str(doc.get('key') or '')) >= self.CHALLENGE_FROM_IDX
        if t == 'achievement':
            key = str(doc.get('key') or '')
            rarity = (doc.get('detail') or {}).get('rarity')
            if not rarity:
                if key in self.BADGES_SINGLE:
                    rarity = self.BADGES_SINGLE[key]['rarity']
                elif key in self.BADGES_PROG:
                    rarity = (doc.get('detail') or {}).get('rarity') or 'common'
            return rarity in ('epic', 'legendary', 'mythic', 'ancient')
        if t == 'streak':
            return str(doc.get('key') or '') in ('7', '30', '90')
        return t in ('global_first', 'weekly_champion')

    async def prestige_feed(self, me_uid: int, limit: int = 5) -> dict:
        """۵ رویداد آخر عمومی (۴۸ ساعت) + واکنش‌ها — کش ۱۰ دقیقه‌ای (Spec §۶.۳)"""
        items = None
        try:
            doc = await self.settings.find_one({'_id': 'feed_cache'})
            if doc and (datetime.now().timestamp()
                        - float(doc.get('computed_at', 0))) < self.PC_CACHE_TTL_SEC:
                items = doc.get('items')
        except Exception:
            items = None
        if items is None:
            cutoff = (datetime.now() - timedelta(hours=self.FEED_WINDOW_H)).isoformat()
            docs = await self.prestige_history.find({'at': {'$gte': cutoff}}) \
                .sort('at', -1).limit(60).to_list(60)
            docs = [d for d in docs if self._feed_is_public(d)]
            uids = list({int(d.get('uid', 0) or 0) for d in docs})
            names = {}
            if uids:
                try:
                    users = await self.users.find({'user_id': {'$in': uids}},
                        {'user_id': 1, 'name': 1, 'nickname': 1, 'privacy_public': 1}).to_list(len(uids))
                    # 🏷 Identity v1 — فید اجتماعی با display_name
                    names = {d['user_id']:
                             (self.display_name_of(d) if d.get('privacy_public', True)
                              else 'یک دانشجو') for d in users}
                except Exception:
                    pass
            items = []
            for d in docs:
                uid = int(d.get('uid', 0) or 0)
                name = names.get(uid, 'دانشجو')
                eid = str(d.get('_id', '')) or \
                    f"{uid}:{d.get('at')}:{d.get('type')}:{d.get('key')}"
                reactions = d.get('reactions') or {}
                items.append({
                    'id': eid, 'type': d.get('type'), 'uid': uid,
                    'name': name, 'text': self._feed_label(d, name),
                    'at': d.get('at'),
                    'reactions': {'clap': int(reactions.get('clap', 0) or 0),
                                  'fire': int(reactions.get('fire', 0) or 0),
                                  'crown': int(reactions.get('crown', 0) or 0)},
                })
                if len(items) >= limit:
                    break
            try:
                await self.settings.update_one({'_id': 'feed_cache'},
                    {'$set': {'items': items,
                              'computed_at': datetime.now().timestamp()}},
                    upsert=True)
            except Exception:
                pass
        # my_reaction جداگانه per request (هویت واکنش‌دهنده خروجی نمی‌شود)
        my_map = {}
        ids = [it['id'] for it in items]
        if ids:
            try:
                mine = await self.feed_reactions.find(
                    {'uid': me_uid, 'event_id': {'$in': ids}}).to_list(len(ids))
                my_map = {r['event_id']: r.get('kind') for r in mine}
            except Exception:
                pass
        return {'items': [dict(it, my_reaction=my_map.get(it['id']))
                          for it in items]}

    async def feed_react(self, uid: int, event_id: str, kind: str = None) -> dict:
        """ثبت/تعویض/حذف واکنش — ضدتکرار (event_id,uid) یکتا (Spec §۶.۳)"""
        if kind not in (None, 'clap', 'fire', 'crown'):
            return {'ok': False, 'code': 'bad_kind'}
        event_id = str(event_id or '')[:120]
        if not event_id:
            return {'ok': False, 'code': 'bad_event'}
        try:
            q = {'_id': ObjectId(event_id)}
        except Exception:
            q = {'_id': event_id}
        ev = await self.prestige_history.find_one(q)
        if not ev:
            return {'ok': False, 'code': 'not_found'}
        existing = await self.feed_reactions.find_one({'event_id': event_id, 'uid': uid})
        delta = {'clap': 0, 'fire': 0, 'crown': 0}
        my = None
        now_iso = datetime.now().isoformat()
        # toggle-off: همان واکنش دوباره یا حذف صریح
        if (kind is None) or (existing and existing.get('kind') == kind):
            if existing:
                await self.feed_reactions.delete_many(
                    {'event_id': event_id, 'uid': uid})
                delta[existing.get('kind', 'clap')] -= 1
            my = None
        elif existing:
            delta[existing.get('kind', 'clap')] -= 1
            await self.feed_reactions.update_one(
                {'event_id': event_id, 'uid': uid},
                {'$set': {'kind': kind, 'at': now_iso}})
            delta[kind] += 1
            my = kind
        else:
            try:
                await self.feed_reactions.insert_one(
                    {'event_id': event_id, 'uid': uid, 'kind': kind, 'at': now_iso})
                delta[kind] += 1
                my = kind
            except Exception:
                # race: جایگزینی به‌جای درج (ایندکس یکتا)
                await self.feed_reactions.update_one(
                    {'event_id': event_id, 'uid': uid},
                    {'$set': {'kind': kind, 'at': now_iso}})
                my = kind
        incs = {f'reactions.{k}': v for k, v in delta.items() if v}
        if incs:
            try:
                await self.prestige_history.update_one(q, {'$inc': incs})
            except Exception:
                pass
        try:
            # شمارنده‌ها بلافاصله تازه شوند — کش فید ۱۰دقیقه‌ای باطل می‌شود
            await self.settings.delete_many({'_id': 'feed_cache'})
        except Exception:
            pass
        ev2 = await self.prestige_history.find_one(q) or ev
        react = ev2.get('reactions') or {}
        return {'ok': True, 'my_reaction': my,
                'reactions': {'clap': int(react.get('clap', 0) or 0),
                              'fire': int(react.get('fire', 0) or 0),
                              'crown': int(react.get('crown', 0) or 0)}}

    # ───────── Hero Card عمومی (Spec §۶.۲) ─────────

    async def prestige_public(self, target_uid: int) -> dict:
        """کارت عمومی رنک — بدون آمار حساس؛ احترام کامل به privacy"""
        raw = await self.users.find_one(
            {'user_id': int(target_uid), 'approved': True})
        if not raw:
            return {'ok': False, 'code': 'not_found'}
        u = self._puser(raw)
        if not u.get('privacy_public', True):
            return {'ok': True, 'limited': True}
        eff = max(u['prestige_xp'] - u['decay_penalty'], u['rank_floor_xp'])
        idx, div = self._rank_for(eff)
        floor_idx, _ = self._rank_for(u['rank_floor_xp'])
        cap = max(self.CHALLENGE_FROM_IDX - 1, floor_idx)
        if idx > cap:
            idx, div = cap, 1
        r = self.PRESTIGE_RANKS[idx]
        today = self._tehran_today()
        total_active = await self._pc_total_active()
        rank_number = None
        top_pct = None
        if total_active:
            try:
                better = await self.users.count_documents({
                    'approved': True,
                    'last_active_day': {'$gte': (datetime.fromisoformat(today)
                                                 - timedelta(days=self.ACTIVE_WINDOW_DAYS))
                                        .date().isoformat()},
                    'effective_xp': {'$gt': eff},
                })
                rank_number = better + 1
                top_pct = max(1, (rank_number * 100 + total_active - 1) // total_active)
            except Exception:
                pass
        bot_username = os.getenv('BOT_USERNAME', '')
        share_link = (f"https://t.me/{bot_username}?startapp=rank_{target_uid}"
                      if bot_username else '')
        # QR سبک سروری (SVG) — اگر پکیج/لینک نبود، FE بلوک را پنهان می‌کند
        qr_svg = ''
        if share_link:
            try:
                import io as _io
                import qrcode as _qr
                import qrcode.image.svg as _qrs
                _img = _qr.make(share_link,
                                image_factory=_qrs.SvgPathImage,
                                box_size=10, border=1)
                _buf = _io.BytesIO()
                _img.save(_buf)
                qr_svg = _buf.getvalue().decode('utf-8', 'ignore')
            except Exception:
                qr_svg = ''
        rec = u.get('records') or {}
        top_idx = self._rank_idx(rec.get('top_rank_key') or 'rookie')
        return {
            'ok': True, 'limited': False,
            'name': raw.get('name') or 'کاربر',
            'icon': r[2], 'title': r[1], 'color': r[4], 'gradient': r[5],
            'div': div, 'roman': self.ROMAN[div], 'stars': self.DIV_STARS[div],
            'rank_number': rank_number, 'top_pct': top_pct,
            'streak': {'current': u['streak_current'], 'best': u['streak_best']},
            'records': {
                'best_acc': rec.get('best_acc', 0),
                'best_exam_pct': rec.get('best_exam_pct', 0),
                'top_rank_icon': self.PRESTIGE_RANKS[top_idx][2],
                'top_rank_title': self.PRESTIGE_RANKS[top_idx][1],
            },
            'showcase': self._showcase_meta(u),
            'share_link': share_link, 'qr_svg': qr_svg,
            'uid': int(target_uid),
        }

    # ───────── بستن هفته (Spec §۶.۱ — جاب) ─────────

    async def prestige_weekly_close(self) -> dict:
        """جاب پایان هفته: snapshot چینش + قهرمان هفته (+۱۰۰/نشان/رکوردها)"""
        today = self._tehran_today()
        iso_now = f"{today[:4]}-W{datetime.fromisoformat(today).isocalendar().week:02d}"
        done_key = f"weekly_closed:{iso_now}"
        if await self.get_setting(done_key, False):
            return {'skipped': True, 'week': iso_now}
        docs = await self.users.find({'approved': True, 'weekly_xp': {'$gt': 0}}) \
            .to_list(100000)
        docs.sort(key=lambda d: (-int(d.get('weekly_xp', 0) or 0),
                                 -int(d.get('streak_current', 0) or 0),
                                 str(d.get('last_gain_at') or '9999'),
                                 str(d.get('registered_at') or '9999')))
        positions = {str(int(d.get('user_id', 0) or 0)): i + 1
                     for i, d in enumerate(docs)}
        try:
            prev = await self.settings.find_one({'_id': 'lb_snapshot_week'})
            await self.settings.update_one(
                {'_id': 'lb_snapshot_prev'},
                {'$set': prev or {}}, upsert=True)
            await self.settings.update_one(
                {'_id': 'lb_snapshot_week'},
                {'$set': {'week': iso_now, 'positions': positions,
                          'at': datetime.now().isoformat()}},
                upsert=True)
        except Exception:
            pass
        champion = None
        if docs:
            champ = docs[0]
            cuid = int(champ.get('user_id', 0) or 0)
            await self.prestige_event(cuid, 'weekly_champion', {'week': iso_now})
            champion = {'uid': cuid, 'name': champ.get('name') or 'کاربر',
                        'weekly_xp': int(champ.get('weekly_xp', 0) or 0)}
        # ریست زنجیره‌ی صدر برای همه‌ی غیرقهرمان‌ها (idempotent با خود جاب)
        for d in docs:
            uid_x = int(d.get('user_id', 0) or 0)
            if champion and uid_x == champion['uid']:
                continue
            if int((d.get('records') or {}).get('top1_weeks_current', 0) or 0) > 0:
                try:
                    await self.users.update_one({'user_id': uid_x},
                        {'$set': {'records.top1_weeks_current': 0}})
                except Exception:
                    pass
        try:
            await self.set_setting(done_key, True)
        except Exception:
            pass
        return {'skipped': False, 'week': iso_now,
                'rows': len(docs), 'champion': champion}

    async def prestige_weekly_close_state(self) -> dict:
        """وضعیت آخرین بستن هفته — برای نمای مدیریتی/کارت لیدربرد"""
        doc = None
        try:
            doc = await self.settings.find_one({'_id': 'lb_snapshot_week'})
        except Exception:
            pass
        return doc or {}

    async def get_lessons(self, term: str = None):
        """
        دروس بانک سوال از bs_lessons (پنل محتوا) — سینک کامل.
        FIX جدید: پارامتر term اختیاری — برای دسته‌بندی ترم به ترم
        در بانک سوال (مثل بخش منابع علوم پایه)، نه نمایش تخت همه‌چی.
        """
        q = {'term': term} if term else {}
        lessons = await self.bs_lessons.find(q).sort([('term', 1), ('order', 1)]).to_list(500)
        seen, names = set(), []
        for l in lessons:
            n = l.get('name', '').strip()
            if n and n not in seen:
                seen.add(n); names.append(n)
        return names

    async def get_topics(self, lesson: str = None):
        """مباحث بانک سوال از bs_sessions همان درس"""
        if not lesson:
            sessions = await self.bs_sessions.find({}).to_list(2000)
        else:
            lesson_doc = await self.bs_lessons.find_one({'name': lesson})
            if not lesson_doc:
                return []
            sessions = await self.bs_sessions.find(
                {'lesson_id': str(lesson_doc['_id'])}
            ).sort('number', 1).to_list(500)
        seen, topics = set(), []
        for s in sessions:
            t = s.get('topic', '').strip()
            if t and t not in seen:
                seen.add(t); topics.append(t)
        return topics

    # ══════════════════════════════════════════════════
    #  برنامه
    # ══════════════════════════════════════════════════

    async def add_schedule(self, stype: str, lesson: str, teacher: str,
                           date: str, time: str, location: str,
                           notes: str = '', group: str = 'هر دو', is_weekly: bool = False,
                           flex_type: str = 'fixed', flex_note: str = ''):
        """
        FIX جدید: flex_type — 'fixed' (ثابت) یا 'flexible' (منعطف).
        برای کلاس منعطف، flex_note آخرین زمان اعلام‌شده را نگه می‌دارد.
        """
        r = await self.schedules.insert_one({
            'type': stype, 'lesson': lesson, 'teacher': teacher,
            'date': date, 'time': time, 'location': location,
            'notes': notes, 'group': group, 'is_weekly': is_weekly,
            'flex_type': flex_type, 'flex_note': flex_note,
            'created_at': datetime.now().isoformat(), 'notified_days': [],
        })
        return r.inserted_id

    async def update_schedule_time(self, sid: str, new_date: str, new_time: str, note: str = ''):
        """
        FIX جدید: تغییر زمان یک کلاس منعطف — برای اعلام به‌روز شدن زمان
        برگزاری به دانشجویان استفاده می‌شود.
        """
        try:
            await self.schedules.update_one(
                {'_id': ObjectId(sid)},
                {'$set': {'date': new_date, 'time': new_time, 'flex_note': note,
                          'last_time_change': datetime.now().isoformat()}}
            )
            return True
        except Exception:
            return False

    async def get_schedule_by_id(self, sid: str):
        """
        FIX جدید (بخش اول — ویرایش برنامه): گرفتن یک برنامه با ID،
        برای نمایش اطلاعات فعلی قبل از ویرایش.
        """
        try:
            return await self.schedules.find_one({'_id': ObjectId(sid)})
        except Exception:
            return None

    async def update_schedule_field(self, sid: str, field: str, value) -> bool:
        """
        FIX جدید (بخش اول — ویرایش برنامه): ویرایش یک فیلد مشخص از یک
        برنامه‌ی موجود. حتماً از UPDATE استفاده می‌شود، نه INSERT —
        رکورد جدیدی ساخته نمی‌شود و ID برنامه ثابت می‌ماند.
        """
        allowed_fields = {'date', 'time', 'location', 'teacher', 'lesson', 'notes', 'group'}
        if field not in allowed_fields:
            return False
        try:
            result = await self.schedules.update_one(
                {'_id': ObjectId(sid)},
                {'$set': {field: value, 'last_edited_at': datetime.now().isoformat()}}
            )
            return result.matched_count > 0
        except Exception:
            logger.exception('update_schedule_field failed')
            return False

    async def update_schedule_full(self, sid: str, lesson: str, teacher: str,
                                    date: str, time: str, location: str,
                                    notes: str = '', group: str = 'هر دو',
                                    flex_type: str = 'fixed', flex_note: str = '') -> bool:
        """
        FIX جدید (بخش اول — ویرایش برنامه): ویرایش کامل همه فیلدهای یک
        برنامه‌ی موجود با یک UPDATE واحد. رکورد جدید ساخته نمی‌شود و
        ID برنامه دست‌نخورده باقی می‌ماند.
        """
        try:
            result = await self.schedules.update_one(
                {'_id': ObjectId(sid)},
                {'$set': {
                    'lesson': lesson, 'teacher': teacher, 'date': date, 'time': time,
                    'location': location, 'notes': notes, 'group': group,
                    'flex_type': flex_type, 'flex_note': flex_note,
                    'last_edited_at': datetime.now().isoformat(),
                }}
            )
            return result.matched_count > 0
        except Exception:
            logger.exception('update_schedule_full failed')
            return False

    async def get_schedules(self, stype: str = None, upcoming: bool = True, group: str = None):
        from utils import now_tehran
        q = {}
        if stype:    q['type'] = stype
        if upcoming: q['date'] = {'$gte': now_tehran().strftime('%Y-%m-%d')}
        if group:
            q['$or'] = [
                {'group': group},
                {'group': 'هر دو'},
                {'group': ''},
                {'group': None},
                {'group': {'$exists': False}},
            ]
        return await self.schedules.find(q).sort('date', 1).to_list(200)

    async def delete_schedule(self, sid: str):
        try:
            await self.schedules.delete_one({'_id': ObjectId(sid)})
        except Exception: pass

    async def upcoming_exams(self, days: int = 7, group: str = None):
        """Return near exams, optionally limited to a student's group.

        Empty/missing and ``هر دو`` group values are shared schedule entries and
        must remain visible to every student. ``group`` is optional so existing
        bot/admin callers keep their previous all-groups behaviour.
        """
        from utils import now_tehran
        today = now_tehran().strftime('%Y-%m-%d')
        future = (now_tehran() + timedelta(days=max(0, days))).strftime('%Y-%m-%d')
        query = {
            'type': 'exam',
            'date': {'$gte': today, '$lte': future},
        }
        normalized_group = str(group or '').strip()
        if normalized_group:
            query['$or'] = [
                {'group': normalized_group},
                {'group': 'هر دو'},
                {'group': ''},
                {'group': None},
                {'group': {'$exists': False}},
            ]
        return await self.schedules.find(query).sort('date', 1).to_list(20)

    async def get_exams_for_reminder(self, remind_days: int):
        target = (datetime.now() + timedelta(days=remind_days)).strftime('%Y-%m-%d')
        key    = f'd{remind_days}'
        return await self.schedules.find({
            'type': 'exam', 'date': target, 'notified_days': {'$ne': key},
        }).to_list(50)

    async def mark_exam_notified(self, sid: str, remind_days: int):
        key = f'd{remind_days}'
        try:
            await self.schedules.update_one(
                {'_id': ObjectId(sid)}, {'$addToSet': {'notified_days': key}}
            )
        except Exception: pass

    # ══════════════════════════════════════════════════
    #  FAQ
    # ══════════════════════════════════════════════════

    async def faq_get_all(self):
        return await self.faq.find({}).sort('order', 1).to_list(100)

    async def faq_add(self, question: str, answer: str, category: str = 'عمومی'):
        count = await self.faq.count_documents({})
        await self.faq.insert_one({
            'question': question, 'answer': answer, 'category': category,
            'order': count, 'created_at': datetime.now().isoformat(),
        })

    async def faq_delete(self, fid: str):
        try:
            await self.faq.delete_one({'_id': ObjectId(fid)})
        except Exception: pass

    async def seed_subscription_copyright_faqs(self):
        """
        FIX مهم: faq.py._get_faq_data فقط وقتی دیتابیس FAQ کاملاً
        خالیه از DEFAULT_FAQS (فallback کد) استفاده می‌کند؛ به محض
        این‌که دیتابیس حتی یک سؤال داشته باشد، فقط همان چیزی که در
        دیتابیس است نمایش داده می‌شود و بقیه‌ی دسته‌ها (که فقط در کد
        بودند) کلاً از دید کاربر محو می‌شوند.
        قبلاً این تابع فقط دو دسته‌ی جدید («خرید اشتراک»،
        «قوانین و کپی‌رایت») را درج می‌کرد — که همین باعث شد بقیه‌ی
        دسته‌ها (علوم پایه، رفرنس، بانک سوال، برنامه، پروفایل، تیکت،
        مشکلات فنی) روی نصب واقعی ناپدید شوند. حالا همه‌ی دسته‌های
        DEFAULT_FAQS را sync می‌کند (upsert-by-question، سؤالات
        دستیِ ادمین در دسته‌های دیگر دست‌نخورده می‌مانند).
        """
        from faq import DEFAULT_FAQS
        for cat, items in DEFAULT_FAQS.items():
            for question, answer in items:
                existing = await self.faq.find_one({'question': question})
                if existing:
                    await self.faq.update_one(
                        {'_id': existing['_id']}, {'$set': {'answer': answer, 'category': cat}}
                    )
                else:
                    await self.faq_add(question, answer, cat)
        logger.info("❓ همه‌ی سؤالات پیش‌فرض FAQ همگام‌سازی شدند")

    async def faq_get_categories(self):
        return await self.faq.distinct('category') or []

    # ══════════════════════════════════════════════════
    #  تیکت‌ها
    # ══════════════════════════════════════════════════

    async def ticket_create(self, uid: int, name: str, subject: str, message: str) -> int:
        count = await self.tickets.count_documents({})
        tid   = count + 1
        await self.tickets.insert_one({
            'ticket_id': tid, 'user_id': uid, 'user_name': name,
            'subject': subject, 'message': message, 'status': 'open',
            'created_at': datetime.now().isoformat(), 'replies': [],
        })
        return tid

    async def ticket_get(self, ticket_id: int):
        return await self.tickets.find_one({'ticket_id': ticket_id})

    async def ticket_get_all(self, status: str = None):
        q = {'status': status} if status else {}
        return await self.tickets.find(q).sort('created_at', -1).to_list(100)

    async def ticket_list_for_user(self, uid: int, limit: int = 10) -> list:
        """⚠️ قابلیتِ جدید: تیکت‌های خودِ همین کاربر — برای get_my_tickets."""
        return await self.tickets.find({'user_id': uid}).sort('created_at', -1).to_list(limit)

    async def ticket_get_user(self, uid: int):
        return await self.tickets.find({'user_id': uid}).sort('created_at', -1).to_list(20)

    async def ticket_add_reply(self, ticket_id: int, reply_text: str):
        await self.tickets.update_one(
            {'ticket_id': ticket_id},
            {
                '$push': {'replies': {'text': reply_text, 'at': datetime.now().isoformat()}},
                '$set':  {'last_reply_at': datetime.now().isoformat()},
            }
        )

    async def ticket_reply(self, ticket_id: int, reply: str):
        await self.ticket_add_reply(ticket_id, reply)

    async def ticket_close(self, ticket_id: int):
        await self.tickets.update_one(
            {'ticket_id': ticket_id},
            {'$set': {'status': 'closed', 'closed_at': datetime.now().isoformat()}}
        )

    async def ticket_reopen(self, ticket_id: int):
        """
        FIX جدید طبق سند: بازگشایی تیکت — قبلاً این قابلیت اصلاً
        وجود نداشت و دانشجو مجبور بود تیکت جدید بسازد.
        """
        await self.tickets.update_one(
            {'ticket_id': ticket_id},
            {'$set': {'status': 'open'}, '$unset': {'closed_at': ''}}
        )

    # ══════════════════════════════════════════════════
    #  آمار
    # ══════════════════════════════════════════════════

    async def log(self, uid: int, action: str, data: dict = None):
        await self.stats_col.insert_one({
            'user_id': uid, 'action': action,
            'data': data or {}, 'timestamp': datetime.now().isoformat(),
        })

    async def user_stats(self, uid: int) -> dict:
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        week_act, downloads, user = await asyncio.gather(
            self.stats_col.count_documents({'user_id': uid, 'timestamp': {'$gt': week_ago}}),
            self.stats_col.count_documents({
                'user_id': uid,
                'action': {'$in': ['bs_download', 'ref_download', 'qbank_download']},
            }),
            self.get_user(uid),
        )
        total   = user.get('total_answers', 0)   if user else 0
        correct = user.get('correct_answers', 0) if user else 0
        pct     = round(correct / total * 100, 1) if total > 0 else 0
        return {
            'downloads': downloads, 'total_answers': total,
            'correct_answers': correct, 'percentage': pct,
            'week_activity': week_act,
            'weak_topics': user.get('weak_topics', []) if user else [],
        }

    async def weekly_activity(self, uid: int) -> list:
        result = []
        for i in range(6, -1, -1):
            day   = datetime.now() - timedelta(days=i)
            start = day.replace(hour=0,  minute=0,  second=0,  microsecond=0).isoformat()
            end   = day.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
            count = await self.stats_col.count_documents({
                'user_id': uid, 'timestamp': {'$gte': start, '$lte': end},
            })
            result.append((day.strftime('%m/%d'), count))
        return result

    async def global_stats(self) -> dict:
        week_ago  = (datetime.now() - timedelta(days=7)).isoformat()
        new_users = await self.users.count_documents({'registered_at': {'$gt': week_ago}})
        # FIX جدید: online_30m و total_downloads هم اینجا اضافه شد تا
        # نمای کلی سریع پنل ادمین (admin:stats) بدون فراخوانی جداگانه
        # این دو متریک تعامل/سلامت را هم در یک نگاه نشان دهد.
        dl_pipeline = [{'$group': {'_id': None, 'total': {'$sum': '$downloads'}}}]
        vals = await asyncio.gather(
            self.users.count_documents({'approved': True}),
            self.users.count_documents({'approved': False}),
            self.questions.count_documents({'approved': True}),
            self.qbank_files.count_documents({}),
            self.bs_lessons.count_documents({}),
            self.bs_sessions.count_documents({}),
            self.bs_content.count_documents({}),
            self.ref_subjects.count_documents({}),
            self.ref_books.count_documents({}),
            self.tickets.count_documents({'status': 'open'}),
            self.users.count_documents({'role': 'content_admin'}),
            self.count_active_users(30),
            self.bs_content.aggregate(dl_pipeline).to_list(1),
            self.ref_files.aggregate(dl_pipeline).to_list(1),
        )
        keys = [
            'users','pending','questions','qbank_files',
            'bs_lessons','bs_sessions','bs_content',
            'ref_subjects','ref_books','open_tickets','content_admins',
            'online_30m',
        ]
        d = dict(zip(keys, vals[:len(keys)]))
        bs_dl, ref_dl = vals[len(keys)], vals[len(keys) + 1]
        d['total_downloads'] = (
            (bs_dl[0]['total']  if bs_dl  else 0) +
            (ref_dl[0]['total'] if ref_dl else 0)
        )
        d['new_users_week'] = new_users
        return d

    async def content_admin_stats(self, intake=None) -> dict:
        """آمار پنل محتوا. پیش‌فرض intake=None ⇒ رفتار قدیمی (کل سیستم).
        🌊 C1 — با intake مشخص (از جمله '' = سراسری): فقط لنگرهای همان
        scope شمرده می‌شوند؛ فرزندان از طریق شناسه‌ی والد join می‌شوند."""
        if intake is not None:
            return await self._content_admin_stats_scoped(intake)
        keys_content = [
            ('bs_lessons',   self.bs_lessons,   {}),
            ('bs_sessions',  self.bs_sessions,  {}),
            ('bs_total',     self.bs_content,   {}),
            ('bs_video',     self.bs_content,   {'type': 'video'}),
            ('bs_pdf',       self.bs_content,   {'type': 'pdf'}),
            ('bs_ppt',       self.bs_content,   {'type': 'ppt'}),
            ('bs_voice',     self.bs_content,   {'type': 'voice'}),
            ('bs_note',      self.bs_content,   {'type': 'note'}),
            ('bs_test',      self.bs_content,   {'type': 'test'}),
            ('ref_subjects', self.ref_subjects, {}),
            ('ref_books',    self.ref_books,    {}),
            ('ref_files',    self.ref_files,    {}),
            ('ref_fa',       self.ref_files,    {'lang': 'fa'}),
            ('ref_en',       self.ref_files,    {'lang': 'en'}),
            ('q_total',      self.questions,    {'approved': True}),
            ('q_pending',    self.questions,    {'approved': False}),
            ('q_by_bot',     self.questions,    {'approved': True, 'by_bot': True}),
            ('q_by_users',   self.questions,    {'approved': True, 'by_bot': {'$ne': True}}),
            ('users_count',  self.users,        {'approved': True}),
        ]
        counts = await asyncio.gather(*[col.count_documents(q) for _, col, q in keys_content])
        result = {k: v for (k, col, q), v in zip(keys_content, counts)}
        pipeline = [{'$group': {'_id': None, 'total': {'$sum': '$downloads'}}}]
        r_bs, r_ref = await asyncio.gather(
            self.bs_content.aggregate(pipeline).to_list(1),
            self.ref_files.aggregate(pipeline).to_list(1),
        )
        result['total_downloads'] = (
            (r_bs[0]['total']  if r_bs  else 0) +
            (r_ref[0]['total'] if r_ref else 0)
        )
        return result

    async def _content_admin_stats_scoped(self, intake: str) -> dict:
        """🌊 C1 — همان ساختار content_admin_stats ولی محدود به یک scope."""
        intake = intake or ''
        lessons = await self.bs_lessons.find({'intake': intake}).to_list(500)
        lids = [str(l['_id']) for l in lessons]
        sessions = await self.bs_sessions.find(
            {'lesson_id': {'$in': lids}}).to_list(2000) if lids else []
        sids = [str(s['_id']) for s in sessions]
        cq = {'session_id': {'$in': sids}} if sids else {'session_id': '__none__'}

        subjects = await self.ref_subjects.find({'intake': intake}).to_list(500)
        sub_ids = [str(s['_id']) for s in subjects]
        books = await self.ref_books.find(
            {'subject_id': {'$in': sub_ids}}).to_list(2000) if sub_ids else []
        bids = [str(b['_id']) for b in books]
        fq = {'book_id': {'$in': bids}} if bids else {'book_id': '__none__'}

        keys = [
            ('bs_lessons',   self.bs_lessons,   {'intake': intake}),
            ('bs_sessions',  self.bs_sessions,  {'lesson_id': {'$in': lids} if lids else {'$in': []}}),
            ('bs_total',     self.bs_content,   cq),
            ('bs_video',     self.bs_content,   dict(cq, type='video')),
            ('bs_pdf',       self.bs_content,   dict(cq, type='pdf')),
            ('bs_ppt',       self.bs_content,   dict(cq, type='ppt')),
            ('bs_voice',     self.bs_content,   dict(cq, type='voice')),
            ('bs_note',      self.bs_content,   dict(cq, type='note')),
            ('bs_test',      self.bs_content,   dict(cq, type='test')),
            ('ref_subjects', self.ref_subjects, {'intake': intake}),
            ('ref_books',    self.ref_books,    {'subject_id': {'$in': sub_ids} if sub_ids else {'$in': []}}),
            ('ref_files',    self.ref_files,    fq),
            ('ref_fa',       self.ref_files,    dict(fq, lang='fa')),
            ('ref_en',       self.ref_files,    dict(fq, lang='en')),
            ('q_total',      self.questions,    {'approved': True, 'intake': intake}),
            ('q_pending',    self.questions,    {'approved': False, 'intake': intake}),
            ('q_by_bot',     self.questions,    {'approved': True, 'by_bot': True, 'intake': intake}),
            ('q_by_users',   self.questions,    {'approved': True, 'by_bot': {'$ne': True}, 'intake': intake}),
            ('users_count',  self.users,        {'approved': True, 'intake': intake} if intake else {'approved': True}),
        ]
        counts = await asyncio.gather(*[col.count_documents(q) for _, col, q in keys])
        result = {k: v for (k, col, q), v in zip(keys, counts)}
        pipeline_bs = [{'$match': cq},
                       {'$group': {'_id': None, 'total': {'$sum': '$downloads'}}}]
        pipeline_rf = [{'$match': fq},
                       {'$group': {'_id': None, 'total': {'$sum': '$downloads'}}}]
        r_bs, r_ref = await asyncio.gather(
            self.bs_content.aggregate(pipeline_bs).to_list(1),
            self.ref_files.aggregate(pipeline_rf).to_list(1),
        )
        result['total_downloads'] = (
            (r_bs[0]['total']  if r_bs  else 0) +
            (r_ref[0]['total'] if r_ref else 0)
        )
        return result

    # ══════════════════════════════════════════════════
    #  FIX جدید: داشبورد آماری پیشرفته پنل ادمین — پوشش کامل‌تر
    #  کل ربات (کاربران/محتوا/سوالات/تیکت‌ها/اعلان‌ها) با جزئیات
    #  بیشتر از global_stats ساده‌ی قبلی.
    # ══════════════════════════════════════════════════

    async def stats_dashboard_users(self) -> dict:
        """آمار جزئی کاربران: رشد، فعالیت، گروه/ورودی، نقش‌های فرعی"""
        from utils import today_start_utc_str
        now          = datetime.now()
        today_start  = today_start_utc_str()
        week_ago     = (now - timedelta(days=7)).isoformat()
        month_ago    = (now - timedelta(days=30)).isoformat()

        (total_approved, total_pending, new_today, new_week, new_month,
         g1, g2, active_today, active_week, blocked_bot, content_admins,
         all_approved_users, all_intakes, all_roles) = await asyncio.gather(
            self.users.count_documents({'approved': True}),
            self.users.count_documents({'approved': False}),
            self.users.count_documents({'registered_at': {'$gte': today_start}}),
            self.users.count_documents({'registered_at': {'$gte': week_ago}}),
            self.users.count_documents({'registered_at': {'$gte': month_ago}}),
            self.users.count_documents({'approved': True, 'group': '1'}),
            self.users.count_documents({'approved': True, 'group': '2'}),
            self.users.count_documents({'last_active': {'$gte': today_start}}),
            self.users.count_documents({'last_active': {'$gte': week_ago}}),
            self.users.count_documents({'blocked_bot': True}),
            self.users.count_documents({'role': 'content_admin'}),
            self.users.find({'approved': True}).to_list(length=None),
            self.get_all_intakes(),
            self.get_all_admin_roles(),
        )

        inactive_14 = (now - timedelta(days=14)).isoformat()
        inactive_30 = (now - timedelta(days=30)).isoformat()
        inactive_14d = sum(
            1 for u in all_approved_users
            if not u.get('last_active') or u['last_active'] < inactive_14
        )
        inactive_30d = sum(
            1 for u in all_approved_users
            if not u.get('last_active') or u['last_active'] < inactive_30
        )

        # روند رشد ثبت‌نام ۷ روز اخیر
        growth_7d = []
        for i in range(6, -1, -1):
            day = now - timedelta(days=i)
            d0  = day.strftime('%Y-%m-%dT00:00:00')
            d1  = day.strftime('%Y-%m-%dT23:59:59')
            cnt = sum(1 for u in all_approved_users if d0 <= (u.get('registered_at') or '') <= d1)
            growth_7d.append((day.strftime('%m/%d'), cnt))

        # تفکیک بر اساس ورودی
        intake_label = {i['code']: i['label'] for i in all_intakes}
        intake_counts: dict = {}
        for u in all_approved_users:
            key = u.get('intake') or ''
            intake_counts[key] = intake_counts.get(key, 0) + 1
        by_intake = sorted(
            [(intake_label.get(code, code) if code else 'بدون ورودی', cnt)
             for code, cnt in intake_counts.items()],
            key=lambda x: -x[1]
        )

        role_counts: dict = {}
        for r in all_roles:
            role_counts[r.get('role', '')] = role_counts.get(r.get('role', ''), 0) + 1

        # FIX جدید: ۳ کاربر برتر (بر اساس جدول برترین‌های dashboard.py)
        # هم اینجا نمایش داده می‌شود تا ادمین فعال‌ترین کاربران را هم
        # در کنار آمار رشد/فعالیت ببیند.
        top_users = await self.get_leaderboard(3)

        return {
            'total_approved': total_approved, 'total_pending': total_pending,
            'new_today': new_today, 'new_week': new_week, 'new_month': new_month,
            'group1': g1, 'group2': g2,
            'group_unset': max(total_approved - g1 - g2, 0),
            'active_today': active_today, 'active_week': active_week,
            'inactive_14d': inactive_14d, 'inactive_30d': inactive_30d,
            'blocked_bot': blocked_bot, 'content_admins': content_admins,
            'growth_7d': growth_7d, 'by_intake': by_intake,
            'sub_admin_roles': role_counts, 'top_users': top_users,
        }

    async def stats_dashboard_content(self) -> dict:
        """آمار جزئی محتوا: علوم پایه به‌تفکیک نوع، رفرنس به‌تفکیک زبان، دانلودها"""
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        (bs_lessons, bs_sessions, bs_by_type, ref_subjects, ref_books,
         ref_by_lang, faq_count, qbank_files, top_qbank_lessons,
         bs_dl_agg, ref_dl_agg, qbank_dl_agg, top_downloaded_qbank,
         new_bs_week, new_ref_week) = await asyncio.gather(
            self.bs_lessons.count_documents({}),
            self.bs_sessions.count_documents({}),
            self.bs_content.aggregate(
                [{'$group': {'_id': '$type', 'count': {'$sum': 1}}}]
            ).to_list(20),
            self.ref_subjects.count_documents({}),
            self.ref_books.count_documents({}),
            self.ref_files.aggregate(
                [{'$group': {'_id': '$lang', 'count': {'$sum': 1}}}]
            ).to_list(10),
            self.faq.count_documents({}),
            self.qbank_files.count_documents({}),
            self.qbank_files.aggregate([
                {'$group': {'_id': '$lesson', 'count': {'$sum': 1}}},
                {'$sort': {'count': -1}}, {'$limit': 5},
            ]).to_list(5),
            self.bs_content.aggregate(
                [{'$group': {'_id': None, 'total': {'$sum': '$downloads'}}}]
            ).to_list(1),
            self.ref_files.aggregate(
                [{'$group': {'_id': None, 'total': {'$sum': '$downloads'}}}]
            ).to_list(1),
            self.qbank_files.aggregate(
                [{'$group': {'_id': None, 'total': {'$sum': '$downloads'}}}]
            ).to_list(1),
            self.qbank_files.find(
                {'downloads': {'$gt': 0}}, {'lesson': 1, 'topic': 1, 'downloads': 1}
            ).sort('downloads', -1).limit(5).to_list(5),
            self.bs_content.count_documents({'uploaded_at': {'$gt': week_ago}}),
            self.ref_files.count_documents({'uploaded_at': {'$gt': week_ago}}),
        )
        type_labels = {
            'video': '🎥 ویدیو', 'ppt': '📊 پاورپوینت', 'pdf': '📄 PDF',
            'note': '📝 نکات', 'test': '🧪 تست', 'voice': '🎙 ویس',
        }
        bs_types = {type_labels.get(d['_id'], d['_id'] or 'نامشخص'): d['count'] for d in bs_by_type}
        lang_labels = {'fa': '🇮🇷 فارسی', 'en': '🌍 انگلیسی'}
        ref_langs = {lang_labels.get(d['_id'], d['_id'] or 'نامشخص'): d['count'] for d in ref_by_lang}

        return {
            'bs_lessons': bs_lessons, 'bs_sessions': bs_sessions,
            'bs_types': bs_types, 'bs_total_content': sum(bs_types.values()),
            'ref_subjects': ref_subjects, 'ref_books': ref_books,
            'ref_langs': ref_langs, 'ref_total_files': sum(ref_langs.values()),
            'faq_count': faq_count, 'qbank_files': qbank_files,
            'top_qbank_lessons': [(d['_id'] or 'نامشخص', d['count']) for d in top_qbank_lessons],
            'top_downloaded_qbank': [
                (f"{d.get('lesson','نامشخص')} / {d.get('topic','')}".strip(' /'), d.get('downloads', 0))
                for d in top_downloaded_qbank
            ],
            'bs_downloads': (bs_dl_agg[0]['total'] if bs_dl_agg else 0),
            'ref_downloads': (ref_dl_agg[0]['total'] if ref_dl_agg else 0),
            'qbank_downloads': (qbank_dl_agg[0]['total'] if qbank_dl_agg else 0),
            'new_this_week': new_bs_week + new_ref_week,
        }

    async def stats_dashboard_questions(self) -> dict:
        """آمار جزئی بانک سوال: دقت پاسخ‌دهی، پرسوال‌ترین درس‌ها، سخت‌ترین سوالات"""
        (q_approved, q_pending, q_by_bot, q_by_users, by_diff, by_lesson, totals, hardest) = await asyncio.gather(
            self.questions.count_documents({'approved': True}),
            self.questions.count_documents({'approved': False}),
            self.questions.count_documents({'approved': True, 'by_bot': True}),
            self.questions.count_documents({'approved': True, 'by_bot': {'$ne': True}}),
            self.questions.aggregate([
                {'$match': {'approved': True}},
                {'$group': {'_id': '$difficulty', 'count': {'$sum': 1}}},
            ]).to_list(10),
            self.questions.aggregate([
                {'$match': {'approved': True}},
                {'$group': {'_id': '$lesson', 'count': {'$sum': 1}}},
                {'$sort': {'count': -1}}, {'$limit': 5},
            ]).to_list(5),
            self.questions.aggregate([
                {'$match': {'approved': True}},
                {'$group': {'_id': None,
                            'attempts': {'$sum': '$attempt_count'},
                            'correct':  {'$sum': '$correct_count'}}},
            ]).to_list(1),
            self.questions.aggregate([
                {'$match': {'approved': True, 'attempt_count': {'$gte': 5}}},
                {'$project': {
                    'lesson': 1, 'topic': 1, 'question': 1,
                    'attempt_count': 1, 'correct_count': 1,
                    'wrong_rate': {'$divide': [
                        {'$subtract': ['$attempt_count', '$correct_count']},
                        '$attempt_count',
                    ]},
                }},
                {'$sort': {'wrong_rate': -1}}, {'$limit': 5},
            ]).to_list(5),
        )
        diff_labels = {'easy': '🟢 آسان', 'medium': '🟡 متوسط', 'hard': '🔴 سخت'}
        by_difficulty = {diff_labels.get(d['_id'], d['_id'] or 'نامشخص'): d['count'] for d in by_diff}
        total_attempts = totals[0]['attempts'] if totals else 0
        total_correct  = totals[0]['correct']  if totals else 0
        accuracy = round(total_correct / total_attempts * 100, 1) if total_attempts else 0
        hardest_list = [{
            'lesson': h.get('lesson', ''), 'topic': h.get('topic', ''),
            'question': (h.get('question', '') or '')[:50],
            'wrong_rate': round(h.get('wrong_rate', 0) * 100, 1),
            'attempts': h.get('attempt_count', 0),
        } for h in hardest]

        return {
            'approved': q_approved, 'pending': q_pending,
            'by_bot': q_by_bot, 'by_users': q_by_users,
            'by_difficulty': by_difficulty,
            'top_lessons': [(d['_id'] or 'نامشخص', d['count']) for d in by_lesson],
            'total_attempts': total_attempts, 'total_correct': total_correct,
            'accuracy': accuracy, 'hardest_questions': hardest_list,
        }

    async def stats_dashboard_tickets(self) -> dict:
        """آمار جزئی پشتیبانی"""
        week_ago  = (datetime.now() - timedelta(days=7)).isoformat()
        month_ago = (datetime.now() - timedelta(days=30)).isoformat()
        (open_t, closed_t, new_week, new_month, closed_week, resolved_month) = await asyncio.gather(
            self.tickets.count_documents({'status': 'open'}),
            self.tickets.count_documents({'status': 'closed'}),
            self.tickets.count_documents({'created_at': {'$gte': week_ago}}),
            self.tickets.count_documents({'created_at': {'$gte': month_ago}}),
            self.tickets.count_documents({'status': 'closed', 'closed_at': {'$gte': week_ago}}),
            self.tickets.find({
                'status': 'closed', 'closed_at': {'$gte': month_ago},
            }, {'created_at': 1, 'closed_at': 1}).to_list(500),
        )
        # FIX جدید: میانگین زمان رسیدگی — بر مبنای تیکت‌های بسته‌شده‌ی
        # ۳۰ روز اخیر، چون created_at/closed_at رشته‌ی isoformat‌اند و
        # محاسبه در پایتون از aggregation با فرمت ناهمگون مطمئن‌تر است.
        durations_h = []
        for t in resolved_month:
            try:
                c0 = datetime.fromisoformat(t['created_at'])
                c1 = datetime.fromisoformat(t['closed_at'])
                durations_h.append((c1 - c0).total_seconds() / 3600)
            except Exception:
                continue
        avg_resolution_h = round(sum(durations_h) / len(durations_h), 1) if durations_h else None

        return {
            'open': open_t, 'closed': closed_t, 'total': open_t + closed_t,
            'new_week': new_week, 'new_month': new_month, 'closed_week': closed_week,
            'avg_resolution_h': avg_resolution_h, 'resolved_sample': len(durations_h),
        }

    async def stats_dashboard_notif(self) -> dict:
        """خلاصه سلامت اعلان‌های خودکار — بر اساس ۱۰ اجرای اخیر هر job"""
        jobs = ['exam_reminder', 'daily_question', 'new_resources']
        result = {}
        for j in jobs:
            runs = await self.notif_runs.find({'job_name': j}).sort('started_at', -1).to_list(10)
            if not runs:
                result[j] = None
                continue
            last = runs[0]
            result[j] = {
                'runs_checked':  len(runs),
                'total_sent':    sum(r.get('sent', 0) for r in runs),
                'total_failed':  sum(r.get('failed', 0) for r in runs),
                'last_status':   last.get('status', ''),
                'last_at':       (last.get('started_at') or '')[:16].replace('T', ' '),
                'last_sent':     last.get('sent', 0),
                'last_failed':   last.get('failed', 0),
            }
        return result

    async def new_resources_count(self, days: int = 7) -> int:
        since = (datetime.now() - timedelta(days=days)).isoformat()
        bs, refs = await asyncio.gather(
            self.bs_content.count_documents({'uploaded_at': {'$gt': since}}),
            self.ref_files.count_documents({'uploaded_at': {'$gt': since}}),
        )
        return bs + refs

    async def activity_pulse(self) -> dict:
        """
        FIX جدید: نبض فعالیت ربات — حجم کل کنش‌های ثبت‌شده در ۷ روز
        اخیر و پرترافیک‌ترین ساعت شبانه‌روز، برای نمای کلی داشبورد.
        timestamp به‌صورت رشته‌ی isoformat ذخیره می‌شود، پس ساعت با
        substring به‌جای پارس تاریخ کامل استخراج می‌شود (سریع‌تر و
        مطمئن‌تر روی رشته‌های با دقت میکروثانیه‌ی متغیر).
        """
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        total_week, by_hour = await asyncio.gather(
            self.stats_col.count_documents({'timestamp': {'$gt': week_ago}}),
            self.stats_col.aggregate([
                {'$match': {'timestamp': {'$gt': week_ago}}},
                {'$group': {
                    '_id': {'$substrBytes': ['$timestamp', 11, 2]},
                    'count': {'$sum': 1},
                }},
                {'$sort': {'count': -1}}, {'$limit': 1},
            ]).to_list(1),
        )
        peak_hour, peak_count = (None, 0)
        if by_hour:
            peak_hour, peak_count = by_hour[0]['_id'], by_hour[0]['count']
        return {
            'total_actions_week': total_week,
            'peak_hour': peak_hour, 'peak_hour_count': peak_count,
        }

    async def admin_insights(self) -> dict:
        """
        FIX جدید — «مرکز هوش ربات»: به‌جای اینکه ادمین خودش بین چند
        صفحه‌ی آمار بگردد تا مشکلات را پیدا کند، این متد با چند قانون
        ساده (rule-based) روی داده‌های واقعی، خودش هشدارهای قابل‌اقدام
        و پیش‌بینی رشد هفته‌ی بعد را تولید می‌کند. هیچ داده‌ای شبیه‌سازی
        نمی‌شود — همه از همان کالکشن‌های موجود محاسبه می‌شود.
        """
        now        = datetime.now()
        h48        = (now - timedelta(hours=48)).isoformat()
        d14        = (now - timedelta(days=14)).isoformat()
        d3         = (now - timedelta(days=3)).isoformat()

        (
            pending_old, oldest_pending,
            tickets_old, oldest_ticket,
            bad_questions,
            inactive_admins,
            all_sessions, content_session_ids,
        ) = await asyncio.gather(
            self.users.count_documents({'approved': False, 'registered_at': {'$lt': h48}}),
            self.users.find({'approved': False}).sort('registered_at', 1).to_list(1),
            self.tickets.count_documents({'status': 'open', 'created_at': {'$lt': h48}}),
            self.tickets.find({'status': 'open'}).sort('created_at', 1).to_list(1),
            self.questions.count_documents({
                'approved': True, 'attempt_count': {'$gte': 5},
                '$expr': {'$gte': [
                    {'$divide': [
                        {'$subtract': ['$attempt_count', '$correct_count']},
                        '$attempt_count',
                    ]}, 0.7,
                ]},
            }),
            self.users.find({
                'role': 'content_admin',
                '$or': [{'last_active': {'$lt': d14}}, {'last_active': {'$exists': False}}],
            }, {'name': 1}).to_list(20),
            self.bs_sessions.find({'created_at': {'$lt': d3}}, {'_id': 1}).to_list(500),
            self.bs_content.distinct('session_id'),
        )

        oldest_pending_h = None
        if oldest_pending:
            try:
                oldest_pending_h = round((now - datetime.fromisoformat(oldest_pending[0]['registered_at'])).total_seconds() / 3600)
            except Exception:
                pass
        oldest_ticket_h = None
        if oldest_ticket:
            try:
                oldest_ticket_h = round((now - datetime.fromisoformat(oldest_ticket[0]['created_at'])).total_seconds() / 3600)
            except Exception:
                pass

        content_session_ids = set(str(s) for s in content_session_ids)
        empty_sessions = [s for s in all_sessions if str(s['_id']) not in content_session_ids]

        # ── گزارشات محتوا/سوال بررسی‌نشده ──
        new_reports = await self.content_reports.count_documents({'status': 'new'})

        # ── فعالیت ادمین‌های فرعی پنل (بر اساس audit_logs) ──
        # FIX جدید: پرکارترین و کم‌کارترین ادمین‌های فرعی، برای این‌که
        # ادمین ارشد بفهمد کدام همکار واقعاً از پنل استفاده می‌کند و
        # کدام مدت‌هاست سراغش نرفته — بدون نیاز به گشتن دستی در لاگ خام.
        role_docs = await self.get_all_admin_roles()
        admin_uids = [r['_id'] for r in role_docs]
        top_admins, stale_admins = [], []
        if admin_uids:
            week_ago_iso = (now - timedelta(days=7)).isoformat()
            week_agg, last_agg, name_docs = await asyncio.gather(
                self.audit_logs.aggregate([
                    {'$match': {'timestamp': {'$gt': week_ago_iso}, 'actor.id': {'$in': admin_uids}}},
                    {'$group': {'_id': '$actor.id', 'count': {'$sum': 1}}},
                    {'$sort': {'count': -1}},
                ]).to_list(50),
                self.audit_logs.aggregate([
                    {'$match': {'actor.id': {'$in': admin_uids}}},
                    {'$group': {'_id': '$actor.id', 'last_action': {'$max': '$timestamp'}}},
                ]).to_list(50),
                self.users.find({'user_id': {'$in': admin_uids}}, {'user_id': 1, 'name': 1}).to_list(len(admin_uids)),
            )
            name_map = {d['user_id']: d.get('name', 'ادمین') for d in name_docs}
            role_map = {r['_id']: self.ROLE_LABELS.get(r.get('role', ''), r.get('role', '')) for r in role_docs}
            week_map = {d['_id']: d['count'] for d in week_agg}
            last_map = {d['_id']: d['last_action'] for d in last_agg}

            for uid_ in admin_uids:
                nm = name_map.get(uid_, f"ادمین #{uid_}")
                rl = role_map.get(uid_, '')
                wk = week_map.get(uid_, 0)
                last_ts = last_map.get(uid_)
                if wk > 0:
                    top_admins.append({'name': nm, 'role': rl, 'count': wk})
                if last_ts:
                    try:
                        days_idle = (now - datetime.fromisoformat(last_ts)).days
                    except Exception:
                        days_idle = None
                else:
                    days_idle = None  # هرگز فعالیتی ثبت نشده
                if days_idle is None or days_idle >= 14:
                    stale_admins.append({'name': nm, 'role': rl, 'days_idle': days_idle})
            top_admins.sort(key=lambda x: x['count'], reverse=True)
            top_admins = top_admins[:5]

        # ── روند رشد ۴ هفته‌ی اخیر + پیش‌بینی ساده‌ی هفته‌ی بعد ──
        week_counts = []
        for i in range(4):
            start = (now - timedelta(days=7 * (i + 1))).isoformat()
            end   = (now - timedelta(days=7 * i)).isoformat()
            c = await self.users.count_documents({'registered_at': {'$gte': start, '$lt': end}})
            week_counts.append(c)  # week_counts[0] = این هفته, [3] = ۴ هفته پیش
        this_week = week_counts[0]
        prior_avg = round(sum(week_counts[1:]) / 3, 1) if any(week_counts[1:]) else 0
        slope     = (week_counts[0] - week_counts[3]) / 3 if len(week_counts) == 4 else 0
        forecast_next_week = max(0, round(this_week + slope))
        growth_alert = None
        if prior_avg > 0:
            change = round((this_week - prior_avg) / prior_avg * 100)
            if change <= -30:
                growth_alert = f"📉 افت {abs(change)}٪ در ثبت‌نام این هفته نسبت به میانگین ۳ هفته‌ی قبل"
            elif change >= 50:
                growth_alert = f"📈 جهش {change}٪ در ثبت‌نام این هفته نسبت به میانگین ۳ هفته‌ی قبل"

        alerts = []
        if pending_old:
            alerts.append({
                'icon': '⏳', 'title': f"{pending_old} کاربر بیش از ۴۸ ساعت منتظر تأییدند",
                'detail': f"قدیمی‌ترین: {oldest_pending_h} ساعت پیش" if oldest_pending_h else '',
                'action': 'admin:pending',
            })
        if tickets_old:
            alerts.append({
                'icon': '🎫', 'title': f"{tickets_old} تیکت بیش از ۴۸ ساعت بدون پاسخ باز مانده",
                'detail': f"قدیمی‌ترین: {oldest_ticket_h} ساعت پیش" if oldest_ticket_h else '',
                'action': 'ticket:manage',
            })
        if bad_questions:
            alerts.append({
                'icon': '😵', 'title': f"{bad_questions} سوال نرخ خطای ۷۰٪+ دارند و نیاز به بازبینی دارند",
                'detail': 'حداقل ۵ پاسخ ثبت‌شده برای هرکدام',
                'action': 'admin:stats_questions',
            })
        if inactive_admins:
            names = "، ".join(a.get('name', 'ادمین') for a in inactive_admins[:5])
            alerts.append({
                'icon': '😴', 'title': f"{len(inactive_admins)} ادمین محتوا ۱۴+ روز غیرفعال بوده‌اند",
                'detail': names, 'action': 'admin:cat_users',
            })
        if empty_sessions:
            alerts.append({
                'icon': '📭', 'title': f"{len(empty_sessions)} جلسه‌ی علوم پایه هنوز هیچ محتوایی ندارد",
                'detail': 'حداقل ۳ روز از ساخت‌شان گذشته', 'action': 'admin:cat_content',
            })
        if new_reports:
            alerts.append({
                'icon': '📋', 'title': f"{new_reports} گزارش محتوا/سوال بررسی‌نشده در صف است",
                'detail': '', 'action': 'report:manage:all',
            })
        if stale_admins:
            names = "، ".join(
                f"{a['name']} ({a['days_idle']} روز)" if a['days_idle'] is not None else f"{a['name']} (هرگز)"
                for a in stale_admins[:5]
            )
            alerts.append({
                'icon': '🕸', 'title': f"{len(stale_admins)} ادمین فرعی پنل ۱۴+ روز از پنل استفاده نکرده‌اند",
                'detail': names, 'action': 'admin:cat_users',
            })
        if growth_alert:
            alerts.append({'icon': '📊', 'title': growth_alert, 'detail': '', 'action': 'admin:stats_users'})

        return {
            'alerts': alerts,
            'week_counts': week_counts, 'this_week': this_week, 'prior_avg': prior_avg,
            'forecast_next_week': forecast_next_week,
            'top_admins': top_admins, 'stale_admins': stale_admins,
        }


# instance جهانی
    # ══════════════════════════════════════════════════
    #  تنظیمات کلی ربات (bot_settings)
    # ══════════════════════════════════════════════════

    async def get_setting(self, key: str, default=None):
        doc = await self.settings.find_one({'_id': 'global'})
        if not doc:
            return default
        return doc.get(key, default)

    async def set_setting(self, key: str, value) -> None:
        await self.settings.update_one(
            {'_id': 'global'},
            {'$set': {key: value, 'updated_at': datetime.now().isoformat()}},
            upsert=True
        )

    async def delete_setting(self, key: str) -> None:
        try:
            await self.settings.update_one(
                {'_id': 'global'}, {'$unset': {key: ''}}
            )
        except Exception:
            pass

    async def get_settings_by_prefix(self, prefix: str) -> dict:
        """
        FIX (ارسال زماندار پایدار): برای پیدا کردن تمام کلیدهایی که با
        یک پیشوند مشخص شروع می‌شوند (مثلاً scheduled_broadcast_) —
        استفاده در بازیابی پیام‌های زماندار بعد از ری‌استارت ربات.
        """
        doc = await self.settings.find_one({'_id': 'global'})
        if not doc:
            return {}
        return {k: v for k, v in doc.items() if isinstance(k, str) and k.startswith(prefix)}

    async def get_all_settings(self) -> dict:
        doc = await self.settings.find_one({'_id': 'global'})
        return doc or {}

    async def users_missing_student_id(self) -> list:
        return await self.users.find({
            'approved': True,
            '$or': [
                {'student_id': {'$exists': False}},
                {'student_id': ''},
                {'student_id': None},
            ]
        }).to_list(1000)

    # ══════════════════════════════════════════════════
    #  سطوح دسترسی چندگانه ادمین (admin_roles)
    #  جدا از users.role (student/content_admin) — مخصوص
    #  زیرمجموعه‌های ادمین ارشد: مدیر محتوا کلی/محدود، پشتیبان
    # ══════════════════════════════════════════════════

    # نقش‌های ممکن و برچسب فارسی‌شان
    ROLE_LABELS = {
        'support':        '🎫 پشتیبان (فقط تیکت)',
        # 🌊 موج C1 — rename برچسب‌ها (کلید نقش دست‌نخورده):
        # content_admin  = ادمین ارشد محتوا (همه ورودی‌ها + سراسری)
        # content_scoped = ادمین محتوای ورودی خاص (قفل‌شده روی scope_intake)
        'content_admin':  '🎓 ادمین ارشد محتوا',
        'content_scoped': '📅 ادمین محتوای ورودی خاص',
        'broadcaster':    '📢 مسئول اطلاعیه',
        'reviewer':       '🤓 خرخون (بررسی گزارش سوال/جزوه)',   # FIX جدید
        'bot_admin':      '👮 ادمین ربات (نماینده)',            # FIX جدید
        'grade_rep':      '📊 نماینده ورودی (ثبت نمره)',        # FIX جدید
    }

    # ماتریس مجوزها برای هر نقش — استفاده در has_permission
    ROLE_PERMISSIONS = {
        'support':        {'tickets'},
        'content_admin':  {'content', 'questions_review'},
        'content_scoped': {'content_scoped', 'questions_review_scoped'},
        'broadcaster':    {'broadcast'},
        'reviewer':       {'reports_review'},                          # FIX جدید
        'bot_admin':      {'users', 'schedules', 'notifications', 'broadcast'},      # FIX جدید
        'grade_rep':      {'grades_scoped'},                           # FIX جدید
    }

    async def add_admin_role(self, uid: int, role: str, added_by: int,
                              scope_intake: str = None) -> bool:
        """افزودن نقش فرعی ادمین — اگه از قبل نقشی داشت، آپدیت میشه"""
        if role not in self.ROLE_LABELS:
            return False
        await self.admin_roles.update_one(
            {'_id': uid},
            {'$set': {
                'role':         role,
                'scope_intake': scope_intake,
                'added_by':     added_by,
                'added_at':     datetime.now().isoformat(),
            }},
            upsert=True
        )
        # 🛡 RBAC-W1 — آینه‌ی دوطرفه: کالکشن جدید هم هم‌زمان به‌روز
        # می‌شود تا هر دو مخزن قدیمی/جدید همیشه Sync بمانند (§۵).
        await self._add_role_key(uid, role, scope_intake)
        return True

    async def remove_admin_role(self, uid: int):
        # 🛡 RBAC-W1 — قبل از حذف، کلید نقش را می‌دانیم تا آینه را هم پاک کنیم
        doc = await self.get_admin_role(uid)
        await self.admin_roles.delete_one({'_id': uid})
        if doc and doc.get('role'):
            await self._remove_role_key(uid, doc['role'])

    async def get_admin_role(self, uid: int) -> dict:
        """نقش فرعی یک کاربر — None اگه نداشت"""
        return await self.admin_roles.find_one({'_id': uid})

    async def get_all_admin_roles(self) -> list:
        return await self.admin_roles.find({}).sort('added_at', -1).to_list(100)

    async def has_permission(self, uid: int, permission: str) -> bool:
        """
        چک کردن دسترسی — ADMIN_ID (مدیر ارشد) همیشه همه‌چیز دارد.
        بقیه بر اساس admin_roles چک می‌شوند.
        """
        if uid == int(os.getenv('ADMIN_ID', '0')):
            return True
        doc = await self.get_admin_role(uid)
        legacy_ok = False
        if doc:
            perms = self.ROLE_PERMISSIONS.get(doc.get('role', ''), set())
            legacy_ok = permission in perms
        # 🛡 RBAC-W1 — مسیر دیتابیس‌محور (مکمل مسیر قدیمی؛ هیچ
        # دسترسی قبلی کم نمی‌شود، فقط نقش‌های جدید هم پاس می‌شوند)
        if not legacy_ok:
            legacy_ok = await self.has_perm(uid, permission)
        return legacy_ok

    async def get_scoped_intake(self, uid: int) -> str:
        """
        اگه کاربر مدیر محتوای محدود به یک ورودی خاص باشد، کد آن
        ورودی را برمی‌گرداند، وگرنه None (یعنی دسترسی کامل/بدون محدودیت)
        🌊 موج C1: منبع دوم — دارندگان مجوز content.scoped که فقط در
        user_roles.scope_intake ثبت شده‌اند (داربست تک‌منبع RBAC).
        """
        if uid == int(os.getenv('ADMIN_ID', '0')):
            return None
        doc = await self.get_admin_role(uid)
        if doc and doc.get('role') == 'content_scoped':
            return doc.get('scope_intake')
        # C1 — fallback: نقش دیتابیس‌محور با scope (میرور دوطرفه موجود،
        # ولی اگر user_roles جلوتر بود، scope از آنجا خوانده می‌شود)
        ur = await self.user_roles.find_one({'_id': uid})
        if ur and ur.get('scope_intake'):
            scope = ur.get('scope_intake')
            keys  = list(ur.get('roles') or [])
            if 'content_scoped' in keys:
                return scope
            # نقش سفارشی دارای مجوز content.scoped
            if await self.has_perm(uid, 'content.scoped'):
                return scope
        return None

    # ══════════════════════════════════════════════════
    #  🌊 موج C1 — متن (scope) محتوای ورودی‌محور
    #  قرارداد: intake='' یعنی «🌐 سراسری» (شامل داده legacy).
    #  لنگرهای scope: bs_lessons / ref_subjects / questions / qbank_files
    #  فرزندان scope را از والد به ارث می‌برند (resolver زنجیره‌ای).
    # ══════════════════════════════════════════════════

    async def get_content_scope(self, uid: int) -> dict:
        """
        منبع واحد تصمیم scope محتوا (§۸ spec):
          {'kind':'global'}              → ادمین ارشد محتوا/مالک/ادمین
          {'kind':'scoped','intake': X}  → ادمین محتوای ورودی خاص
          None                           → کاربر عادی (دسترسی مدیریتی ندارد)
        ترتیب: global همیشه بر scoped غلبه دارد (Never-Narrow).
        """
        if uid == int(os.getenv('ADMIN_ID', '0')):
            return {'kind': 'global', 'intake': None}
        u = await self.get_user(uid)
        if u and u.get('role') in ('admin', 'content_admin'):
            return {'kind': 'global', 'intake': None}
        doc = await self.get_admin_role(uid)
        if doc and doc.get('role') == 'content_scoped' and doc.get('scope_intake'):
            return {'kind': 'scoped', 'intake': doc.get('scope_intake')}
        # RBAC دیتابیس‌محور
        if await self.has_perm(uid, 'content.manage'):
            return {'kind': 'global', 'intake': None}
        if await self.has_perm(uid, 'content.scoped'):
            scope = await self.get_scoped_intake(uid)
            if scope:
                return {'kind': 'scoped', 'intake': scope}
            # مجوز scoped بدون scope تنظیم‌شده ⇒ legacy رفتار: فقط سراسری
            return {'kind': 'scoped', 'intake': ''}
        return None

    async def can_access_intake(self, uid: int, intake: str) -> bool:
        """enforce مدیریتی: آیا actor اجازه‌ی CRUD/مشاهده‌ی مدیریتی محتوای
        این intake را دارد؟ global → همه؛ scoped → فقط دقیقاً scope خودش."""
        scope = await self.get_content_scope(uid)
        if not scope:
            return False
        if scope['kind'] == 'global':
            return True
        return (intake or '') == (scope.get('intake') or '')

    # ── resolverهای زنجیره‌ای intake (پیش‌فرض '' = سراسری) ──

    async def lesson_intake(self, lesson_id: str) -> str:
        try:
            d = await self.bs_lessons.find_one(
                {'_id': ObjectId(lesson_id)})
            return (d or {}).get('intake') or ''
        except Exception:
            return ''

    async def session_intake(self, session_id: str) -> str:
        s = await self.bs_get_session(session_id)
        if not s:
            return ''
        return await self.lesson_intake(s.get('lesson_id', ''))

    async def content_intake(self, content_id: str) -> str:
        c = await self.bs_get_content_item(content_id)
        if not c:
            return ''
        return await self.session_intake(c.get('session_id', ''))

    async def ref_subject_intake(self, subject_id: str) -> str:
        try:
            d = await self.ref_subjects.find_one(
                {'_id': ObjectId(subject_id)})
            return (d or {}).get('intake') or ''
        except Exception:
            return ''

    async def ref_book_intake(self, book_id: str) -> str:
        b = await self.ref_get_book(book_id)
        if not b:
            return ''
        return await self.ref_subject_intake(b.get('subject_id', ''))

    async def ref_file_intake(self, file_id: str) -> str:
        f = await self.ref_get_file(file_id)
        if not f:
            return ''
        return await self.ref_book_intake(f.get('book_id', ''))

    async def question_intake(self, qid: str) -> str:
        q = await self.get_question_by_id(qid)
        return (q or {}).get('intake') or ''

    def student_intake_filter(self, user_intake: str):
        """لیست intakeهای قابل مشاهده برای دانشجو: ورودی خودش + سراسری.
        این تنها قرارداد خواندن سمت دانشجوست (Bot + API)."""
        return [user_intake or '', ''] if user_intake else ['']

    # ══════════════════════════════════════════════════
    #  🛡 RBAC دیتابیس‌محور — موج W1 (Execution Contract 🔒)
    #  تک‌منبع حقیقت: کالکشن‌های roles / user_roles / perm_catalog
    #  قوانین قفل (§۴ و §۶ قرارداد):
    #   • هیچ نقش/مجوز/برچسب/رنگ/آیکون جدیدی «در کد» ساخته نمی‌شود —
    #     دو ثابت زیر فقط بذر اولیه‌ی idempotent‌اند؛ پس از seed،
    #     خوانده/نوشته فقط از دیتابیس (تغییر دستی ادمین حفظ می‌شود).
    #   • Improve, Never Replace: admin_roles و users.role به‌عنوان
    #     mirror سازگاری دوطرفه زنده می‌مانند (§۱۰ سند).
    #   • ADMIN_ID (مالک) همیشه بای‌پس — تنها استثنای قرارداد §۸.
    # ══════════════════════════════════════════════════

    # دسته‌های مجوز (حفظ ترتیب نمایش در ماتریس مینی‌اپ)
    PERM_CATEGORIES = [
        ('users',         'کاربران'),
        ('roles',         'نقش‌ها'),
        ('content',       'محتوا'),
        ('questions',     'سؤالات'),
        ('schedules',     'برنامه و امتحان'),
        ('grades',        'نمرات'),
        ('tickets',       'تیکت'),
        ('reports',       'گزارش‌ها'),
        ('notifications', 'اعلان‌ها'),
        ('ai',            'هوشیار'),
        ('subscription',  'اشتراک'),
        ('stats',         'آمار'),
        ('prestige',      'پرستیژ'),
        ('settings',      'تنظیمات'),
        ('backup',        'بکاپ'),
        ('system',        'سیستم'),
    ]

    # کاتالوگ مجوزها — (key, برچسب فارسی, دسته)
    # هر سوییچ تکی است (§۶): هیچ گروه‌بندی منطقی در کد نیست.
    PERMISSION_CATALOG = [
        ('users.view',           'مشاهده‌ی کاربران',            'users'),
        ('users.manage',         'مدیریت کاربران',              'users'),
        ('users.suspend',        'تعلیق/رفع تعلیق کاربر',       'users'),
        ('users.delete',         'حذف/بلاک کاربر',              'users'),
        ('users.message',        'ارسال پیام به کاربر',         'users'),
        ('roles.manage',         'مدیریت نقش‌ها و مجوزها',      'roles'),
        ('content.manage',       'مدیریت محتوا (کلی)',          'content'),
        ('content.scoped',       'محتوای محدود به ورودی',       'content'),
        ('questions.review',     'بررسی سؤالات پیشنهادی',       'questions'),
        ('questions.review_scoped','بررسی سؤالات (ورودی خود)',  'questions'),
        ('questions.delete',     'حذف سؤال',                    'questions'),
        ('schedules.manage',     'مدیریت برنامه و امتحان',      'schedules'),
        ('grades.manage',        'مدیریت نمرات (کلی)',          'grades'),
        ('grades.scoped',        'ثبت نمره (ورودی خود)',        'grades'),
        ('tickets.reply',        'پاسخ به تیکت',                'tickets'),
        ('tickets.manage',       'مدیریت وضعیت تیکت‌ها',        'tickets'),
        ('reports.review',       'بررسی گزارش سؤال/جزوه',       'reports'),
        ('notifications.manage', 'تنظیمات پیش‌فرض اعلان',       'notifications'),
        ('broadcast.send',       'ارسال همگانی/اطلاعیه',        'notifications'),
        ('ai.manage',            'مدیریت هوشیار',               'ai'),
        ('subscription.manage',  'مدیریت اشتراک‌ها',            'subscription'),
        ('stats.view',           'آمار و داشبورد مدیریتی',      'stats'),
        ('prestige.manage',      'تنظیمات پرستیژ',              'prestige'),
        ('settings.manage',      'تنظیمات سیستم',               'settings'),
        ('backup.manage',        'بکاپ و بازیابی',              'backup'),
        ('audit.view',           'مشاهده‌ی لاگ حساس',           'system'),
        ('system.manage',        'عملیات حساس سیستم',           'system'),
    ]

    # نگاشت مجوز قدیمی (ROLE_PERMISSIONS) → کلیدهای جدید — فقط برای بذر
    _LEGACY_PERM_MAP = {
        'tickets':                 ['tickets.reply', 'tickets.manage'],
        'content':                 ['content.manage'],
        'questions_review':        ['questions.review'],
        'content_scoped':          ['content.scoped'],
        'questions_review_scoped': ['questions.review_scoped'],
        'broadcast':               ['broadcast.send'],
        'reports_review':          ['reports.review'],
        'users':                   ['users.view', 'users.manage'],
        'schedules':               ['schedules.manage'],
        'notifications':           ['notifications.manage'],
        'grades_scoped':           ['grades.scoped'],
        'grades':                  ['grades.manage'],
    }

    async def ensure_rbac_seed(self) -> dict:
        """بذر idempotent (§۱۰): اجرای دوباره هیچ چیز را بازنویسی نمی‌کند.

        roles با $setOnInsert ساخته می‌شوند ⇒ ویرایش دستی ادمین
        (نام/رنگ/مجوزها) در اجراهای بعدی سالم می‌ماند. نقش‌های سیستم
        با permsِ نگاشت‌یافته از ماتریس قدیمی — قفل رفتاری کامل."""
        now = datetime.now().isoformat()

        # ۱) کاتالوگ مجوزها: فقط اگر کالکشن خالی است
        perms_seeded = 0
        if await self.perm_catalog.count_documents({}) == 0:
            for key, label, cat in self.PERMISSION_CATALOG:
                await self.perm_catalog.update_one(
                    {'_id': key},
                    {'$setOnInsert': {
                        '_id': key, 'label': label, 'category': cat}},
                    upsert=True,
                )
            perms_seeded = len(self.PERMISSION_CATALOG)

        # ۲) نقش‌های سیستمی: upsertِ صرفاً-درج (ویرایش‌ها حفظ می‌شود)
        roles_before = await self.roles.count_documents({})
        for key, label in self.ROLE_LABELS.items():
            legacy_perms = self.ROLE_PERMISSIONS.get(key, set())
            perms = []
            for lp in legacy_perms:
                perms.extend(self._LEGACY_PERM_MAP.get(lp, [lp]))
            # یکتا و مرتب — بدون تکرار
            perms = sorted(set(perms))
            await self.roles.update_one(
                {'_id': key},
                {'$setOnInsert': {
                    '_id':        key,
                    'label':      label,
                    'desc':       '',
                    'icon':       label.split(' ')[0] if label else '🛡',
                    'color':      '#70A7FF',
                    'priority':   50,
                    'system':     True,   # حذف‌ناپذیر ولی قابل ویرایش
                    'active':     True,
                    'visible':    True,
                    'perms':      perms,
                    'created_at': now,
                    'updated_at': now,
                }},
                upsert=True,
            )
        roles_after = await self.roles.count_documents({})
        return {
            'roles_seeded': max(0, roles_after - roles_before),
            'perms_seeded': perms_seeded,
        }

    async def rbac_migrate_users(self) -> dict:
        """مهاجرت idempotent (§۱۰): admin_roles + users.role → user_roles.

        از addToSet-منطقی (dedup در پایتون) استفاده می‌کند ⇒ اجرای چندباره
        هیچ داده‌ای تکرار/بازنویسی نمی‌کند؛ هیچ نقشی حذف نمی‌شود."""
        count_ar = 0
        async for doc in self.admin_roles.find({}):
            role = doc.get('role')
            if not role:
                continue
            await self._add_role_key(
                doc['_id'], role, doc.get('scope_intake'))
            count_ar += 1

        count_ur = 0
        legacy = await self.users.find(
            {'role': {'$in': ['content_admin', 'support']}}
        ).to_list(None)
        for u in legacy:
            role_key = u.get('role')
            if role_key in ('content_admin', 'support'):
                await self._add_role_key(u['user_id'], role_key)
                count_ur += 1

        return {'from_admin_roles': count_ar, 'from_users_role': count_ur}

    # ══════════════════════════════════════════════════
    #  🌊 موج C1 — مهاجرت scope ورودی محتوا
    # ══════════════════════════════════════════════════

    async def migrate_content_intake_scope(self) -> dict:
        """مهاجرت Safe + Idempotent + Re-runnable (§۲۴ spec).

        ۱) backfill «intake:''» (= 🌐 سراسری/legacy) روی چهار لنگر
           محتوایی — فقط اسنادِ فاقد فیلد ($exists:false) ⇒ اجرای
           دوباره صفر نوشتاری و هیچ overrideای رخ نمی‌دهد. هیچ سندی
           حذف نمی‌شود و داده‌ی بدون scope orphan نمی‌شود ('' همان
           سطل نگه‌داری legacy است).
        ۲) rename شرطی label نقش‌های content_* در کالکشن roles — فقط
           اگر label هنوز یکی از برچسب‌های قدیمیِ شناخته‌شده باشد؛
           برچسب سفارشی‌شده‌ی دستی ادمین هرگز له نمی‌شود.
        ۳) وضعیت اجرا در کالکشن migrations ثبت می‌شود (قابل ردیابی).
        """
        now = datetime.now().isoformat()
        backfilled = {}
        for name, col in [('bs_lessons', self.bs_lessons),
                          ('ref_subjects', self.ref_subjects),
                          ('questions', self.questions),
                          ('qbank_files', self.qbank_files)]:
            r = await col.update_many(
                {'intake': {'$exists': False}},
                {'$set': {'intake': ''}},
            )
            backfilled[name] = r.modified_count

        # rename شرطی label — کلید نقش دست‌نخورده می‌ماند
        label_map = {
            'content_admin': {
                'olds': ['🎓 مدیر محتوا (کلی)', 'مدیر محتوا (کلی)',
                         'مدیر محتوا کلی', 'مدیر محتوا'],
                'new': self.ROLE_LABELS['content_admin'],
            },
            'content_scoped': {
                'olds': ['📅 مدیر محتوا (محدود به ورودی)',
                         '📅 مدیر محتوا (محدود)', 'مدیر محتوا (محدود به ورودی)'],
                'new': self.ROLE_LABELS['content_scoped'],
            },
        }
        labels_renamed = 0
        for key, cfg in label_map.items():
            r = await self.roles.update_one(
                {'_id': key, 'label': {'$in': cfg['olds']}},
                {'$set': {'label': cfg['new'],
                          'icon': cfg['new'].split(' ')[0],
                          'updated_at': now}},
            )
            labels_renamed += r.modified_count

        await self.migrations.update_one(
            {'_id': 'c1_content_intake_scope'},
            {'$set': {'backfilled': backfilled,
                      'labels_renamed': labels_renamed,
                      'last_run_at': now},
             '$setOnInsert': {'first_run_at': now}},
            upsert=True,
        )
        return {'backfilled': backfilled, 'labels_renamed': labels_renamed}

    # ──────────────────────────────────────────────────
    #  CRUD نقش‌ها
    # ──────────────────────────────────────────────────

    async def list_roles(self) -> list:
        """همه‌ی نقش‌ها — مرتب: priority ↑ سپس برچسب (منبع UI/API)."""
        docs = await self.roles.find({}).to_list(None)
        return sorted(
            docs,
            key=lambda d: (d.get('priority', 99), d.get('label', '')),
        )

    async def get_role(self, key: str):
        return await self.roles.find_one({'_id': key})

    async def role_label(self, key: str) -> str:
        """برچسب نقش: دیتابیس اول، fallback به لیست قدیمی (سازگاری)."""
        doc = await self.get_role(key)
        if doc and doc.get('label'):
            return doc['label']
        return self.ROLE_LABELS.get(key, key)

    async def _valid_perm_keys(self) -> set:
        docs = await self.perm_catalog.find({}).to_list(None)
        if not docs:
            return {k for k, _, _ in self.PERMISSION_CATALOG}
        return {d['_id'] for d in docs}

    async def create_role(self, payload: dict, actor: int = 0):
        """ساخت نقش دلخواه (§۶). خروجی: (doc, err)"""
        key = (payload.get('key') or '').strip()
        label = (payload.get('label') or '').strip()
        if not label or len(label) > 60:
            return None, 'label_invalid'
        if not key:
            key = f"custom_{int(datetime.now().timestamp())}"
        if not key.isidentifier() or ' ' in key or len(key) > 40:
            return None, 'key_invalid'
        if await self.get_role(key):
            return None, 'key_exists'
        valid = await self._valid_perm_keys()
        perms = sorted({p for p in (payload.get('perms') or [])
                        if p in valid})
        now = datetime.now().isoformat()
        doc = {
            '_id':        key,
            'label':      label,
            'desc':       (payload.get('desc') or '')[:200],
            # آیکون پیش‌فرض از خودِ برچسب (توکن اول اگر اموجی باشد)
            # — هم‌سو با منطق seed؛ در غیر این صورت 🛡
            'icon':       (payload.get('icon')
                           or label.split(' ')[0][:4] or '🛡')[:4],
            'color':      payload.get('color') or '#70A7FF',
            'priority':   int(payload.get('priority') or 90),
            'system':     False,
            'active':     True,
            'visible':    True,
            'perms':      perms,
            'created_at': now,
            'updated_at': now,
        }
        await self.roles.insert_one(doc)
        return doc, None

    _ROLE_EDITABLE = ('label', 'desc', 'icon', 'color',
                      'priority', 'active', 'visible', 'perms')

    async def update_role(self, key: str, changes: dict, actor: int = 0):
        """ویرایش نقش — فقط فیلدهای لیست‌سفید _ROLE_EDITABLE.
        label خالی ممنوع؛ perms فقط کلیدهای معتبر کاتالوگ."""
        old = await self.get_role(key)
        if not old:
            return None, 'not_found'
        valid = await self._valid_perm_keys()
        updates = {}
        for field in self._ROLE_EDITABLE:
            if field not in changes or changes[field] is None:
                continue
            val = changes[field]
            if field == 'label':
                val = str(val).strip()
                if not val or len(val) > 60:
                    return None, 'label_invalid'
            elif field == 'perms':
                val = sorted({p for p in val if p in valid})
            elif field == 'priority':
                val = max(1, min(999, int(val)))
            updates[field] = val
        if not updates:
            return old, None
        updates['updated_at'] = datetime.now().isoformat()
        updates['updated_by'] = actor
        await self.roles.update_one({'_id': key}, {'$set': updates})
        return await self.get_role(key), None

    async def delete_role(self, key: str):
        """حذف نقش — گاردها (§۶): system و نقشِ دارای کاربر حذف‌ناپذیر."""
        role = await self.get_role(key)
        if not role:
            return False, 'not_found', 0
        if role.get('system'):
            return False, 'system_role', 0
        count = 0
        async for doc in self.user_roles.find({}):
            if key in (doc.get('roles') or []):
                count += 1
        if count:
            return False, 'in_use', count
        await self.roles.delete_many({'_id': key})
        return True, '', 0

    async def users_count_by_role(self) -> dict:
        counts = {}
        async for doc in self.user_roles.find({}):
            for key in (doc.get('roles') or []):
                counts[key] = counts.get(key, 0) + 1
        return counts

    # ──────────────────────────────────────────────────
    #  تخصیص نقش به کاربر (چندنقشی — Union مجوزها)
    # ──────────────────────────────────────────────────

    async def _add_role_key(self, uid: int, key: str,
                            scope_intake: str = None):
        doc = await self.user_roles.find_one({'_id': uid})
        roles = list((doc or {}).get('roles') or [])
        changed = key not in roles
        if changed:
            roles.append(key)
        updates = {'updated_at': datetime.now().isoformat()}
        if changed:
            updates['roles'] = roles
        if scope_intake is not None:
            updates['scope_intake'] = scope_intake
        if changed or scope_intake is not None or not doc:
            await self.user_roles.update_one(
                {'_id': uid}, {'$set': updates}, upsert=True)
        # 🛡 RBAC-W3 — پروجکشن میراثی هم‌زمان (§۵)
        await self._sync_admin_role_projection(uid)
        return changed

    async def _remove_role_key(self, uid: int, key: str):
        doc = await self.user_roles.find_one({'_id': uid})
        roles = [r for r in ((doc or {}).get('roles') or [])
                 if r != key]
        await self.user_roles.update_one(
            {'_id': uid},
            {'$set': {'roles': roles,
                      'updated_at': datetime.now().isoformat()}},
            upsert=True)
        # 🛡 RBAC-W3 — پروجکشن میراثی هم‌زمان (§۵)
        await self._sync_admin_role_projection(uid)
        return True

    async def get_user_roles(self, uid: int) -> dict:
        """نقش‌های کاربر: کلیدها + سندهای resolveشده + scope.

        نقش ناموجود (custom حذف‌شده) در خروجی نمی‌آید ولی کلیدش
        در keys باقی می‌ماند تا UI بتواند هشدار دهد."""
        doc = await self.user_roles.find_one({'_id': uid})
        keys = list((doc or {}).get('roles') or [])
        roles = []
        for key in keys:
            role = await self.get_role(key)
            if role:
                roles.append(role)
        return {
            'keys': keys,
            'roles': roles,
            'scope_intake': (doc or {}).get('scope_intake'),
        }

    async def get_user_perms(self, uid: int) -> set:
        """Union مجوزهای نقش‌های «فعال» — §۷ قرارداد (Multi Role).

        مالک همیشه کل کاتالوگ را دارد (تنها استثنا — §۸)."""
        valid = await self._valid_perm_keys()
        if uid == int(os.getenv('ADMIN_ID', '0')):
            return set(valid)
        perms = set()
        info = await self.get_user_roles(uid)
        for role in info['roles']:
            if not role.get('active', True):
                continue
            perms.update(role.get('perms') or [])
        return perms & valid

    async def has_perm(self, uid: int, permission: str) -> bool:
        """چک مرکزی دسترسی — تنها نقطه‌ی تصمیم Permission-Driven.

        بای‌پسها (قفل سازگاری): ۱) مالک ADMIN_ID  ۲) users.role=='admin'
        قدیمی (سوپریوزر میراثی که در چند مسیر قدیمی پذیرفته شده است)."""
        if uid == int(os.getenv('ADMIN_ID', '0')):
            return True
        u = await self.get_user(uid)
        if u and u.get('role') == 'admin':
            return True
        return permission in await self.get_user_perms(uid)

    async def sync_legacy_role_mirror(self, uid: int) -> str:
        """نگه‌داشت users.role (mirror سازگاری) — §۵ Sync.

        قانون: قوی‌ترین نقش سازگارِ قدیمی، از روی user_roles محاسبه
        می‌شود؛ users.role=='admin' هرگز دست‌نخورده می‌ماند؛ اگر سند
        user_roles وجود نداشته باشد (کاربر دست‌نخورده‌ی RBAC) هیچ
        تغییری نمی‌دهد ⇒ هیچ downgrade بی‌دلیلی ممکن نیست."""
        doc = await self.user_roles.find_one({'_id': uid})
        if not doc:
            return ''
        user = await self.get_user(uid)
        cur = (user or {}).get('role', 'student')
        if cur == 'admin':
            return cur
        info = await self.get_user_roles(uid)
        keys = info['keys']
        perms = await self.get_user_perms(uid)
        target = 'student'
        if 'content_admin' in keys or 'content.manage' in perms:
            target = 'content_admin'
        elif 'support' in keys or 'tickets.reply' in perms:
            target = 'support'
        if target != cur:
            await self.update_user(uid, {'role': target})
        return target

    async def _sync_admin_role_projection(self, uid: int) -> None:
        """پروجکشن admin_roles (تک‌نقشی میراثی) از روی user_roles
        (چندنقشی) — §۵ Sync قرارداد: منوهای ربات که مدل قدیمی را
        می‌خوانند برای کلیدهای legacy همیشه درست می‌مانند.
        پایداری: نقش فعلی admin_roles اگر هنوز تخصیص‌یافته است ابقا
        می‌شود؛ در غیر این صورت اولین کلید legacy از لیست کاربر."""
        doc = await self.user_roles.find_one({'_id': uid})
        keys = list((doc or {}).get('roles') or [])
        legacy_keys = [k for k in keys if k in self.ROLE_LABELS]
        cur = await self.admin_roles.find_one({'_id': uid})
        cur_role = (cur or {}).get('role')
        if cur_role and cur_role in legacy_keys:
            primary = cur_role
        elif legacy_keys:
            primary = legacy_keys[0]
        else:
            primary = None
        if primary is None:
            if cur is not None:
                await self.admin_roles.delete_many({'_id': uid})
            return
        scope = (doc or {}).get('scope_intake')
        if cur and cur_role == primary \
           and cur.get('scope_intake') == scope:
            return  # بدون تغییر — صفر نویز نوشتاری
        await self.admin_roles.update_one(
            {'_id': uid},
            {'$set': {
                'role':         primary,
                'scope_intake': scope,
                'added_by':     'rbac',
                'added_at':     datetime.now().isoformat(),
            }},
            upsert=True,
        )

    # ══════════════════════════════════════════════════
    #  🏷 Identity Layer v1 — لقب (Nickname)
    #  تک‌منبع نمایش نام (§۴): full_name=هویت واقعی (آموزش/
    #  مدیریت)، nickname=هویت اجتماعی، display_name=آنچه
    #  رابط‌ها نشان می‌دهند (nickname یا name). همه‌چیز
    #  در همان سند users است ⇒ Hot Path صفر کوئری اضافه.
    #  Future-ready: رنگ/تأیید/بج لقب = فقط توسعه‌ی
    #  display_name_of، بدون Refactor.
    # ══════════════════════════════════════════════════

    # کلمات رزروشده (بذر — در identity_config قابل ویرایش است)
    RESERVED_NICKNAMES = [
        'admin', 'support', 'system', 'developer', 'moderator',
        'bot', 'humsyar', 'هامزیار', 'مدیر', 'پشتیبانی', 'ادمین',
    ]

    IDENTITY_DEFAULTS = {
        'min_length':       3,
        'max_length':       24,
        'cooldown_days':    30,
        'allow_emoji':      True,
        'allow_spaces':     True,
        'blacklist':        [],
        'reserved_words':   RESERVED_NICKNAMES,
    }

    def display_name_of(self, user: dict) -> str:
        """🏷 تک‌منبع نمایش نام — SYNC (بدون کوئری، §Performance).

        قانون §۳: لقب اگر هست، همان؛ وگرنه نام واقعی."""
        if not isinstance(user, dict):
            return 'کاربر هامزیار'
        nick = (user.get('nickname') or '').strip()
        if nick:
            return nick
        return (user.get('name') or '').strip() or 'کاربر هامزیار'

    # پیام‌های فارسی خطای لقب — تک‌منبع مشترک API و Bot (§یک منبع واحد)
    NICK_ERROR_FA = {
        'empty':        'لقب خالی است',
        'too_short':    'لقب کوتاه است (حداقل طول از تنظیمات)',
        'too_long':     'لقب بلند است (حداکثر از تنظیمات)',
        'bad_chars':    'فقط حروف فارسی/انگلیسی، عدد، فاصله، _ و - و ایموجی محدود مجاز است',
        'emoji_spam':   'بیش از حد ایموجی (حداکثر ۳ عدد)',
        'emoji_only':   'لقب نمی‌تواند فقط ایموجی باشد',
        'emoji_denied': 'استفاده از ایموجی در لقب خاموش است',
        'space_denied': 'فاصله در لقب مجاز نیست',
        'link_denied':  'لینک در لقب مجاز نیست',
        'phone_denied': 'شماره تماس در لقب مجاز نیست',
        'tg_denied':    'آیدی/اشاره تلگرامی در لقب مجاز نیست',
        'reserved':     'این لقب رزرو شده است',
        'blacklisted':  'این لقب مجاز نیست',
        'taken':        'این لقب قبلاً انتخاب شده است',
        'cooldown':     'فعلاً نمی‌توانی لقب را تغییر بدهی (Cooldown)',
        'not_found':    'کاربر پیدا نشد',
    }

    def nick_error_text(self, err: str, info: dict = None) -> str:
        """متن فارسی خطای لقب (+ تاریخ در Cooldown) — مشترک API/Bot."""
        info = info or {}
        detail = self.NICK_ERROR_FA.get(err, err or 'خطای نامشخص')
        if err == 'cooldown' and info.get('next_change_at'):
            detail = (f"{detail} — "
                      f"از {str(info['next_change_at'])[:10]} به بعد")
        return detail

    async def get_identity_config(self) -> dict:
        """تنظیمات لایه‌ی هویت — قابل تغییر بدون Deploy (§Settings)."""
        doc = await self.settings.find_one({'_id': 'identity_config'})
        cfg = dict(self.IDENTITY_DEFAULTS)
        if doc:
            overrides = doc.get('config') or {}
            for key in self.IDENTITY_DEFAULTS:
                if key in overrides and overrides[key] is not None:
                    cfg[key] = overrides[key]
        return cfg

    async def update_identity_config(self, patch: dict,
                                     actor: int = 0) -> dict:
        """به‌روزرسانی whitelist تنظیمات هویت (پنل ادمین)."""
        allowed = set(self.IDENTITY_DEFAULTS)
        clean = {k: v for k, v in (patch or {}).items() if k in allowed}
        await self.settings.update_one(
            {'_id': 'identity_config'},
            {'$set': {**{f'config.{k}': v for k, v in clean.items()},
                      'updated_by': actor,
                      'updated_at': datetime.now().isoformat()}},
            upsert=True,
        )
        return await self.get_identity_config()

    # ── Normalize و Validate (کاملاً سمت سرور — §قوانین) ──

    _INVISIBLE_CHARS = (
        '​‌‍‎‏‪‫‬‭‮⁠'
        '﻿᠎‌'
    )

    _EMOJI_RE = None   # lazy compile

    @classmethod
    def _emoji_pattern(cls):
        if cls._EMOJI_RE is None:
            import re as _re
            cls._EMOJI_RE = _re.compile(
                '[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍‏⁉‼™↔-↙'
                '⤴-⤵�-�️]'
            )
        return cls._EMOJI_RE

    def _norm_nick(self, raw: str) -> str:
        """Normalize (§قوانین): NFKC (Ａｍｉｒ→Amir) + حذف
        کاراکترهای نامرئی/Zero-Width + جمع‌کردن فاصله‌های اضافه + trim."""
        import re
        import unicodedata
        text = unicodedata.normalize('NFKC', raw or '')
        for ch in self._INVISIBLE_CHARS:
            text = text.replace(ch, '')
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def validate_nickname(self, raw: str, cfg: dict):
        """اعتبارسنجی کامل لقب — خروجی: (ok, err, clean)

        کنترل‌ها: طول، الفبا (فا/En/عدد/_/-/space)، سقف ایموجی،
        HTML/Markdown/RTL-hack/Injection (از مسیر الفبا رد می‌شوند)،
        لینک/تلفن/@آیدی، رزرو و بلک‌لیست (case-insensitive)."""
        import re
        clean = self._norm_nick(raw)

        if not clean:
            return False, 'empty', clean

        # طول با شمارش یونیکد (بدون ایموجی‌ها هم طول کافی باشد؟ — خیر؛ کل)
        min_len = int(cfg.get('min_length', 3))
        max_len = int(cfg.get('max_length', 24))
        if len(clean) < min_len:
            return False, 'too_short', clean
        if len(clean) > max_len:
            return False, 'too_long', clean

        # ایموجی — سقف ۳ عدد ضداسپم (§Emoji Spam)
        emoji_hits = self._emoji_pattern().findall(clean)
        if emoji_hits and not cfg.get('allow_emoji', True):
            return False, 'emoji_denied', clean
        if len(emoji_hits) > 3:
            return False, 'emoji_spam', clean
        if emoji_hits and len(clean) == len(emoji_hits) + (
                ' ' in clean and clean.count(' ') or 0):
            # فقط ایموجی/فاصله = بدون حرف ⇒ نام نیست
            letters = self._emoji_pattern().sub('', clean).replace(' ', '')
            if not letters:
                return False, 'emoji_only', clean

        if ' ' in clean and not cfg.get('allow_spaces', True):
            return False, 'space_denied', clean

        # الفبا — هرچیزی خارج از این‌ها (HTML/Markdown/@/لینک‌گرافی/
        # کاراکترهای کنترل/اسکریپت) داری رد مستقیم
        base = self._emoji_pattern().sub('', clean)
        if not re.fullmatch(
            r'[A-Za-z0-9_\-\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF ]+',
            base,
        ):
            return False, 'bad_chars', clean

        # لینک/تلفن/آیدی تلگرام (§Abuse Prevention)
        low = clean.lower()
        if re.search(r'(https?|www\.|t\.me|\.com|\.ir|\.net|\.org)', low):
            return False, 'link_denied', clean
        if re.search(r'\d[\d\s\-\.]{7,}\d', low):
            return False, 'phone_denied', clean
        if '@' in clean or 'تلگرام' in clean:
            return False, 'tg_denied', clean

        # رزرو + بلک‌لیست (case-insensitive)
        canon = low
        reserved = [str(w).lower() for w in cfg.get('reserved_words') or []]
        blacklist = [str(w).lower() for w in cfg.get('blacklist') or []]
        if canon in reserved:
            return False, 'reserved', clean
        for bad in blacklist:
            if bad and bad in canon:
                return False, 'blacklisted', clean
        return True, '', clean

    async def nickname_status(self, uid: int, user: dict = None) -> dict:
        """وضعیت لقب کاربر برای API پروفایل — اگر `user` سند
        آماده باشد از همان استفاده می‌شود (صفر کوئری اضافه)."""
        if user is None:
            user = await self.get_user(uid) or {}
        cfg = await self.get_identity_config()
        cool = int(cfg.get('cooldown_days', 30))
        last = user.get('nickname_updated_at')
        can_change = True
        next_at = None
        if last:
            try:
                from datetime import timedelta
                last_dt = datetime.fromisoformat(str(last))
                next_dt = last_dt + timedelta(days=cool)
                if datetime.now() < next_dt:
                    can_change = False
                    next_at = next_dt.isoformat()
            except ValueError:
                pass
        return {
            'nickname':           user.get('nickname') or None,
            'display_name':       self.display_name_of(user),
            'can_change_nickname': can_change,
            'next_change_at':     next_at,
            'show_real_name':     user.get('show_real_name', True),
            'cooldown_days':      cool,
        }

    async def set_nickname(self, uid: int, raw: str,
                           changed_by: str = 'user',
                           reason: str = ''):
        """تنظیم/تغییر/پاک‌کردن لقب — خروجی: (ok, err, info)

        • raw خالی ⇒ پاک‌کردن لقب (display به نام واقعی برمی‌گردد)
        • Cooldown فقط برای خود کاربر؛ ادمین (changed_by!='user') بای‌پس
        • History + display_name_cache + Audit (§Audit/§History)"""
        user = await self.get_user(uid)
        if not user:
            return False, 'not_found', {}
        cfg = await self.get_identity_config()
        now = datetime.now().isoformat()
        old_nick = user.get('nickname') or None

        # پاک‌کردن لقب — بدون Cooldown و بدون Validation
        if raw is None or not str(raw).strip():
            await self.update_user(uid, {
                'nickname':            None,
                'nickname_normalized': None,
                'nickname_updated_at': now,
                'display_name_cache':  (user.get('name') or '').strip(),
            })
            await self.users.update_one(
                {'user_id': uid},
                {'$push': {'nickname_history': {
                    'old': old_nick, 'new': None, 'at': now,
                    'by': changed_by, 'reason': reason or 'clear',
                }}},
            )
            await self._audit_nickname(uid, user, old_nick, None,
                                       changed_by, 'حذف لقب')
            return True, '', {'nickname': None,
                              'display_name': (user.get('name') or '').strip()}

        ok, err, clean = self.validate_nickname(raw, cfg)
        if not ok:
            return False, err, {'clean': clean}

        # Cooldown — فقط برای خود کاربر (§تغییر لقب)
        if changed_by == 'user':
            status = await self.nickname_status(uid)
            if not status['can_change_nickname']:
                return False, 'cooldown', {
                    'next_change_at': status['next_change_at']}

        # یکتایی — case-insensitive روی nickname_normalized
        canon = clean.lower()
        clash = await self.users.find_one({
            'nickname_normalized': canon,
            'user_id': {'$ne': uid},
        })
        if clash:
            return False, 'taken', {}

        await self.update_user(uid, {
            'nickname':            clean,
            'nickname_normalized': canon,
            'nickname_updated_at': now,
            'display_name_cache':  clean,
        })
        await self.users.update_one(
            {'user_id': uid},
            {'$push': {'nickname_history': {
                'old': old_nick, 'new': clean, 'at': now,
                'by': changed_by, 'reason': reason or 'set',
            }}},
        )
        await self._audit_nickname(uid, user, old_nick, clean,
                                   changed_by, 'تغییر لقب')
        return True, '', {'nickname': clean, 'display_name': clean}

    async def _audit_nickname(self, uid: int, user: dict,
                              old_nick, new_nick,
                              changed_by: str, action: str):
        """§Audit — هر تغییر لقب با before/after (خطا مسیر را نمی‌شکند)."""
        try:
            performer_id = uid
            if changed_by.startswith('admin:'):
                raw_id = changed_by.split(':', 1)[1]
                if raw_id.isdigit():
                    performer_id = int(raw_id)
            performer = {} if performer_id == uid \
                else (await self.get_user(performer_id) or {})
            await self.log_action(
                performer_id,
                self.display_name_of(performer or user),
                'student' if changed_by == 'user' else 'مدیر',
                action,
                module='Users', severity='INFO',
                target_id=str(uid), target_type='user',
                target_label=self.display_name_of(user),
                before={'nickname': old_nick},
                after={'nickname': new_nick},
                tags=['identity'],
            )
        except Exception:
            pass

    async def set_show_real_name(self, uid: int, value: bool) -> bool:
        """سوئیچ حریم خصوصی (§Privacy) — فقط نمایش را کنترل می‌کند."""
        await self.update_user(uid, {'show_real_name': bool(value)})
        return True

    # ══════════════════════════════════════════════════
    #  لاگ فعالیت حساس (audit_logs)
    # ══════════════════════════════════════════════════

    # FIX جدید: سطوح اهمیت لاگ — برای فیلتر کردن نویز از سیگنال
    SEVERITY_LEVELS = {
        'INFO':     '🟢 INFO',
        'WARNING':  '🟡 WARNING',
        'HIGH':     '🟠 HIGH',
        'CRITICAL': '🔴 CRITICAL',
    }

    # ══════════════════════════════════════════════════
    #  بازطراحی کامل Audit Log — مدل داده غنی
    # ══════════════════════════════════════════════════
    #
    # طبق استاندارد جدید، هر لاگ شامل:
    #   id, timestamp, severity, module, action,
    #   actor{id,name,role}, target{type,id,label},
    #   details, changes[before/after], metadata, correlation_id, tags
    #
    # ماژول‌ها همیشه به انگلیسی در کد ذخیره می‌شوند (پایدار برای
    # کوئری/فیلتر) و فقط هنگام نمایش به فارسی ترجمه می‌شوند.

    MODULE_LABELS_FA = {
        'Users':         'کاربران',
        'Roles':         'نقش‌ها',
        'Settings':      'تنظیمات',
        'Questions':     'سوالات',
        'Content':       'محتوا',
        'Schedules':     'برنامه کلاسی',
        'Tickets':       'تیکت‌ها',
        'Reports':       'گزارش‌ها',
        'Notifications': 'اعلان‌ها',
        'Backup':        'بکاپ',
        'System':        'سیستم',
        'Auth':          'ورود/خروج',
        'Subscription':  'اشتراک',   # FIX جدید
        'Grades':        'نمرات',    # FIX جدید
    }

    async def log_action(self, actor_id: int, actor_name: str, actor_role: str,
                          action: str, module: str, category: str = 'admin',
                          severity: str = 'INFO', target_id: str = '',
                          target_type: str = '', target_label: str = '',
                          before: dict = None, after: dict = None,
                          details: str = '', tags: list = None,
                          correlation_id: str = None) -> str:
        """
        FIX بازطراحی کامل — مدل داده غنی طبق سند:
        actor شامل نقش، target شامل برچسب قابل‌فهم (نه فقط ObjectId خام)،
        changes به‌صورت فهرست فیلد:قبل:بعد، correlation_id برای ردیابی
        عملیات چندمرحله‌ای (مثلاً ارسال همگانی)، و tags برای جستجو.

        target_label: نام/عنوان قابل‌فهم هدف (مثلاً نام کاربر یا متن سوال)
        — این چیزی است که در پیام لاگ به‌جای ObjectId خام نشان داده می‌شود.
        """
        changes = []
        if before and after:
            for key in after:
                changes.append({
                    'field': key,
                    'before': before.get(key, '—'),
                    'after':  after.get(key, '—'),
                })

        doc = {
            'timestamp':      datetime.now().isoformat(),
            'severity':       severity,
            'module':         module,
            'category':       category,
            'action':         action,
            'actor': {
                'id':   actor_id,
                'name': actor_name,
                'role': actor_role or 'نامشخص',
            },
            'target': {
                'type':  target_type,
                'id':    target_id,
                'label': target_label,
            },
            'details':        details,
            'changes':        changes,
            'tags':           tags or [],
            'correlation_id': correlation_id,
        }
        r = await self.audit_logs.insert_one(doc)
        return str(r.inserted_id)

    async def get_recent_logs(self, category: str = None, min_severity: str = None,
                               module: str = None, limit: int = 30) -> list:
        q = {}
        if category:
            q['category'] = category
        if min_severity:
            order = ['INFO', 'WARNING', 'HIGH', 'CRITICAL']
            idx = order.index(min_severity) if min_severity in order else 0
            q['severity'] = {'$in': order[idx:]}
        if module:
            q['module'] = module
        return await self.audit_logs.find(q).sort('timestamp', -1).to_list(limit)

    async def get_actor_role_label(self, uid: int) -> str:
        """
        FIX طبق سند: در ۹۶٪ لاگ‌های قبلی نقش فرستنده مشخص نبود.
        این متد یک‌جا و یکدست نقش واقعی هر کاربر را برمی‌گرداند —
        مدیر ارشد، یا یکی از نقش‌های فرعی، بدون ایموجی (برای متن لاگ).
        """
        if uid == int(os.getenv('ADMIN_ID', '0')):
            return 'مدیر ارشد'
        role_doc = await self.get_admin_role(uid)
        if role_doc:
            label = self.ROLE_LABELS.get(role_doc.get('role', ''), '')
            # حذف ایموجی و پرانتز برای متن لاگ تمیز
            import re
            clean = re.sub(r'^[^\w\u0600-\u06FF]+', '', label).strip()
            return clean or role_doc.get('role', 'نامشخص')
        user = await self.get_user(uid)
        if user and user.get('role') == 'content_admin':
            return 'ادمین ارشد محتوا'
        return 'دانشجو'

    async def get_logs_by_correlation(self, correlation_id: str) -> list:
        """همه‌ی لاگ‌های یک عملیات چندمرحله‌ای (مثل شروع/پیشرفت/پایان broadcast)"""
        return await self.audit_logs.find(
            {'correlation_id': correlation_id}
        ).sort('timestamp', 1).to_list(100)

    async def search_logs_by_tag(self, tag: str, limit: int = 30) -> list:
        """جستجوی لاگ بر اساس تگ — مثلاً 'کاربران' یا 'حذف'"""
        return await self.audit_logs.find(
            {'tags': tag}
        ).sort('timestamp', -1).to_list(limit)

    # ══════════════════════════════════════════════════
    #  گزارش هفتگی/ماهانه خودکار
    # ══════════════════════════════════════════════════

    async def weekly_report_stats(self) -> dict:
        """آمار خلاصه برای گزارش دوره‌ای ادمین"""
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()

        new_users = await self.users.count_documents(
            {'registered_at': {'$gte': week_ago}}
        )
        active_users = await self.answers.distinct(
            'user_id', {'answered_at': {'$gte': week_ago}}
        ) if hasattr(self, 'answers') else []

        # FIX: پرطرفدارترین درس — بر اساس مجموع دانلود محتوای هر درس.
        # bs_content فیلد lesson مستقیم ندارد (فقط session_id) پس باید
        # session → lesson_id → lesson.name را در پایتون join بزنیم.
        top_lesson = None
        try:
            all_content  = await self.bs_content.find({}).to_list(5000)
            all_sessions = await self.bs_sessions.find({}).to_list(2000)
            all_lessons  = await self.bs_lessons.find({}).to_list(500)
            session_to_lesson = {str(s['_id']): s.get('lesson_id', '') for s in all_sessions}
            lesson_id_to_name = {str(l['_id']): l.get('name', '') for l in all_lessons}
            downloads_by_lesson: dict = {}
            for c in all_content:
                sid = c.get('session_id', '')
                lid = session_to_lesson.get(sid, '')
                lname = lesson_id_to_name.get(lid, '')
                if lname:
                    downloads_by_lesson[lname] = downloads_by_lesson.get(lname, 0) + c.get('downloads', 0)
            if downloads_by_lesson:
                top_lesson = max(downloads_by_lesson, key=downloads_by_lesson.get)
        except Exception as e:
            logger.debug(f"weekly_report_stats top_lesson error: {e}")

        open_tickets   = await self.tickets.count_documents({'status': 'open'})
        closed_week    = await self.tickets.count_documents(
            {'status': 'closed', 'closed_at': {'$gte': week_ago}}
        )
        total_tickets_week = await self.tickets.count_documents(
            {'created_at': {'$gte': week_ago}}
        )

        # کاربرانی که بیش از ۱۴ روز فعالیت نداشتند (احتمال غیرفعال شدن)
        inactive_cutoff = (datetime.now() - timedelta(days=14)).isoformat()
        all_appr = await self.users.find({'approved': True}).to_list(length=None)
        inactive_count = 0
        for u in all_appr:
            last = u.get('last_active', u.get('registered_at', ''))
            if last < inactive_cutoff:
                inactive_count += 1

        return {
            'new_users':          new_users,
            'active_users_count': len(set(active_users)),
            'top_lesson':         top_lesson or 'داده‌ای نیست',
            'open_tickets':       open_tickets,
            'closed_week':        closed_week,
            'total_tickets_week': total_tickets_week,
            'inactive_count':     inactive_count,
            'total_users':        await self.users.count_documents({'approved': True}),
        }


    # ══════════════════════════════════════════════════
    #  FIX جدید: لاگ وضعیت ارسال نوتیف‌ها (notif_runs)
    #  برای رفع نیاز: «بدون تکرار، بدون نقص، قابل retry،
    #  وضعیت ارسال در دیتابیس ذخیره شود»
    # ══════════════════════════════════════════════════

    # ══════════════════════════════════════════════════
    #  🔔 صندوق اعلان کاربر (مرکز اعلان مینی‌اپ) — موج ۴.۹۰
    #  قرارداد مرکزی: همه‌ی نویسنده‌ها (جاب‌های ربات، پنل‌های وب/بات)
    #  رویداد را با همین ساختار ثبت می‌کنند؛ مینی‌اپ فقط می‌خواند.
    #  body متنِ ساده (بدون HTML) است تا در هر سطحی امن نمایش داده شود.
    # ══════════════════════════════════════════════════


    # ══════════════════════════════════════════════════
    #  🧠 موج N1 — Notification Spine (منبع واحد رویدادها)
    #  هر ntype اینجا meta کامل دارد: دسته، آیکون، تُن،
    #  اولویت و کلید ترجیح کاربر. بات / API / FE فقط
    #  از همین ثبت‌نامه می‌خوانند — منطق موازی ممنوع.
    # ══════════════════════════════════════════════════

    # کاتالوگ دسته‌های ترجیح کاربر — (key, label, desc, default)
    # این لیست هم در صفحه‌ی مینی‌اپ هم در منوی بات نمایش می‌یابد.
    NOTIF_CATALOG = [
        ('resources',    '📚 منابع و جزوه‌ها',      'فایل‌های درسی علوم پایه و جزوه‌ها',           True),
        ('references',   '📖 رفرنس‌ها',             'آپدیت کتاب‌ها و خواندنی‌های رفرنس',            True),
        ('basic_sci',    '🩺 علوم پایه',            'جلسات و محتوای درس‌های علوم پایه',             True),
        ('qbank',        '❓ بانک سؤال',             'سؤال روزانه و وضعیت سؤال‌های پیشنهادی‌ات',    True),
        ('schedule',     '📅 برنامه‌ی هفتگی',       'کلاس جدید، جبرانی و تغییر زمان',               True),
        ('exams',        '📝 امتحان‌ها',            'یادآوری‌های رسمی امتحان',                      True),
        ('grades',       '📊 نمرات',                 'ثبت نمره‌ی جدید در کارنامه',                  True),
        ('tickets',      '🎫 پشتیبانی و تیکت',       'پاسخ‌ها و وضعیت گفت‌وگوی پشتیبانی',          True),
        ('subscription', '💳 اشتراک',                'فعال‌سازی، یادآوری پایان و وضعیت رسید',       True),
        ('discounts',    '🎁 تخفیف‌ها',              'پیشنهادها و کدهای تخفیف',                     True),
        ('ai',           '🤖 هوشیار',                'رویدادهای دستیار هوشمند',                     True),
        ('announcement', '📢 اطلاعیه‌ها',            'خبرها، پیام‌های آموزشی و اطلاعیه‌ها',         True),
        ('polls',        '🗳 نظرسنجی',               'نظرسنجی‌های رسمی',                            True),
        ('gamification', '🎮 بازی‌واری و رنک',       'ارتقای رنک/دیویژن، نشان‌ها و رقابت',          True),
        ('profile',      '👤 حساب',                  'تأیید حساب و رویدادهای پروفایل',              True),
        ('system',       '⚙️ سیستم',                 'سایر رویدادهای حساس حساب',                    True),
    ]

    # ntype → (category, icon, tone, priority, pref_key|None)
    # pref_key=None ⇒ مهار ترجیحی ندارد (همیشه DM هم می‌رود)
    NOTIF_TYPES = {
        # ── مدرسی/آموزشی ──
        'exam_reminder':    ('exams',        '📝', 'red',    'normal',   'exams'),
        'exam':             ('exams',        '📝', 'red',    'normal',   'exams'),
        'daily_question':   ('qbank',        '🧪', 'purple', 'low',      'qbank'),
        'new_resources':    ('resources',    '📚', 'green',  'normal',   'resources'),
        'new_references':   ('references',   '📖', 'purple', 'normal',   'references'),
        'new_basic_sci':    ('basic_sci',    '🩺', 'acc',    'normal',   'basic_sci'),
        'class':            ('schedule',     '🏫', 'blue',   'normal',   'schedule'),
        'makeup':           ('schedule',     '🔄', 'yellow', 'normal',   'schedule'),
        'schedule_change':  ('schedule',     '🔄', 'yellow', 'high',     'schedule'),
        'grade':            ('grades',       '📊', 'acc',    'critical', 'grades'),
        # ── پشتیبانی/اشتراک ──
        'ticket_created':   ('tickets',      '🎫', 'green',  'normal',   'tickets'),
        'ticket_reply':     ('tickets',      '📨', 'green',  'critical', 'tickets'),
        'ticket_closed':    ('tickets',      '✅', 'green',  'normal',   'tickets'),
        'ticket_reopened':  ('tickets',      '🔓', 'yellow', 'normal',   'tickets'),
        'sub_activated':    ('subscription', '💎', 'acc',    'critical', 'subscription'),
        'sub_expiring':     ('subscription', '⏳', 'yellow', 'high',     'subscription'),
        'sub_expired':      ('subscription', '⌛', 'red',    'critical', 'subscription'),
        'payment_rejected': ('subscription', '❌', 'red',    'high',     'subscription'),
        # ── حساب/اعلامیه ──
        'account':          ('profile',      '🎓', 'green',  'high',     'profile'),
        # 🎁 موج D1 — کمپین‌های تخفیف: دسته‌ی مجزا + مهار ترجیحی «تخفیف‌ها»
        'discount':         ('discounts',    '🎁', 'acc',    'normal',   'discounts'),
        'admin_dm':         ('announcement', '📩', 'blue',   'high',     'announcement'),
        'announcement':     ('announcement', '📢', 'blue',   'normal',   'announcement'),
        'edu_message':      ('announcement', '🎓', 'acc',    'low',      'announcement'),
        'general':          ('announcement', '🔔', 'blue',   'normal',   'announcement'),
        'question_approved':('qbank',        '✍️', 'green',  'high',     'qbank'),
        'question_rejected':('qbank',        '❕', 'yellow', 'normal',   'qbank'),
        'report_resolved':  ('announcement', '🩺', 'green',  'normal',   'announcement'),
        # ── خانواده‌ی پرستیژ (دسته‌ی واحد: gamification) ──
        'rank_up':          ('gamification', '🎉', 'acc',    'high',     'gamification'),
        'div_up':           ('gamification', '⭐', 'acc',    'normal',   'gamification'),
        'streak':           ('gamification', '🔥', 'red',    'low',      'gamification'),
        'demote':           ('gamification', '📉', 'yellow', 'normal',   'gamification'),
        'return':           ('gamification', '🫶', 'green',  'low',      'gamification'),
        'founder':          ('gamification', '🏛️', 'acc',    'high',     'gamification'),
        'achievement':      ('gamification', '🏅', 'purple', 'normal',   'gamification'),
        'global_first':     ('gamification', '🏆', 'yellow', 'high',     'gamification'),
        'weekly_champion':  ('gamification', '👑', 'yellow', 'high',     'gamification'),
        'challenge':        ('gamification', '⚔️', 'red',    'normal',   'gamification'),
        'challenge_win':    ('gamification', '⚔️', 'green',  'high',     'gamification'),
        'challenge_fail':   ('gamification', '💪', 'yellow', 'normal',   'gamification'),
    }

    _NOTIF_META_FALLBACK = ('system', '🔔', 'blue', 'normal', 'general')

    _INBOX_GROUP_WINDOW_H = 72   # پنجره‌ی Smart Grouping

    def notif_type_meta(self, ntype: str) -> dict:
        """♻️ meta کامل یک ntype — خروجی ثابت-شکل حتی برای نوع ناشناخته"""
        cat, icon, tone, prio, pref = self.NOTIF_TYPES.get(
            ntype, self._NOTIF_META_FALLBACK)
        return {'category': cat, 'icon': icon, 'tone': tone,
                'priority': prio, 'pref': pref}

    async def notif_catalog(self) -> list:
        """📋 فهرست دسته‌ها برای صفحه‌ی ترجیحات (همراه پیش‌فرض جاری پنل)"""
        defaults = await self.get_notif_defaults()
        return [{'key': k, 'label': l, 'desc': d,
                 'default': bool(defaults.get(k, d))}
                for k, l, d, _default in self.NOTIF_CATALOG]

    def notif_pref_on(self, settings: dict, key, defaults: dict = None) -> bool:
        """🎚 آیا این دسته برای کاربر روشن است؟ (کلید قدیمی خودکار canonical می‌شود)

        key=None یعنی نوتیف مهار ندارد ⇒ همیشه True (Critical مسیر)."""
        if key is None:
            return True
        canon = self.PREF_ALIAS.get(key, key)
        if canon is None:
            return True
        settings = settings or {}
        if canon in settings:
            return bool(settings[canon])
        if key in settings:          # مقدار قدیمی دقیق ذخیره‌شده
            return bool(settings[key])
        base = defaults or {}
        if canon in base:
            return bool(base[canon])
        return bool(base.get(key, True))

    _INBOX_KEEP = 100  # سقف نگه‌داری اعلان برای هر کاربر

    async def inbox_add(self, user_id: int, ntype: str, title: str,
                        body: str, link: str = None, *, payload: dict = None,
                        group_key: str = None, group_title: str = None) -> None:
        """ثبت یک اعلان برای یک کاربر + هرسِ نگه‌داری (قدیمی‌تر از KEEP)

        🧠 موج N1 — اسکیمای غنی (category/icon/tone/priority/pinned/count)
        از ثبت‌نامه خوانده می‌شود، اما فیلدهای پایه سازگار-عقبرو می‌مانند.
        group_key ⇒ Smart Grouping: اگر سند باز هم‌کلید در پنجره‌ی اخیر
        باشد، به‌جای درج جدید همان تقویت می‌شود (count+۱، متن تازه،
        خوانده‌نشده مجدد) — الگوی «۳ منبع جدید به جای ۳ اعلان»."""
        try:
            uid = int(user_id)
            meta = self.notif_type_meta(ntype)
            now_iso = datetime.now().isoformat()

            # ♻ Smart Grouping — ادغام در سند باز هم‌کلید
            if group_key:
                cutoff = (datetime.now() - timedelta(
                    hours=self._INBOX_GROUP_WINDOW_H)).isoformat()
                prev = await self.user_notifs.find_one({
                    'user_id': uid, 'group_key': group_key,
                    'created_at': {'$gte': cutoff}})
                if prev:
                    cnt = int(prev.get('count') or 1) + 1
                    if group_title:
                        new_title = group_title.format(count=cnt)[:160]
                    elif '{count}' in title:
                        new_title = title.format(count=cnt)[:160]
                    else:
                        new_title = str(title)[:160]
                    await self.user_notifs.update_one({'_id': prev['_id']}, {
                        '$set': {
                            'type': ntype, 'title': new_title,
                            'body': str(body)[:900],
                            'link': link or prev.get('link'),
                            'category': meta['category'],
                            'icon': meta['icon'], 'tone': meta['tone'],
                            'priority': meta['priority'],
                            'read': False, 'created_at': now_iso,
                        },
                        '$inc': {'count': 1},
                    })
                    await self._inbox_prune(uid)
                    return

            await self.user_notifs.insert_one({
                'user_id':    uid,
                'type':       ntype,
                'title':      str(title)[:160],
                'body':       str(body)[:900],
                'link':       link or None,
                # 🧠 فیلدهای غنی — FE برای فیلتر/اولویت/pin از آن‌ها می‌خواند
                'category':   meta['category'],
                'icon':       meta['icon'],
                'tone':       meta['tone'],
                'priority':   meta['priority'],
                'pinned':     False,
                'count':      1,
                'payload':    payload or None,
                'group_key':  group_key or None,
                'read':       False,
                'created_at': now_iso,
            })
            await self._inbox_prune(uid)
        except Exception as e:
            # اعلان نباید مسیر اصلی رویداد (ارسال/ثبت) را بشکند
            logger.warning(f"inbox_add failed for {user_id}: {e}")

    async def _inbox_prune(self, uid: int) -> None:
        """🧹 هرس محافظ — قدیمی‌تر از سقف KEEP حذف می‌شود (سندی که
        pinned است، هرگز هرس نمی‌شود تا کاربر بتواند مهم‌ها را سنجاق کند)"""
        try:
            count = await self.user_notifs.count_documents({'user_id': int(uid)})
            if count > self._INBOX_KEEP:
                old = self.user_notifs.find(
                    {'user_id': int(uid), 'pinned': {'$ne': True}}
                ).sort('created_at', -1).skip(self._INBOX_KEEP).limit(200)
                old_ids = [d['_id'] async for d in old]
                if old_ids:
                    await self.user_notifs.delete_many({'_id': {'$in': old_ids}})
        except Exception:
            pass


    async def notify_user(self, uid, ntype: str, *, title: str, body: str,
                          link: str = None, dm: str = None,
                          payload: dict = None, group_key: str = None,
                          group_title: str = None) -> dict:
        """🧠 موج N1 — Entry واحد رویدادهای کاربرمحور.

        یک فراخوانی ⇒ دو مسیر همگام (Source of Truth = Inbox):
          ۱) ثبت کامل در Inbox (همیشه — آرشیو به‌ترتیب-categorised،
             با meta ثابت و قابلیت pin/group/count).
          ۲) اگر dm داده شود: قرار در صف DM ربات (با WebApp Deep Link
             خودکار از سوی job مصرف‌کننده)... مگر ترجیح کاربر دسته را
             خاموش کرده باشد (Criticalها هرگز مهار نمی‌شوند).

        برمی‌گرداند {'inbox': True, 'dm': bool} تا تست/جیاب رفتار را پایش کند."""
        uid = int(uid)
        meta = self.notif_type_meta(ntype)
        await self.inbox_add(uid, ntype, title, body, link,
                             payload=payload, group_key=group_key,
                             group_title=group_title)

        dm_queued = False
        if dm is not None:
            allowed = True
            pref = meta['pref']
            if pref and meta['priority'] != 'critical':
                try:
                    user = await self.get_user(uid)
                    settings = (user or {}).get('notification_settings', {})
                    defaults = await self.get_notif_defaults()
                    allowed = self.notif_pref_on(settings, pref, defaults)
                except Exception:
                    allowed = True
            if allowed:
                try:
                    await self.bot_notifs.insert_one({
                        'type':       f'event:{ntype}',
                        'chat_id':    uid,
                        'text':       dm,
                        'link':       link or None,  # 🧩 ⇒ دکمه‌ی WebApp
                        'sent':       False,
                        'created_at': datetime.now().isoformat(),
                    })
                    dm_queued = True
                except Exception as e:
                    # صف DM اشکال بخورد، آرشیو Inbox کماکان کامل است
                    logger.warning(f"notify_user dm queue failed for {uid}: {e}")
        return {'inbox': True, 'dm': dm_queued}

    async def inbox_add_many(self, docs: list) -> None:
        """درج گروهی برای اعلان‌های همگانی (هر دیکت: user_id/type/title/body/link)"""
        if not docs:
            return
        try:
            now_iso = datetime.now().isoformat()
            rows = []
            for d in docs:
                meta = self.notif_type_meta(d['type'])
                rows.append({
                    'user_id':    int(d['user_id']),
                    'type':       d['type'],
                    'title':      str(d['title'])[:160],
                    'body':       str(d.get('body', ''))[:900],
                    'link':       d.get('link') or None,
                    'category':   meta['category'],
                    'icon':       meta['icon'],
                    'tone':       meta['tone'],
                    'priority':   meta['priority'],
                    'pinned':     False,
                    'count':      1,
                    'payload':    d.get('payload') or None,
                    'group_key':  d.get('group_key') or None,
                    'read':       False,
                    'created_at': now_iso,
                })
            # تکه‌تکه تا سقف BSON معقول رعایت شود
            for i in range(0, len(rows), 500):
                await self.user_notifs.insert_many(rows[i:i + 500], ordered=False)
        except Exception as e:
            logger.warning(f"inbox_add_many failed ({len(docs)} docs): {e}")

    async def inbox_list(self, user_id: int, limit: int = 60,
                         category: str = None, q: str = None,
                         unread_only: bool = False) -> dict:
        """فهرست اعلان‌های کاربر + شمارش خوانده‌نشده (یک پاسخ برای صفحه و بج)

        🧠 موج N1 — خروجی غنی (category/icon/tone/priority/pinned/count)
        با سازگاری کامل (کلیدهای قدیمی دست‌نخورده) + فیلتر اختیاری
        category/q/unread که هم کلاینت هم سرور می‌تواند بدهد. ترتیب:
        پین‌شده‌ها بالاتر، سپس جدیدترین."""
        uid = int(user_id)
        cursor = (self.user_notifs.find({'user_id': uid})
                  .sort('created_at', -1).limit(400))
        need_q = (q or '').strip().lower()
        items = []
        async for d in cursor:
            meta = self.notif_type_meta(d.get('type', 'general'))
            item = {
                'id':         str(d['_id']),
                'type':       d.get('type', 'general'),
                'title':      d.get('title', ''),
                'body':       d.get('body', ''),
                'link':       d.get('link'),
                'read':       bool(d.get('read', False)),
                'created_at': d.get('created_at', ''),
                # 🧠 فیلدهای غنی — نقص اسناد قدیمی با registry پر می‌شود
                'category':   d.get('category') or meta['category'],
                'icon':       d.get('icon') or meta['icon'],
                'tone':       d.get('tone') or meta['tone'],
                'priority':   d.get('priority') or meta['priority'],
                'pinned':     bool(d.get('pinned', False)),
                'count':      int(d.get('count') or 1),
            }
            if category and item['category'] != category:
                continue
            if unread_only and item['read']:
                continue
            if need_q and need_q not in (
                    (item['title'] + ' ' + item['body']).lower()):
                continue
            items.append(item)
        items.sort(key=lambda i: i['created_at'], reverse=True)
        # 📌 پین‌شده‌ها مطلقاً بالای لیست (دسته‌ی زمانی در FE گروه‌بندی می‌شود)
        pinned   = [i for i in items if i['pinned']]
        unpinned = [i for i in items if not i['pinned']]
        items = (pinned + unpinned)[:limit]
        unread = await self.user_notifs.count_documents({'user_id': uid, 'read': False})
        return {'items': items, 'unread': unread}

    async def inbox_unread_count(self, user_id: int) -> int:
        """🔢 شمارش سبک خوانده‌نشده (بدون لفظ آیتم‌ها) — برای بج سبک"""
        try:
            return await self.user_notifs.count_documents(
                {'user_id': int(user_id), 'read': False})
        except Exception:
            return 0

    async def inbox_pin(self, user_id: int, nid: str, pinned: bool) -> bool:
        """📌 سنجاق کردن یک اعلان (پین‌شده‌ها بالاتر و مصون از هرس)"""
        try:
            r = await self.user_notifs.update_one(
                {'_id': ObjectId(str(nid)), 'user_id': int(user_id)},
                {'$set': {'pinned': bool(pinned)}})
            return bool(getattr(r, 'modified_count', 0) or
                        getattr(r, 'matched_count', 0))
        except Exception:
            return False

    async def inbox_mark_read(self, user_id: int, ids: list = None) -> int:
        """علامت خوانده‌شدن — ids=None یعنی همه؛ خروجی: شمارش خوانده‌نشده‌ی باقی‌مانده"""
        uid = int(user_id)
        flt = {'user_id': uid, 'read': False}
        if ids:
            obj_ids = []
            for x in ids:
                try:
                    obj_ids.append(ObjectId(str(x)))
                except Exception:
                    pass
            if not obj_ids:
                return await self.user_notifs.count_documents({'user_id': uid, 'read': False})
            flt['_id'] = {'$in': obj_ids}
        await self.user_notifs.update_many(flt, {'$set': {'read': True}})
        return await self.user_notifs.count_documents({'user_id': uid, 'read': False})

    async def inbox_delete(self, user_id: int, nid: str) -> bool:
        """حذف یک اعلانِ خودِ کاربر (مالکیت با user_id تضمین می‌شود)"""
        try:
            r = await self.user_notifs.delete_one({
                '_id': ObjectId(str(nid)), 'user_id': int(user_id)})
            return r.deleted_count > 0
        except Exception:
            return False

    async def notif_run_start(self, job_name: str) -> str:
        """ثبت شروع یک اجرای job — برمی‌گرداند run_id برای ادامه ثبت"""
        r = await self.notif_runs.insert_one({
            'job_name':  job_name,
            'started_at': datetime.now().isoformat(),
            'status':    'running',
            'sent':      0,
            'failed':    0,
            'total':     0,
            'finished_at': None,
        })
        return str(r.inserted_id)

    async def notif_run_finish(self, run_id: str, sent: int, failed: int, total: int,
                                status: str = 'completed', error: str = ''):
        try:
            await self.notif_runs.update_one(
                {'_id': ObjectId(run_id)},
                {'$set': {
                    'sent': sent, 'failed': failed, 'total': total,
                    'status': status, 'error': error,
                    'finished_at': datetime.now().isoformat(),
                }}
            )
        except Exception:
            pass

    async def get_recent_notif_runs(self, job_name: str = None, limit: int = 15) -> list:
        q = {'job_name': job_name} if job_name else {}
        return await self.notif_runs.find(q).sort('started_at', -1).to_list(limit)

    async def get_failed_notif_targets(self, run_id: str) -> list:
        """کاربرانی که ارسال برایشان fail شده — برای retry دستی"""
        doc = await self.notif_runs.find_one({'_id': ObjectId(run_id)})
        return doc.get('failed_user_ids', []) if doc else []

    async def notif_run_add_failed(self, run_id: str, user_ids: list):
        try:
            await self.notif_runs.update_one(
                {'_id': ObjectId(run_id)},
                {'$set': {'failed_user_ids': user_ids}}
            )
        except Exception:
            pass

    async def notif_run_add_failed_detailed(self, run_id: str, records: list):
        """
        FIX جدید: برای job هایی که در یک اجرا چند پیام متفاوت
        می‌فرستند (مثل یادآوری چند امتحان مختلف در یک اجرا)، هر کاربر
        ناموفق به‌همراه متن دقیق همان پیامی که برایش در نظر گرفته شده
        بود ذخیره می‌شود — نه فقط آیدی خام — تا «تلاش مجدد» بتواند
        محتوای درست را برایش بفرستد (نه یک پیام کلی جایگزین).
        records: [{'user_id': int, 'message': str}, ...]
        """
        try:
            await self.notif_runs.update_one(
                {'_id': ObjectId(run_id)},
                {'$set': {
                    'failed_user_ids': [r['user_id'] for r in records],
                    'failed_targets_detailed': records,
                }}
            )
        except Exception:
            pass

    async def get_failed_notif_details(self, run_id: str) -> list:
        """
        برمی‌گرداند [{'user_id':, 'message':}] برای retry دقیق.
        اگر جزئیات هر کاربر جداگانه ذخیره نشده باشد (job‌های تک‌پیامی
        مثل سوال روزانه/منابع جدید)، از متن عمومی ذخیره‌شده‌ی همان
        اجرا (notif_run_set_message) برای همه‌ی آیدی‌های ناموفق
        استفاده می‌شود.
        """
        try:
            doc = await self.notif_runs.find_one({'_id': ObjectId(run_id)})
        except Exception:
            return []
        if not doc:
            return []
        detailed = doc.get('failed_targets_detailed')
        if detailed:
            return detailed
        ids = doc.get('failed_user_ids', [])
        msg = doc.get('message_text')
        if ids and msg:
            return [{'user_id': uid, 'message': msg} for uid in ids]
        return []

    async def notif_run_set_message(self, run_id: str, text: str, parse_mode: str = 'HTML'):
        """
        FIX مهم: این متد قبلاً خط تعریفش (async def) به‌طور کامل از کد
        حذف شده بود — بدنه‌اش به‌عنوان کد مرده زیر get_failed_notif_details
        باقی مونده بود، پس هیچوقت واقعاً روی کلاس DB تعریف نمی‌شد و هر
        بار new_resources_notif_job صداش می‌زد با
        AttributeError: 'DB' object has no attribute 'notif_run_set_message'
        کرش می‌کرد و کل نوتیف منابع جدید لغو می‌شد.
        ذخیره‌ی متن واقعی پیامی که در این اجرا ارسال شده — تا دکمه‌ی
        «تلاش مجدد» در پنل ادمین بتواند همان محتوای واقعی (نه یک پیام
        کلی جایگزین) را دوباره برای کاربران fail‌شده بفرستد.
        """
        try:
            await self.notif_runs.update_one(
                {'_id': ObjectId(run_id)},
                {'$set': {'message_text': text, 'message_parse_mode': parse_mode}}
            )
        except Exception:
            pass

    async def get_notif_run_message(self, run_id: str) -> dict:
        """برمی‌گرداند {'text':..., 'parse_mode':...} یا None اگر ذخیره نشده باشد"""
        try:
            doc = await self.notif_runs.find_one({'_id': ObjectId(run_id)})
        except Exception:
            return None
        if not doc or not doc.get('message_text'):
            return None
        return {'text': doc['message_text'], 'parse_mode': doc.get('message_parse_mode', 'HTML')}


    # ══════════════════════════════════════════════════
    #  FIX جدید: سیستم گزارش ایراد سوال/جزوه (content_reports)
    # ══════════════════════════════════════════════════

    REPORT_REASONS = {
        'wrong_answer':  'پاسخ اشتباه',
        'wrong_option':  'گزینه اشتباه',
        'incomplete':    'متن ناقص',
        'broken_file':   'فایل خراب',
        'outdated':      'محتوای قدیمی',
        'other':         'سایر',
    }

    async def create_content_report(self, target_type: str, target_id: str,
                                     reporter_id: int, reporter_name: str,
                                     reason: str, note: str = '',
                                     designer_id: int = None) -> int:
        """
        ثبت گزارش جدید — target_type: 'question' یا 'resource'.
        designer_id: آیدی طراح سوال (اگه target سوال باشد) برای اطلاع‌رسانی مستقیم.
        """
        count = await self.content_reports.count_documents({})
        report_id = count + 1
        await self.content_reports.insert_one({
            'report_id':    report_id,
            'target_type':  target_type,
            'target_id':    target_id,
            'reporter_id':  reporter_id,
            'reporter_name': reporter_name,
            'reason':       reason,
            'note':         note,
            'designer_id':  designer_id,
            'status':       'new',   # new, reviewing, resolved, rejected
            'created_at':   datetime.now().isoformat(),
            'resolved_at':  None,
            'resolved_by':  None,
        })
        return report_id

    async def get_content_report(self, report_id: int):
        return await self.content_reports.find_one({'report_id': report_id})

    async def get_content_reports(self, status: str = None, limit: int = 50) -> list:
        q = {'status': status} if status else {}
        return await self.content_reports.find(q).sort('created_at', -1).to_list(limit)

    async def update_report_status(self, report_id: int, status: str, resolved_by: int = None):
        prev = None
        try:
            prev = await self.content_reports.find_one({'report_id': report_id})
        except Exception:
            pass
        update_data = {'status': status}
        if status in ('resolved', 'rejected'):
            update_data['resolved_at'] = datetime.now().isoformat()
            update_data['resolved_by'] = resolved_by
        await self.content_reports.update_one(
            {'report_id': report_id}, {'$set': update_data}
        )
        # 👑 P1 — اولین گذار به resolved ⇒ پاداش «گزارش مفید» به گزارش‌دهنده
        # 🧠 N1.2 — سینک‌فیکس: گزارش‌دهنده هیچ‌جا نمی‌فهمید گزارشش بررسی
        # شده؛ حالا تک‌منبع زنده (Inbox + DM + Deep Link به «گزارش‌های من»).
        try:
            if (status == 'resolved'
                    and (prev or {}).get('status') != 'resolved'
                    and (prev or {}).get('reporter_id')):
                rep_uid = int(prev['reporter_id'])
                await self.prestige_event(rep_uid,
                    'report_useful', {'report_id': report_id})
        except Exception:
            pass
        # 🧠 N1.2 — خبر در try جدا (ایزوله از موتور پرستیژ)
        try:
            if (status == 'resolved'
                    and (prev or {}).get('status') != 'resolved'
                    and (prev or {}).get('reporter_id')):
                rep_uid = int(prev['reporter_id'])
                await self.notify_user(rep_uid, 'report_resolved',
                    title='🩺 گزارشت بررسی شد',
                    body='گزارش محتوایی که فرستادی بررسی و تأیید شد '
                         '— چشم‌بازای حسرت ممنونه 🙏',
                    link='/me/reports',
                    dm=('🩺 <b>گزارشت بررسی شد</b>\n\n'
                        'گزارش محتوایی که فرستادی بررسی و تأیید شد. '
                        'از وسواس مثبتی که داری مرسی 🙏'))
        except Exception:
            pass

    async def get_reviewers(self) -> list:
        """همه کاربرانی که نقش reviewer (خرخون) دارند"""
        docs = await self.admin_roles.find({'role': 'reviewer'}).to_list(100)
        return [d['_id'] for d in docs]

    async def content_reports_stats(self) -> dict:
        new_count       = await self.content_reports.count_documents({'status': 'new'})
        reviewing_count = await self.content_reports.count_documents({'status': 'reviewing'})
        resolved_count  = await self.content_reports.count_documents({'status': 'resolved'})
        rejected_count  = await self.content_reports.count_documents({'status': 'rejected'})
        return {
            'new': new_count, 'reviewing': reviewing_count,
            'resolved': resolved_count, 'rejected': rejected_count,
        }


    # ══════════════════════════════════════════════════
    #  FIX جدید: قفل اجباری عضویت کانال (Force Subscribe)
    # ══════════════════════════════════════════════════

    async def get_required_channels(self) -> list:
        """لیست کانال‌هایی که عضویت در آن‌ها برای استفاده از ربات اجباری است"""
        doc = await self.settings.find_one({'_id': 'global'})
        return (doc or {}).get('required_channels', [])

    async def add_required_channel(self, channel_id: str, channel_title: str, invite_link: str = ''):
        channels = await self.get_required_channels()
        if any(c['id'] == channel_id for c in channels):
            return False
        channels.append({'id': channel_id, 'title': channel_title, 'invite_link': invite_link})
        await self.set_setting('required_channels', channels)
        return True

    async def remove_required_channel(self, channel_id: str):
        channels = await self.get_required_channels()
        channels = [c for c in channels if c['id'] != channel_id]
        await self.set_setting('required_channels', channels)


    # ══════════════════════════════════════════════════
    #  FIX جدید: تنظیمات پیش‌فرض اعلان‌ها برای کاربران جدید
    # ══════════════════════════════════════════════════

    DEFAULT_NOTIF_FALLBACK = {
        # 🧠 موج N1 — کاتالوگ یکپارچه‌ی دسته‌ها (کلیدهای Canonical)
        'resources': True, 'references': True, 'basic_sci': True,
        'qbank': True, 'schedule': True, 'exams': True, 'grades': True,
        'tickets': True, 'subscription': True, 'discounts': True,
        'ai': True, 'announcement': True, 'polls': True, 'profile': True,
        'gamification': True, 'system': True,
        # کلیدهای قدیمی (سازگاری — همان معنا، نگاشتی از طریق PREF_ALIAS)
        'new_resources': True, 'schedule_old_guard': None,
        'exam': True, 'makeup': True,
        'daily_question': False, 'edu_message': True, 'general': True,
        'grade_release': True, 'sub_expiry': True,
    }

    # 🧠 موج N1 — canonical کردن کلیدهای قدیمی ترجیح به دسته‌های جدید؛
    # هر جا pref خوانده/نوشته شود، از همین نگاشت عبور می‌کند تا کاربران
    # قدیمی با سندهای فعلی بدون مهاجرت دستی به دسته‌های تازه برسند.
    PREF_ALIAS = {
        'new_resources': 'resources',
        'exam':          'exams',
        'makeup':        'schedule',
        'daily_question': 'qbank',
        'edu_message':   'announcement',
        'general':       'announcement',
        'grade_release': 'grades',
        'sub_expiry':    'subscription',
        'schedule_old_guard': None,
    }

    async def get_notif_defaults(self) -> dict:
        """
        مقادیر پیش‌فرض فعلی اعلان‌ها — قابل تغییر از پنل ادمین.
        کاربران تازه ثبت‌نام‌شده همین مقادیر را به ارث می‌برند.
        """
        saved = await self.get_setting('notif_defaults', None)
        if saved is None:
            return dict(self.DEFAULT_NOTIF_FALLBACK)
        # ترکیب با fallback برای کلیدهای جدیدی که ممکن است بعداً اضافه شوند
        merged = dict(self.DEFAULT_NOTIF_FALLBACK)
        merged.update(saved)
        return merged

    async def set_notif_default(self, ntype: str, value: bool):
        defaults = await self.get_notif_defaults()
        defaults[ntype] = value
        await self.set_setting('notif_defaults', defaults)

    async def mark_user_blocked(self, uid: int, blocked: bool = True):
        """
        FIX (ارسال همگانی حرفه‌ای‌تر): وقتی ارسال پیام به کاربری با خطای
        Forbidden (کاربر ربات را بلاک کرده) مواجه می‌شود، این پرچم را
        ذخیره می‌کنیم — هم برای گزارش دقیق‌تر ارسال همگانی، هم برای
        اینکه دفعات بعد بلافاصله این کاربر را در آمار «مسدود» بشماریم.
        """
        try:
            await self.users.update_one(
                {'user_id': uid},
                {'$set': {'blocked_bot': blocked,
                          'blocked_bot_at': datetime.now().isoformat()}}
            )
        except Exception:
            pass

    async def apply_notif_default_to_all_users(self, ntype: str, value: bool) -> int:
        """
        FIX (بخش سوم): وقتی ادمین یک تنظیم پیش‌فرض اعلان را تغییر می‌دهد،
        باید همان لحظه روی تمام کاربران (قدیمی و جدید، فعال و غیرفعال)
        اعمال شود — نه فقط روی کاربران تازه ثبت‌نامی.
        قبلاً چون هر کاربر هنگام ثبت‌نام یک کپی صریح از دیکشنری
        notification_settings می‌گرفت، تغییر بعدیِ پیش‌فرض هرگز به
        کاربران قبلی نمی‌رسید (چون s.get(key, ...) همیشه مقدار صریح
        قدیمی را برمی‌گرداند، نه پیش‌فرض جدید را).
        این متد با یک UPDATE سراسری، مقدار را برای همه کاربران هم‌زمان
        بازنویسی می‌کند.
        """
        try:
            result = await self.users.update_many(
                {}, {'$set': {f'notification_settings.{ntype}': value}}
            )
            return result.modified_count
        except Exception:
            logger.exception('apply_notif_default_to_all_users failed')
            return 0


    async def count_active_users(self, minutes: int = 30) -> int:
        """
        FIX جدید: تعداد کاربرانی که در N دقیقه اخیر فعالیتی داشته‌اند —
        برای نمایش «کاربران آنلاین تقریبی» در وضعیت ربات استفاده می‌شود.
        """
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        return await self.users.count_documents({'last_active': {'$gte': cutoff}})

    async def count_active_users_today(self) -> int:
        """تعداد کاربرانی که امروز (به وقت تهران) حداقل یک‌بار فعالیت داشته‌اند"""
        from utils import today_start_utc_str
        today_start = today_start_utc_str()
        return await self.users.count_documents({'last_active': {'$gte': today_start}})

    # ══════════════════════════════════════════════════════════════
    #  💳 سیستم اشتراک — FIX جدید
    #  پلن‌ها (چندتایی) + وضعیت هر کاربر + صف رسیدها + کدهای تخفیف
    # ══════════════════════════════════════════════════════════════

    # ── پلن‌ها ──
    async def sub_plan_add(self, name: str, days: int, price: int) -> str:
        count = await self.sub_plans.count_documents({})
        r = await self.sub_plans.insert_one({
            'name': name, 'days': days, 'price': price,
            'active': True, 'order': count,
            'created_at': datetime.now().isoformat(),
        })
        return str(r.inserted_id)

    async def sub_plan_list(self, only_active: bool = False) -> list:
        q = {'active': True} if only_active else {}
        return await self.sub_plans.find(q).sort('order', 1).to_list(50)

    async def sub_plan_get(self, plan_id: str):
        try:
            return await self.sub_plans.find_one({'_id': ObjectId(plan_id)})
        except Exception:
            return None

    async def sub_plan_update(self, plan_id: str, data: dict) -> bool:
        try:
            await self.sub_plans.update_one({'_id': ObjectId(plan_id)}, {'$set': data})
            return True
        except Exception:
            return False

    async def sub_plan_toggle(self, plan_id: str) -> bool:
        p = await self.sub_plan_get(plan_id)
        if not p:
            return False
        await self.sub_plans.update_one(
            {'_id': ObjectId(plan_id)}, {'$set': {'active': not p.get('active', True)}}
        )
        return True

    async def sub_plan_delete(self, plan_id: str):
        try:
            await self.sub_plans.delete_one({'_id': ObjectId(plan_id)})
        except Exception:
            pass

    # ── کدهای تخفیف ──
    async def discount_add(self, code: str, percent: int, max_uses: int = 0,
                            expires_at: str = None, created_by: int = 0,
                            target_plan_ids: list = None, per_user_limit: int = 0) -> bool:
        code = code.strip().upper()
        if await self.discount_codes.find_one({'code': code}):
            return False
        await self.discount_codes.insert_one({
            'code': code, 'percent': max(1, min(100, percent)),
            'max_uses': max_uses, 'used_count': 0,
            'expires_at': expires_at, 'active': True,
            # 🎟 موج D1 — [] یا None یعنی همه‌ی پلن‌های فعال؛
            # غیرخالی یعنی فقط همان plan_idها
            'target_plan_ids': [str(p) for p in (target_plan_ids or [])],
            # 0 = نامحدود؛ N = هر کاربر حداکثر N بار (پنیر discount_uses اتمیک)
            'per_user_limit': max(0, int(per_user_limit or 0)),
            'created_by': created_by, 'created_at': datetime.now().isoformat(),
        })
        return True

    async def discount_list(self) -> list:
        return await self.discount_codes.find({}).sort('created_at', -1).to_list(100)

    async def discount_get(self, code: str) -> dict:
        return await self.discount_codes.find_one({'code': code.strip().upper()})

    async def discount_toggle(self, code: str) -> bool:
        d = await self.discount_codes.find_one({'code': code.strip().upper()})
        if not d:
            return False
        await self.discount_codes.update_one(
            {'_id': d['_id']}, {'$set': {'active': not d.get('active', True)}}
        )
        return True

    async def discount_delete(self, code: str) -> bool:
        result = await self.discount_codes.delete_one({'code': code.strip().upper()})
        return result.deleted_count > 0

    async def discount_validate(self, code: str, plan_id: str = None,
                                 user_id: int = None) -> dict:
        """
        اعتبارسنجی کد تخفیف — کد را مصرف نمی‌کند، فقط بررسی می‌کند.
        خروجی: {'ok': True, 'percent': N} یا {'ok': False, 'reason': '...'}
        موج D1: پارامترهای اختیاری plan_id/user_id — وقتی داده شوند،
        محدودیت پلن هدف و سقف استفاده‌ی هر کاربر هم چک می‌شود. فرم امضای
        قبلی (فقط code) کاملاً سازگار می‌ماند.
        """
        d = await self.discount_codes.find_one({'code': code.strip().upper()})
        if not d or not d.get('active'):
            return {'ok': False, 'reason': 'کد تخفیف معتبر نیست.'}
        if d.get('expires_at') and d['expires_at'] < datetime.now().isoformat():
            return {'ok': False, 'reason': 'این کد تخفیف منقضی شده.'}
        if d.get('max_uses', 0) > 0 and d.get('used_count', 0) >= d['max_uses']:
            return {'ok': False, 'reason': 'سقف استفاده از این کد تمام شده.'}
        # 🎟 موج D1 — محدودیت پلن هدف
        targets = d.get('target_plan_ids') or []
        if plan_id and targets and str(plan_id) not in targets:
            return {'ok': False, 'reason': 'این کد برای این پلن قابل استفاده نیست.'}
        # 🎟 موج D1 — سقف استفاده‌ی هر کاربر
        if user_id is not None and d.get('per_user_limit', 0) > 0:
            used_by_user = await self.discount_uses.count_documents(
                {'code': d['code'], 'user_id': int(user_id)})
            if used_by_user >= d['per_user_limit']:
                return {'ok': False, 'reason': 'شما قبلاً از این کد استفاده کرده‌اید.'}
        return {'ok': True, 'percent': d['percent'], 'discount': d}

    async def discount_consume(self, code: str, user_id: int = None):
        """
        مصرف کد — موج D1: کاملاً اتمیک و بدون نشتی.

          (۱) اگر per_user_limit فعال است، رزرو کاربر در discount_uses با
              unique index اتمیک ثبت می‌شود؛ تکراری ⇒ None (used_count
              دست‌نخورده می‌ماند — نشتی صفر).
          (۲) find_one_and_update با guard شرطی ($expr روی max_uses،
              expires_at و active) — در استفاده‌ی هم‌زمانِ چند کاربر
              used_count هرگز از max_uses عبور نمی‌کند (race fix).
          (۳) اگر گام ۲ شکست بخورد، رزرو گام ۱ جبران (حذف) می‌شود.

        max_uses=0 یعنی نامحدود.
        خروجی: سند به‌روزشده، یا None اگر نامعتبر/منقضی/پر شده باشد.
        """
        code_u = code.strip().upper()
        # (۱) رزرو per-user — قبل از افزایش شمارنده، تا شکست مصرف نشتی نسازد
        reserved = False
        if user_id is not None:
            d0 = await self.discount_codes.find_one({'code': code_u})
            if d0 and d0.get('per_user_limit', 0) > 0:
                try:
                    await self.discount_uses.insert_one({
                        'code': code_u, 'user_id': int(user_id),
                        'used_at': datetime.now().isoformat(),
                    })
                    reserved = True
                except Exception:
                    return None  # کاربر قبلاً این کد را مصرف کرده
        # (۲) مصرف اتمیک با guard
        now_iso = datetime.now().isoformat()
        d = await self.discount_codes.find_one_and_update(
            {
                'code': code_u, 'active': True,
                '$and': [
                    {'$or': [{'expires_at': None}, {'expires_at': {'$gt': now_iso}},
                             {'expires_at': {'$exists': False}}]},
                    {'$or': [{'max_uses': 0},
                             {'$expr': {'$lt': ['$used_count', '$max_uses']}}]},
                ],
            },
            {'$inc': {'used_count': 1}},
            return_document=True,
        )
        if not d:
            # (۳) جبران رزرو — مصرف انجام نشد
            if reserved:
                try:
                    await self.discount_uses.delete_one(
                        {'code': code_u, 'user_id': int(user_id)})
                except Exception:
                    pass
            return None
        # ⛔ موج D2 — لحظه‌ی اتمام ظرفیت: فقط همین یک مصرف‌کننده گذار از
        # max-1 به max را می‌بیند (فیلتر اتمیک تضمین می‌کند) ⇒ دقیقاً یک
        # سیگنال. خروجی ربات (mini_app_outbox_job) متن کمپین‌های ارسالی
        # را به «اتمام موجودی» ادیت می‌کند. نامحدود (۰) ⇒ هرگز.
        try:
            mu = int(d.get('max_uses', 0) or 0)
            if mu > 0 and int(d.get('used_count', 0) or 0) >= mu:
                await self.bot_notifs.insert_one({
                    'type': 'signal', 'chat_id': 0,
                    'text': f'__DISCOUNT_EXHAUSTED__:{code_u}',
                    'sent': False, 'created_at': datetime.now().isoformat(),
                })
        except Exception:
            pass  # سیگنال نباید مسیر خرید را بشکند
        return d

    async def discount_release(self, code: str, user_id: int = None):
        """
        جبران مصرف — در رد رسید پرداخت صدا زده می‌شود: رزرو per-user حذف
        و used_count یک واحد کم می‌شود (کف ۰) تا کاربر بتواند با رسید
        درست دوباره از همان کد استفاده کند.
        برای کدهای per_user_limit تنها وقتی شمارنده کم می‌شود که رزروی
        واقعیِ همین کاربر حذف شده باشد (ضد کاهش اشتباه).
        """
        try:
            code_u = code.strip().upper()
            freed = False
            if user_id is not None:
                r = await self.discount_uses.delete_one(
                    {'code': code_u, 'user_id': int(user_id)})
                freed = (r.deleted_count or 0) > 0
            d0 = await self.discount_codes.find_one({'code': code_u})
            if not d0:
                return
            if d0.get('per_user_limit', 0) > 0 and user_id is not None and not freed:
                return
            await self.discount_codes.update_one(
                {'code': code_u, 'used_count': {'$gt': 0}},
                {'$inc': {'used_count': -1}})
        except Exception:
            pass

    # ── کاربران و سگمنت‌های کمپین (موج D1) ──
    async def discount_segment_users(self, segment: str = 'all') -> list:
        """کاربران هدف کمپین. segment: all | subscribers | no_sub"""
        if segment == 'subscribers':
            subs = await self.subscriptions.find(
                {'status': 'active', 'end_date': {'$gte': datetime.now().isoformat()}}
            ).to_list(length=None)
            ids = list({int(s['_id']) for s in subs})
            if not ids:
                return []
            return await self.users.find(
                {'approved': True, 'blocked_bot': {'$ne': True}, 'user_id': {'$in': ids}}
            ).to_list(length=None)
        if segment == 'no_sub':
            subs = await self.subscriptions.find(
                {'status': 'active', 'end_date': {'$gte': datetime.now().isoformat()}}
            ).to_list(length=None)
            ids = list({int(s['_id']) for s in subs})
            return await self.users.find(
                {'approved': True, 'blocked_bot': {'$ne': True}, 'user_id': {'$nin': ids}}
            ).to_list(length=None)
        return await self.users.find(
            {'approved': True, 'blocked_bot': {'$ne': True}}
        ).to_list(length=None)

    async def discount_payment_stats(self, code: str) -> dict:
        """آمار استفاده‌ی واقعی یک کد — از اسناد sub_payments (snapshot مالی)."""
        code_u = code.strip().upper()
        approved = await self.sub_payments.find(
            {'discount_code': code_u, 'status': 'approved'}
        ).to_list(length=None)
        return {
            'usage_approved': len(approved),
            'revenue': sum(int(p.get('final_price', 0) or 0) for p in approved),
            'discount_given': sum(
                max(0, int(p.get('price', 0) or 0) - int(p.get('final_price', 0) or 0))
                for p in approved
            ),
        }

    async def discount_bcast_create(self, code: str, target: str, created_by: int,
                                     source: str = 'bot') -> str:
        import uuid
        bid = uuid.uuid4().hex[:12]
        await self.discount_bcasts.insert_one({
            'broadcast_id': bid, 'code': code, 'target': target,
            'status': 'sending', 'total': 0, 'sent': 0, 'failed': 0, 'blocked': 0,
            'source': source, 'created_by': created_by,
            'created_at': datetime.now().isoformat(),
        })
        return bid

    async def discount_bcast_get(self, bid: str):
        return await self.discount_bcasts.find_one({'broadcast_id': bid})

    async def discount_bcast_update(self, bid: str, fields: dict):
        await self.discount_bcasts.update_one(
            {'broadcast_id': bid}, {'$set': fields})

    async def discount_bcast_active_for(self, code: str):
        """اگر برای این کد broadcast در حال ارسال است → سند (ضد دابل‌کلیک)"""
        return await self.discount_bcasts.find_one(
            {'code': code, 'status': 'sending'})

    async def discount_bcast_list(self, code: str, limit: int = 5) -> list:
        return await self.discount_bcasts.find(
            {'code': code}).sort('created_at', -1).to_list(limit)

    # ⛔ موج D2 — ادیت «اتمام موجودی»: مرجع پیام‌های کمپین
    async def discount_bcast_add_msgs(self, bid: str, refs: list):
        """ثبت مرجع پیام‌های موفق کمپین — [{'c': chat_id, 'm': message_id}]
        با $push ضمیمه می‌شود تا ادیت همگانیِ «اتمام موجودی» ممکن شود."""
        if not refs:
            return
        await self.discount_bcasts.update_one(
            {'broadcast_id': bid},
            {'$push': {'sent_msgs': {'$each': refs}}})

    async def discount_bcast_with_msgs(self, code: str) -> list:
        """کمپین‌های این کد که حداقل یک مرجع پیام دارند (قابل ادیت)"""
        return await self.discount_bcasts.find(
            {'code': code, 'soldout_marked': {'$ne': True},
             'sent_msgs.0': {'$exists': True}}).to_list(None)

    # ── وضعیت اشتراک هر کاربر (یک سند در هر کاربر، با _id = user_id) ──
    async def sub_get(self, user_id: int) -> dict:
        return await self.subscriptions.find_one({'_id': user_id})

    async def sub_is_active(self, user_id: int) -> bool:
        s = await self.sub_get(user_id)
        if not s or s.get('status') != 'active':
            return False
        return s.get('end_date', '') >= datetime.now().isoformat()

    async def sub_days_left(self, user_id: int) -> int:
        s = await self.sub_get(user_id)
        if not s or s.get('status') != 'active' or not s.get('end_date'):
            return 0
        try:
            end = datetime.fromisoformat(s['end_date'])
            return max(0, (end - datetime.now()).days)
        except Exception:
            return 0

    async def sub_activate(self, user_id: int, days: int, plan_name: str,
                            source: str = 'payment', granted_by: int = 0,
                            extend: bool = False):
        """
        فعال‌سازی/تمدید اشتراک. اگر extend=True و اشتراک فعلی هنوز فعاله،
        روزها از تاریخ پایان فعلی جمع می‌شوند نه از الان (تا تمدید،
        روزهای باقی‌مانده را از بین نبرد).
        """
        now = datetime.now()
        s = await self.sub_get(user_id)
        if extend and s and s.get('status') == 'active' and s.get('end_date', '') > now.isoformat():
            base = datetime.fromisoformat(s['end_date'])
        else:
            base = now
        end_date = (base + timedelta(days=days)).isoformat()
        # FIX جدید: total_days برای رسم نوار پیشرفت باقیمانده استفاده می‌شود
        total_days = max(1, (datetime.fromisoformat(end_date) - base).days) if not extend else days
        await self.subscriptions.update_one(
            {'_id': user_id},
            {'$set': {
                'status': 'active', 'plan_name': plan_name,
                'start_date': now.isoformat(), 'end_date': end_date,
                'source': source, 'granted_by': granted_by,
                'last_plan_days': days,
                # FIX جدید: دو فلگ جدا برای یادآوری ۳روزه و ۱روزه
                'reminder_3d_sent': False, 'reminder_1d_sent': False,
                'updated_at': now.isoformat(),
            }},
            upsert=True
        )
        return end_date

    async def sub_revoke(self, user_id: int, reason: str, revoked_by: int) -> bool:
        result = await self.subscriptions.update_one(
            {'_id': user_id},
            {'$set': {
                'status': 'revoked', 'revoke_reason': reason,
                'revoked_by': revoked_by, 'revoked_at': datetime.now().isoformat(),
            }}
        )
        return result.matched_count > 0

    async def sub_expire_due(self) -> list:
        """کاربرانی که تاریخ پایانشان گذشته ولی هنوز status=active مانده"""
        now_iso = datetime.now().isoformat()
        due = await self.subscriptions.find(
            {'status': 'active', 'end_date': {'$lt': now_iso}}
        ).to_list(500)
        if due:
            await self.subscriptions.update_many(
                {'_id': {'$in': [d['_id'] for d in due]}},
                {'$set': {'status': 'expired'}}
            )
        return due

    async def sub_expiring_soon(self, days_before: int, flag_field: str) -> list:
        """
        اشتراک‌های فعالی که کمتر از N روز تا پایانشان مانده و هنوز
        یادآوری مخصوص همان فلگ (سه‌روزه یا یک‌روزه) را نگرفته‌اند.
        FIX جدید: دو یادآوری جدا (۳ روز و ۱ روز قبل) — دقیقاً مثل
        الگوی یادآوری‌های پلکانی امتحان که در ربات وجود دارد.
        """
        now = datetime.now()
        cutoff = (now + timedelta(days=days_before)).isoformat()
        return await self.subscriptions.find({
            'status': 'active',
            'end_date': {'$gte': now.isoformat(), '$lte': cutoff},
            flag_field: {'$ne': True},
        }).to_list(500)

    async def sub_mark_reminder_sent(self, user_id: int, flag_field: str):
        await self.subscriptions.update_one(
            {'_id': user_id}, {'$set': {flag_field: True}}
        )

    async def sub_stats(self) -> dict:
        active  = await self.subscriptions.count_documents({'status': 'active'})
        expired = await self.subscriptions.count_documents({'status': 'expired'})
        revoked = await self.subscriptions.count_documents({'status': 'revoked'})
        pending = await self.sub_payments.count_documents({'status': 'pending'})
        approved_total = await self.sub_payments.count_documents({'status': 'approved'})
        rejected_total = await self.sub_payments.count_documents({'status': 'rejected'})
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        revenue_total = revenue_month = 0
        plan_counter: dict = {}
        async for p in self.sub_payments.find({'status': 'approved'}):
            amt = p.get('final_price', p.get('price', 0))
            revenue_total += amt
            if p.get('reviewed_at', '') >= month_start:
                revenue_month += amt
            plan_counter[p.get('plan_name', '-')] = plan_counter.get(p.get('plan_name', '-'), 0) + 1
        top_plan = max(plan_counter, key=plan_counter.get) if plan_counter else '-'
        conv_rate = round(approved_total / (approved_total + rejected_total) * 100) if (approved_total + rejected_total) else 0
        return {
            'active': active, 'expired': expired, 'revoked': revoked,
            'pending': pending, 'revenue': revenue_total,
            'revenue_month': revenue_month,
            'approved_total': approved_total, 'rejected_total': rejected_total,
            'top_plan': top_plan, 'conv_rate': conv_rate,
        }

    # ── صف رسیدهای پرداخت ──
    async def sub_payment_create(self, user_id: int, plan_id: str, plan_name: str,
                                  price: int, final_price: int, screenshot_file_id: str,
                                  discount_code: str = None,
                                  discount_percent: int = None) -> str:
        r = await self.sub_payments.insert_one({
            'user_id': user_id, 'plan_id': plan_id, 'plan_name': plan_name,
            'price': price, 'final_price': final_price,
            'discount_code': discount_code,
            # 🎟 موج D1 — snapshot کامل مالی: حتی اگر بعداً کد ویرایش/حذف شود،
            # درصدِ زمان تراکنش ثابت می‌ماند (immutability)
            'discount_percent': discount_percent,
            'screenshot_file_id': screenshot_file_id,
            'status': 'pending', 'submitted_at': datetime.now().isoformat(),
            'admin_msg_id': None,
        })
        return str(r.inserted_id)

    async def sub_payment_get(self, pid: str):
        try:
            return await self.sub_payments.find_one({'_id': ObjectId(pid)})
        except Exception:
            return None

    async def sub_payment_has_pending(self, user_id: int) -> bool:
        """FIX جدید: جلوگیری از اسپم رسید — تا رسید قبلی بررسی نشده، جدید قبول نمی‌شود"""
        return await self.sub_payments.count_documents(
            {'user_id': user_id, 'status': 'pending'}
        ) > 0

    async def sub_payment_reject_count(self, user_id: int) -> int:
        """FIX جدید: تعداد رد قبلی همین کاربر — سیگنال احتمال تخلف/سوءاستفاده برای ادمین"""
        return await self.sub_payments.count_documents(
            {'user_id': user_id, 'status': 'rejected'}
        )

    async def sub_payment_set_admin_msg(self, pid: str, msg_id: int):
        try:
            await self.sub_payments.update_one(
                {'_id': ObjectId(pid)}, {'$set': {'admin_msg_id': msg_id}}
            )
        except Exception:
            pass

    async def sub_payment_decide(self, pid: str, approved: bool, admin_id: int, note: str = ''):
        try:
            await self.sub_payments.update_one(
                {'_id': ObjectId(pid)},
                {'$set': {
                    'status': 'approved' if approved else 'rejected',
                    'reviewed_by': admin_id, 'reviewed_at': datetime.now().isoformat(),
                    'review_note': note,
                }}
            )
            return True
        except Exception:
            return False

    async def sub_payment_list_pending(self) -> list:
        return await self.sub_payments.find({'status': 'pending'}).sort('submitted_at', 1).to_list(100)

    async def sub_payment_history(self, user_id: int) -> list:
        """FIX جدید: تاریخچه‌ی کامل پرداخت‌های یک کاربر (هر وضعیتی) — برای «تاریخچه‌ی من»"""
        return await self.sub_payments.find({'user_id': user_id}).sort('submitted_at', -1).to_list(30)

    async def sub_payment_list_all(self, status: str = None, skip: int = 0, limit: int = 8, extra: dict = None) -> list:
        """FIX جدید: مرور کامل همه‌ی رسیدها (هر وضعیتی) با صفحه‌بندی — برای پنل ادمین
        extra: فیلتر اختیاری اضافه (مثل $or جست‌وجو) — کاملاً backward-compatible."""
        q = {'status': status} if status else {}
        if extra:
            q.update(extra)
        return await self.sub_payments.find(q).sort('submitted_at', -1).skip(skip).limit(limit).to_list(limit)

    async def sub_payment_count_all(self, status: str = None, extra: dict = None) -> int:
        q = {'status': status} if status else {}
        if extra:
            q.update(extra)
        return await self.sub_payments.count_documents(q)

    async def sub_list_by_status(self, status: str = 'active', skip: int = 0, limit: int = 10, extra: dict = None) -> list:
        """FIX جدید: لیست مشترکین بر اساس وضعیت — برای صفحه‌ی «لیست مشترکین» پنل ادمین
        extra: فیلتر اختیاری اضافه (مثل $or جست‌وجو) — کاملاً backward-compatible."""
        q = {'status': status}
        if extra:
            q.update(extra)
        return await self.subscriptions.find(q) \
            .sort('end_date', 1).skip(skip).limit(limit).to_list(limit)

    async def sub_count_by_status(self, status: str = 'active', extra: dict = None) -> int:
        q = {'status': status}
        if extra:
            q.update(extra)
        return await self.subscriptions.count_documents(q)

    # ══════════════════════════════════════════════════
    #  📊 سیستم نمرات — FIX جدید
    #  نمرات امتحانی هر درس، ثبت‌شده توسط ادمین یا نماینده‌ی ورودی
    # ══════════════════════════════════════════════════

    @staticmethod
    def _norm_name(name: str) -> str:
        """نرمال‌سازی نام برای مقایسه — حذف فاصله‌های اضافه/نیم‌فاصله متفاوت"""
        return ' '.join((name or '').replace('\u200c', ' ').split()).strip().lower()

    async def find_students_by_name(self, name: str, intake: str = None) -> list:
        """
        جست‌وجوی دانشجو با نام (برای ثبت نمره‌ی دسته‌ای).
        اگه intake داده بشه، فقط همون ورودی جست‌وجو می‌شه (محدودیت نماینده).
        مقایسه با نرمال‌سازی انجام می‌شود تا فاصله/نیم‌فاصله اذیت نکند.
        """
        target = self._norm_name(name)
        if not target:
            return []
        q = {'approved': True}
        if intake:
            q['intake'] = intake
        candidates = await self.users.find(q).to_list(3000)
        return [u for u in candidates if self._norm_name(u.get('name', '')) == target]

    async def grade_bulk_upsert(self, entries: list, lesson: str, exam_title: str,
                                 exam_date: str, entered_by: int) -> list:
        """
        entries: [{'user_id': int, 'score': float}, ...]
        برای هر دانشجو، اگه نمره‌ی همین درس+امتحان از قبل ثبت شده بود
        آپدیت می‌شود (نه رکورد تکراری)، وگرنه درج می‌شود.
        خروجی: لیست رکوردهای نهایی ثبت‌شده (برای ارسال نوتیف).
        """
        now = datetime.now().isoformat()
        saved = []
        for e in entries:
            uid, score = e['user_id'], e['score']
            existing = await self.grades.find_one({
                'student_id': uid, 'lesson': lesson, 'exam_title': exam_title
            })
            doc = {
                'student_id': uid, 'lesson': lesson, 'exam_title': exam_title,
                'exam_date': exam_date, 'score': score, 'entered_by': entered_by,
                'updated_at': now,
            }
            if existing:
                await self.grades.update_one({'_id': existing['_id']}, {'$set': doc})
                doc['_is_update'] = True
            else:
                doc['created_at'] = now
                r = await self.grades.insert_one(doc)
                doc['_id'] = r.inserted_id
                doc['_is_update'] = False
            saved.append(doc)
        return saved

    async def grade_list_for_student(self, uid: int) -> list:
        return await self.grades.find({'student_id': uid}).sort('exam_date', -1).to_list(200)

    async def grade_list_recent(self, skip: int = 0, limit: int = 10, intake: str = None) -> list:
        """
        FIX جدید: مرور نمرات ثبت‌شده‌ی اخیر — اگه intake داده بشه (برای
        نماینده)، فقط نمرات دانشجویان همون ورودی نشان داده می‌شود.
        """
        if not intake:
            return await self.grades.find({}).sort('created_at', -1).skip(skip).limit(limit).to_list(limit)
        # چون intake روی خودِ grade نیست (روی کاربره)، اول کاربرهای اون ورودی رو می‌گیریم
        student_ids = [u['user_id'] async for u in self.users.find({'intake': intake}, {'user_id': 1})]
        return await self.grades.find({'student_id': {'$in': student_ids}}) \
            .sort('created_at', -1).skip(skip).limit(limit).to_list(limit)

    async def grade_count_recent(self, intake: str = None) -> int:
        if not intake:
            return await self.grades.count_documents({})
        student_ids = [u['user_id'] async for u in self.users.find({'intake': intake}, {'user_id': 1})]
        return await self.grades.count_documents({'student_id': {'$in': student_ids}})

    # ══════════════════════════════════════════════════
    #  آمار مصرف هوشیار (AI) — برای پنل ادمین
    # ══════════════════════════════════════════════════

    async def ai_usage_stats(self, top_n: int = 5) -> dict:
        """
        آمار مصرف هوشیار: تعداد سوال امروز/کل، توکن مصرفی امروز/کل، و
        پرمصرف‌ترین کاربرها. فیلد ai_total_usage (همه‌ی زمان‌ها) و
        ai_usage_count/ai_usage_date (روزانه) روی خودِ سند کاربر در
        check_and_consume_quota نگه‌داری می‌شوند؛ ai_total_tokens/
        ai_tokens_today هم در ai_inc_tokens. اینجا فقط جمع‌بندی‌شان می‌کنیم.
        """
        today = datetime.now().strftime('%Y-%m-%d')
        rows = await self.users.find(
            {'$or': [{'ai_total_usage': {'$gt': 0}}, {'ai_usage_date': today}]},
            {
                'user_id': 1, 'name': 1, 'ai_usage_count': 1, 'ai_usage_date': 1,
                'ai_total_usage': 1, 'ai_total_tokens': 1, 'ai_tokens_today': 1,
            },
        ).to_list(length=None)

        total_today = users_today = total_alltime = users_alltime = 0
        tokens_today = tokens_alltime = 0
        today_list, alltime_list = [], []

        for u in rows:
            alltime = u.get('ai_total_usage', 0) or 0
            tokens_alltime += u.get('ai_total_tokens', 0) or 0
            if alltime > 0:
                total_alltime += alltime
                users_alltime += 1
                alltime_list.append((u.get('name') or '—', u.get('user_id'), alltime))

            if u.get('ai_usage_date') == today:
                today_count = u.get('ai_usage_count', 0) or 0
                tokens_today += u.get('ai_tokens_today', 0) or 0
                if today_count > 0:
                    total_today += today_count
                    users_today += 1
                    today_list.append((u.get('name') or '—', u.get('user_id'), today_count))

        today_list.sort(key=lambda x: x[2], reverse=True)
        alltime_list.sort(key=lambda x: x[2], reverse=True)

        return {
            'total_today':   total_today,
            'users_today':   users_today,
            'total_alltime': total_alltime,
            'users_alltime': users_alltime,
            'tokens_today':   tokens_today,
            'tokens_alltime': tokens_alltime,
            'top_today':     today_list[:top_n],
            'top_alltime':   alltime_list[:top_n],
        }

    async def ai_inc_tokens(self, uid: int, tokens: int) -> None:
        """
        افزایشِ اتمیک (بدون نیاز به خواندن قبلی) توکن مصرفیِ هوشیار برای
        یک کاربر — هم شمارنده‌ی «امروز» (که موقع رد شدن روز در
        check_and_consume_quota صفر می‌شود) و هم شمارنده‌ی «کل».
        """
        if not tokens:
            return
        await self.users.update_one(
            {'user_id': uid},
            {'$inc': {'ai_total_tokens': int(tokens), 'ai_tokens_today': int(tokens)}},
        )

    # ══════════════════════════════════════════════════
    #  مسدودکردن یک کاربر خاص از هوشیار (جدا از بلاک کاملِ ربات)
    # ══════════════════════════════════════════════════

    async def ai_set_banned(self, uid: int, banned: bool) -> None:
        await self.users.update_one({'user_id': uid}, {'$set': {'ai_banned': bool(banned)}})

    async def ai_is_banned(self, uid: int) -> bool:
        user = await self.get_user(uid) or {}
        return bool(user.get('ai_banned'))

    async def ai_list_banned(self, limit: int = 50) -> list:
        return await self.users.find(
            {'ai_banned': True}, {'user_id': 1, 'name': 1}
        ).to_list(length=limit)

    # ══════════════════════════════════════════════════
    #  لاگِ پایدارِ «گزارش پاسخ نامناسب» — قبلاً فقط توی RAM بود و با
    #  ری‌استارتِ ربات از بین می‌رفت؛ حالا برای بررسیِ بعدیِ ادمین توی
    #  دیتابیس هم ثبت می‌شه (مستقل از کشِ موقتِ RAM که برای دکمه‌ی زیر
    #  پیام استفاده می‌شه).
    # ══════════════════════════════════════════════════

    async def ai_log_report(self, uid: int, name: str, question: str, answer: str) -> None:
        await self.ai_reports.insert_one({
            'user_id':  uid,
            'name':     name or '—',
            'question': (question or '—')[:1000],
            'answer':   (answer or '—')[:2000],
            'created_at': datetime.now(),
        })

    async def ai_recent_reports(self, limit: int = 10) -> list:
        cursor = self.ai_reports.find({}).sort('created_at', -1).limit(limit)
        return await cursor.to_list(length=limit)

    # ══════════════════════════════════════════════════
    #  حافظه‌ی مکالمه‌ی هوشیار — ⚠️ فیکس: قبلاً فقط توی RAM بود و با هر
    #  ری‌استارتِ سرور (که این چند روز به‌خاطرِ آپدیت‌های پیاپی زیاد
    #  اتفاق افتاد) کاملاً از بین می‌رفت. حالا روی خودِ سندِ کاربر توی
    #  دیتابیس ذخیره می‌شه — پایدار، ولی فشرده: با $slice همیشه فقط
    #  چند آیتمِ آخر نگه داشته می‌شه (نه یه آرشیوِ بی‌نهایت‌رشد).
    # ══════════════════════════════════════════════════

    async def ai_remember(self, uid: int, role: str, text: str, max_items: int) -> None:
        await self.users.update_one(
            {'user_id': uid},
            {
                '$push': {'ai_mem': {'$each': [{'r': role, 't': (text or '')[:1200]}], '$slice': -max_items}},
                '$set': {'ai_mem_at': datetime.now()},
            },
        )

    async def ai_get_memory(self, uid: int) -> tuple:
        """برمی‌گرداند (items, last_updated_datetime_or_None)."""
        user = await self.get_user(uid) or {}
        return user.get('ai_mem', []) or [], user.get('ai_mem_at')

    async def ai_clear_memory(self, uid: int) -> None:
        await self.users.update_one({'user_id': uid}, {'$unset': {'ai_mem': '', 'ai_mem_at': ''}})

    # ══════════════════════════════════════════════════
    #  گفت‌وگوهای چندگانه‌ی هوشیار (مینی‌اپ) — افزایشی:
    #  حافظه‌ی تک‌رشته‌ای ai_mem بالا دست‌نخورده می‌ماند
    #  تا چت ربات و مینی‌اپ همچنان مشترک باشد؛ این بخش
    #  رشته‌های جداگانه‌ی مدیریت‌شده (پین/آرشیو/حذف) است.
    # ══════════════════════════════════════════════════

    async def ai_conv_create(self, uid: int, title: str = 'گفت‌وگوی جدید') -> str:
        doc = {
            'user_id':    uid,
            'title':      title,
            'pinned':     False,
            'archived':   False,
            'items':      [],
            'preview':    '',
            'msg_count':  0,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
        }
        r = await self.ai_conversations.insert_one(doc)
        return str(r.inserted_id)

    async def ai_conv_insert_copy(self, uid: int, title: str,
                                  items: list,
                                  max_items: int = 120) -> str:
        """درج رونوشتِ یک گفت‌وگو — آیتم‌ها عیناً (با نقش و متن) کپی
        می‌شوند و برچسبِ زمانیِ ساخت/به‌روزرسانی، لحظه‌ی فعلی است."""
        now = datetime.now().isoformat()
        clipped = (items or [])[-max_items:]
        doc = {
            'user_id':    uid,
            'title':      (title or 'رونوشت گفت‌وگو')[:80],
            'pinned':     False,
            'archived':   False,
            'items':      clipped,
            'preview':    (str(clipped[-1].get('t') or '')[:90]
                           if clipped else ''),
            'msg_count':  len(clipped),
            'created_at': now,
            'updated_at': now,
        }
        r = await self.ai_conversations.insert_one(doc)
        return str(r.inserted_id)

    async def ai_conv_list(self, uid: int, include_archived: bool = False) -> list:
        q = {'user_id': uid}
        if not include_archived:
            q['archived'] = {'$ne': True}
        docs = await self.ai_conversations.find(
            q,
            {'items': 0},   # فقط متا — آیتم‌ها را جداگانه می‌خوانیم
        ).to_list(200)
        docs.sort(key=lambda d: (
            0 if d.get('pinned') else 1,
            -(datetime.fromisoformat(d.get('updated_at', '1970-01-01')).timestamp()
              if d.get('updated_at') else 0),
        ))
        return docs

    async def ai_conv_get(self, cid: str, uid: int) -> dict | None:
        try:
            oid = ObjectId(cid)
        except Exception:
            return None
        return await self.ai_conversations.find_one(
            {'_id': oid, 'user_id': uid}
        )

    async def ai_conv_update(self, cid: str, uid: int, fields: dict) -> bool:
        allowed = {'title', 'pinned', 'archived'}
        patch = {k: v for k, v in fields.items() if k in allowed}
        if not patch:
            return False
        patch['updated_at'] = datetime.now().isoformat()
        try:
            oid = ObjectId(cid)
        except Exception:
            return False
        r = await self.ai_conversations.update_one(
            {'_id': oid, 'user_id': uid}, {'$set': patch}
        )
        return r.matched_count == 1

    async def ai_conv_delete(self, cid: str, uid: int) -> bool:
        try:
            oid = ObjectId(cid)
        except Exception:
            return False
        r = await self.ai_conversations.delete_one(
            {'_id': oid, 'user_id': uid}
        )
        return r.deleted_count == 1

    async def ai_conv_delete_empty(self, uid: int) -> None:
        """گفت‌وگوهای خالیِ رهاشده را پاک می‌کند — وقتی کاربر چند بار پشت
        سرهم «گفت‌وگوی جدید» می‌سازد بدون اینکه چیزی بفرستد."""
        await self.ai_conversations.delete_many(
            {'user_id': uid, 'msg_count': {'$lte': 0}}
        )

    async def ai_conv_append(self, cid: str, uid: int,
                             user_item: dict, ai_item: dict,
                             title: str | None, preview: str,
                             max_items: int = 120) -> bool:
        """افزودن یک دورِ پرسش/پاسخ به گفت‌وگو (اتمیک) + به‌روزرسانی متا.
        فقط وقتی title داده شود (اولین دور) عنوانی که ساخته‌ایم ست می‌شود."""
        try:
            oid = ObjectId(cid)
        except Exception:
            return False
        set_fields = {
            'updated_at': datetime.now().isoformat(),
            'preview':    (preview or '')[:90],
        }
        if title:
            set_fields['title'] = title
        r = await self.ai_conversations.update_one(
            {'_id': oid, 'user_id': uid},
            {
                '$push': {'items': {'$each': [user_item, ai_item], '$slice': -max_items}},
                '$set':  set_fields,
                '$inc':  {'msg_count': 2},
            },
        )
        return r.matched_count == 1

    # ══════════════════════════════════════════════════
    #  سندِ مرجعِ فعال — ⚠️ قابلیتِ جدید: وقتی دانشجو یه PDF می‌فرسته،
    #  خودِ فایل روی سرورهای گوگل (Files API، رایگان، ۴۸ ساعت نگه‌داری)
    #  آپلود می‌شه؛ اینجا فقط یه اشاره‌گرِ کوچیک (URI + زمان) ذخیره
    #  می‌کنیم، نه خودِ فایل — دیتابیسِ ما دست‌نخورده و فشرده می‌مونه.
    # ══════════════════════════════════════════════════

    async def ai_set_doc(self, uid: int, uri: str, mime: str, name: str) -> None:
        await self.users.update_one(
            {'user_id': uid},
            {'$set': {
                'ai_doc_uri': uri, 'ai_doc_mime': mime, 'ai_doc_name': name[:100],
                'ai_doc_at': datetime.now(),
            }},
        )

    async def ai_get_doc(self, uid: int) -> dict:
        user = await self.get_user(uid) or {}
        if not user.get('ai_doc_uri'):
            return None
        return {
            'uri': user['ai_doc_uri'], 'mime': user.get('ai_doc_mime'),
            'name': user.get('ai_doc_name'), 'at': user.get('ai_doc_at'),
        }

    async def ai_clear_doc(self, uid: int) -> None:
        await self.users.update_one(
            {'user_id': uid},
            {'$unset': {'ai_doc_uri': '', 'ai_doc_mime': '', 'ai_doc_name': '', 'ai_doc_at': ''}},
        )

    # ══════════════════════════════════════════════════
    #  ⚠️ قابلیتِ جدید: «پروفایلِ ماندگارِ فشرده» — به‌جای نگه‌داشتنِ کلِ
    #  متنِ گفتگوها برای همیشه (که هم مشکلِ حریمِ خصوصی داره هم دیتابیس
    #  رو پر می‌کنه)، فقط چند نکته‌ی مختصر و ماندگار که خودِ مدل تشخیص
    #  می‌ده «ارزشِ به‌خاطرسپردن» رو داره، ذخیره می‌شه (حداکثر ۶ مورد،
    #  با $slice همیشه فشرده می‌مونه). کاملاً جدا از حافظه‌ی مکالمه‌ی
    #  ۶ساعته (ai_mem) — این یکی هیچ TTL ای نداره چون قراره ماندگار باشه.
    # ══════════════════════════════════════════════════

    async def ai_remember_fact(self, uid: int, fact: str, max_items: int = 6) -> None:
        if not fact:
            return
        await self.users.update_one(
            {'user_id': uid},
            {'$push': {'ai_profile_notes': {'$each': [fact[:300]], '$slice': -max_items}}},
        )

    async def ai_get_profile_notes(self, uid: int) -> list:
        user = await self.get_user(uid) or {}
        return user.get('ai_profile_notes', []) or []

    async def ai_forget_profile(self, uid: int) -> None:
        await self.users.update_one({'user_id': uid}, {'$unset': {'ai_profile_notes': ''}})

    async def faq_search_text(self, query_text: str, limit: int = 8) -> list:
        """جستجوی آزادِ متنی توی FAQ — برای Function Callingِ هوشیار."""
        if not query_text:
            return []
        rx = {'$regex': query_text, '$options': 'i'}
        return await self.faq.find(
            {'$or': [{'question': rx}, {'answer': rx}]}
        ).limit(limit).to_list(limit)


db = DB()

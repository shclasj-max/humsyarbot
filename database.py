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
        # FIX جدید: بلک‌لیست بلاک کامل — بر اساس آیدی عددی تلگرام (ثابت و
        # غیرقابل تغییر)، برخلاف یوزرنیم که کاربر می‌تواند عوضش کند.
        # کاربر بلاک‌شده هم از دیتابیس حذف می‌شود و هم دیگر نمی‌تواند
        # با همان آیدی دوباره ثبت‌نام کند.
        self.blacklist    = _db['blacklist']
        self.admin_roles  = _db['admin_roles']      # FIX جدید: سطوح دسترسی چندگانه ادمین
        self.audit_logs   = _db['audit_logs']       # FIX جدید: لاگ فعالیت‌های حساس
        # FIX جدید: سیستم اشتراک — پلن‌ها، وضعیت هر کاربر، رسیدهای
        # در انتظار بررسی، و کدهای تخفیف
        self.sub_plans     = _db['sub_plans']
        self.subscriptions = _db['subscriptions']
        self.sub_payments  = _db['sub_payments']
        self.discount_codes = _db['discount_codes']
        self.grades         = _db['grades']  # FIX جدید: سیستم نمرات

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
            )
            logger.info("✅ ایندکس‌های MongoDB ایجاد شدند")
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
        query = {'approved': True, f'notification_settings.{ntype}': True}
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
        return False

    async def search_users(self, query_text: str):
        """
        FIX مهم: قبلاً فقط name/student_id/username رو با regex می‌گشت —
        یعنی اگه کسی آیدی عددی تلگرام (user_id) وارد می‌کرد، هیچ‌وقت
        پیدا نمی‌شد (چون user_id عدده، نه رشته، و اصلاً توی کوئری
        نبود). حالا هر سه الگو پشتیبانی می‌شه:
          ۱) آیدی عددی تلگرام (مثلاً 123456789)
          ۲) یوزرنیم، با یا بدون @ (مثلاً @ali_r یا ali_r)
          ۳) اسمی که توی ربات ثبت‌نام کرده
        """
        import re
        raw = (query_text or '').strip()
        if not raw:
            return []

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

        return await self.users.find({'$or': or_clauses}).to_list(20)

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
        return [
            u for u in users
            if u.get('notification_settings', {}).get(ntype, True)
        ]

    # ══════════════════════════════════════════════════
    #  علوم پایه — درس‌ها
    # ══════════════════════════════════════════════════

    async def bs_get_lessons(self, term: str):
        return await self.bs_lessons.find({'term': term}).sort('order', 1).to_list(50)

    async def bs_add_lesson(self, term: str, name: str, teacher: str = ''):
        if await self.bs_lessons.find_one({'term': term, 'name': name}):
            return None
        count = await self.bs_lessons.count_documents({'term': term})
        r = await self.bs_lessons.insert_one({
            'term': term, 'name': name, 'teacher': teacher,
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
        await self.log(uid, 'bs_download', {'content_id': cid})

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

    async def ref_get_subjects(self):
        return await self.ref_subjects.find({}).sort('order', 1).to_list(100)

    async def ref_add_subject(self, name: str):
        if await self.ref_subjects.find_one({'name': name}): return None
        count = await self.ref_subjects.count_documents({})
        r = await self.ref_subjects.insert_one({
            'name': name, 'order': count, 'created_at': datetime.now().isoformat(),
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
        await self.log(uid, 'ref_download', {'file_id': fid})

    async def ref_delete_file(self, fid: str):
        try:
            await self.ref_files.delete_one({'_id': ObjectId(fid)})
        except Exception:
            pass

    # ══════════════════════════════════════════════════
    #  بانک سوال
    # ══════════════════════════════════════════════════

    async def add_qbank_file(self, lesson: str, topic: str, file_id: str,
                             description: str, file_type: str = 'document'):
        r = await self.qbank_files.insert_one({
            'lesson': lesson, 'topic': topic, 'file_id': file_id,
            'file_type': file_type, 'description': description,
            'upload_date': datetime.now().isoformat(), 'downloads': 0,
        })
        return r.inserted_id

    async def get_qbank_files(self, lesson: str = None, topic: str = None):
        q = {}
        if lesson: q['lesson'] = lesson
        if topic:  q['topic']  = topic
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
        await self.log(uid, 'qbank_download', {'file_id': fid})

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
                           question_image: str = None, answer_image: str = None):
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
            'approved': auto_approve, 'created_at': datetime.now().isoformat(),
            'attempt_count': 0, 'correct_count': 0,
        })
        return r.inserted_id

    async def get_questions(self, lesson: str = None, topic: str = None,
                            difficulty: str = None, limit: int = 1, exclude: list = None):
        q = {'approved': True}
        if lesson:    q['lesson'] = lesson
        if topic and topic != 'همه': q['topic'] = topic
        if difficulty: q['difficulty'] = difficulty
        if exclude:
            try: q['_id'] = {'$nin': [ObjectId(i) for i in exclude]}
            except Exception: pass
        return await self.questions.find(q).limit(limit).to_list(limit)

    async def get_weak_questions(self, uid: int, limit: int = 1):
        user = await self.get_user(uid)
        weak = user.get('weak_topics', []) if user else []
        if not weak: return await self.get_questions(limit=limit)
        return await self.questions.find(
            {'approved': True, 'topic': {'$in': weak}}
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
        try:
            await self.questions.update_one({'_id': ObjectId(qid)}, {'$set': {'approved': True}})
        except Exception: pass

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
            q['$or'] = [{'group': group}, {'group': 'هر دو'}, {'group': {'$exists': False}}]
        return await self.schedules.find(q).sort('date', 1).to_list(200)

    async def delete_schedule(self, sid: str):
        try:
            await self.schedules.delete_one({'_id': ObjectId(sid)})
        except Exception: pass

    async def upcoming_exams(self, days: int = 7):
        from utils import now_tehran
        today  = now_tehran().strftime('%Y-%m-%d')
        future = (now_tehran() + timedelta(days=days)).strftime('%Y-%m-%d')
        return await self.schedules.find({
            'type': 'exam', 'date': {'$gte': today, '$lte': future},
        }).sort('date', 1).to_list(20)

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

    async def content_admin_stats(self) -> dict:
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
        'content_admin':  '🎓 مدیر محتوا (کلی)',
        'content_scoped': '📅 مدیر محتوا (محدود به ورودی)',
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
        return True

    async def remove_admin_role(self, uid: int):
        await self.admin_roles.delete_one({'_id': uid})

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
        if not doc:
            return False
        perms = self.ROLE_PERMISSIONS.get(doc.get('role', ''), set())
        return permission in perms

    async def get_scoped_intake(self, uid: int) -> str:
        """
        اگه کاربر مدیر محتوای محدود به یک ورودی خاص باشد، کد آن
        ورودی را برمی‌گرداند، وگرنه None (یعنی دسترسی کامل/بدون محدودیت)
        """
        if uid == int(os.getenv('ADMIN_ID', '0')):
            return None
        doc = await self.get_admin_role(uid)
        if doc and doc.get('role') == 'content_scoped':
            return doc.get('scope_intake')
        return None

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
            return 'مدیر محتوا'
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
        update_data = {'status': status}
        if status in ('resolved', 'rejected'):
            update_data['resolved_at'] = datetime.now().isoformat()
            update_data['resolved_by'] = resolved_by
        await self.content_reports.update_one(
            {'report_id': report_id}, {'$set': update_data}
        )

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
        'new_resources': True, 'schedule': True, 'exam': True, 'makeup': True,
        'daily_question': False, 'edu_message': True, 'general': True,
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
                            expires_at: str = None, created_by: int = 0) -> bool:
        code = code.strip().upper()
        if await self.discount_codes.find_one({'code': code}):
            return False
        await self.discount_codes.insert_one({
            'code': code, 'percent': max(1, min(100, percent)),
            'max_uses': max_uses, 'used_count': 0,
            'expires_at': expires_at, 'active': True,
            'created_by': created_by, 'created_at': datetime.now().isoformat(),
        })
        return True

    async def discount_list(self) -> list:
        return await self.discount_codes.find({}).sort('created_at', -1).to_list(100)

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

    async def discount_validate(self, code: str) -> dict:
        """
        اعتبارسنجی کد تخفیف — کد را مصرف نمی‌کند، فقط بررسی می‌کند.
        خروجی: {'ok': True, 'percent': N} یا {'ok': False, 'reason': '...'}
        """
        d = await self.discount_codes.find_one({'code': code.strip().upper()})
        if not d or not d.get('active'):
            return {'ok': False, 'reason': 'کد تخفیف معتبر نیست.'}
        if d.get('expires_at') and d['expires_at'] < datetime.now().isoformat():
            return {'ok': False, 'reason': 'این کد تخفیف منقضی شده.'}
        if d.get('max_uses', 0) > 0 and d.get('used_count', 0) >= d['max_uses']:
            return {'ok': False, 'reason': 'سقف استفاده از این کد تمام شده.'}
        return {'ok': True, 'percent': d['percent']}

    async def discount_consume(self, code: str):
        await self.discount_codes.update_one(
            {'code': code.strip().upper()}, {'$inc': {'used_count': 1}}
        )

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
                                  discount_code: str = None) -> str:
        r = await self.sub_payments.insert_one({
            'user_id': user_id, 'plan_id': plan_id, 'plan_name': plan_name,
            'price': price, 'final_price': final_price,
            'discount_code': discount_code,
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

    async def sub_payment_list_all(self, status: str = None, skip: int = 0, limit: int = 8) -> list:
        """FIX جدید: مرور کامل همه‌ی رسیدها (هر وضعیتی) با صفحه‌بندی — برای پنل ادمین"""
        q = {'status': status} if status else {}
        return await self.sub_payments.find(q).sort('submitted_at', -1).skip(skip).limit(limit).to_list(limit)

    async def sub_payment_count_all(self, status: str = None) -> int:
        q = {'status': status} if status else {}
        return await self.sub_payments.count_documents(q)

    async def sub_list_by_status(self, status: str = 'active', skip: int = 0, limit: int = 10) -> list:
        """FIX جدید: لیست مشترکین بر اساس وضعیت — برای صفحه‌ی «لیست مشترکین» پنل ادمین"""
        return await self.subscriptions.find({'status': status}) \
            .sort('end_date', 1).skip(skip).limit(limit).to_list(limit)

    async def sub_count_by_status(self, status: str = 'active') -> int:
        return await self.subscriptions.count_documents({'status': status})

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


db = DB()

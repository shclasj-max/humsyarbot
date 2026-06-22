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
        self.admin_roles  = _db['admin_roles']      # FIX جدید: سطوح دسترسی چندگانه ادمین
        self.audit_logs   = _db['audit_logs']       # FIX جدید: لاگ فعالیت‌های حساس

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
            'notification_settings': {
                'new_resources':  True,
                'schedule':       True,
                'exam':           True,
                'daily_question': False,
            },
            'total_answers':   0,
            'correct_answers': 0,
            'weak_topics':     [],
        })

    async def update_user(self, uid: int, data: dict):
        await self.users.update_one({'user_id': uid}, {'$set': data})

    async def delete_user(self, uid: int):
        await self.users.delete_one({'user_id': uid})

    async def all_users(self, approved_only: bool = True):
        q = {'approved': True} if approved_only else {}
        return await self.users.find(q).sort('registered_at', -1).to_list(5000)

    async def pending_users(self):
        return await self.users.find({'approved': False}).to_list(100)

    async def notif_users(self, ntype: str):
        return await self.users.find(
            {'approved': True, f'notification_settings.{ntype}': True}
        ).to_list(5000)

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
        regex = {'$regex': query_text, '$options': 'i'}
        return await self.users.find({
            '$or': [
                {'name':       regex},
                {'student_id': regex},
                {'username':   regex},
            ]
        }).to_list(20)

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
        """محتوای جدیدی که هنوز برای آن نوتیف ارسال نشده"""
        return await self.bs_content.find({'notif_sent': {'$ne': True}}).to_list(200)

    async def mark_resources_notified(self, content_ids: list):
        """علامت‌گذاری محتوای ارسال‌شده تا دوباره اعلام نشود"""
        if not content_ids:
            return
        await self.bs_content.update_many(
            {'_id': {'$in': [ObjectId(c) if isinstance(c, str) else c for c in content_ids]}},
            {'$set': {'notif_sent': True}}
        )

    async def bs_get_content_item(self, cid: str):
        try:
            return await self.bs_content.find_one({'_id': ObjectId(cid)})
        except Exception:
            return None

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
        regex = {'$regex': query_text, '$options': 'i'}
        sessions = await self.bs_sessions.find(
            {'$or': [{'topic': regex}, {'teacher': regex}]}
        ).to_list(20)
        result = []
        for s in sessions:
            sid = str(s['_id'])
            contents = await self.bs_content.find({'session_id': sid}).to_list(10)
            for c in contents:
                c['_session'] = s
                result.append(c)
        direct = await self.bs_content.find({'description': regex}).to_list(10)
        existing_ids = {str(r['_id']) for r in result}
        for c in direct:
            if str(c['_id']) not in existing_ids:
                try:
                    c['_session'] = await self.bs_get_session(c.get('session_id', '')) or {}
                except Exception:
                    c['_session'] = {}
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
        existing = await self.ref_files.find_one({'book_id': book_id, 'lang': lang, 'volume': volume})
        if existing:
            await self.ref_files.update_one({'_id': existing['_id']}, {'$set': {
                'file_id': file_id, 'description': description,
                'uploaded_at': datetime.now().isoformat(),
            }})
            return str(existing['_id'])
        count = await self.ref_files.count_documents({'book_id': book_id})
        r = await self.ref_files.insert_one({
            'book_id': book_id, 'lang': lang, 'volume': volume,
            'description': description, 'file_id': file_id,
            'uploaded_at': datetime.now().isoformat(), 'downloads': 0, 'order': count,
        })
        return str(r.inserted_id)

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
                           explanation: str, creator: int, auto_approve: bool = False):
        r = await self.questions.insert_one({
            'lesson': lesson, 'topic': topic, 'difficulty': difficulty,
            'question': question, 'options': options, 'correct_answer': correct,
            'explanation': explanation, 'creator_id': creator,
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

    async def get_questions_for_pdf(self, lesson: str = None, topic: str = None, count: int = 20):
        q = {'approved': True}
        if lesson: q['lesson'] = lesson
        if topic and topic != 'همه': q['topic'] = topic
        return await self.questions.find(q).to_list(count)

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

    async def get_schedules(self, stype: str = None, upcoming: bool = True, group: str = None):
        q = {}
        if stype:    q['type'] = stype
        if upcoming: q['date'] = {'$gte': datetime.now().strftime('%Y-%m-%d')}
        if group:
            q['$or'] = [{'group': group}, {'group': 'هر دو'}, {'group': {'$exists': False}}]
        return await self.schedules.find(q).sort('date', 1).to_list(200)

    async def delete_schedule(self, sid: str):
        try:
            await self.schedules.delete_one({'_id': ObjectId(sid)})
        except Exception: pass

    async def upcoming_exams(self, days: int = 7):
        today  = datetime.now().strftime('%Y-%m-%d')
        future = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
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
        )
        keys = [
            'users','pending','questions','qbank_files',
            'bs_lessons','bs_sessions','bs_content',
            'ref_subjects','ref_books','open_tickets','content_admins',
        ]
        d = dict(zip(keys, vals))
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

    async def new_resources_count(self, days: int = 7) -> int:
        since = (datetime.now() - timedelta(days=days)).isoformat()
        bs, refs = await asyncio.gather(
            self.bs_content.count_documents({'uploaded_at': {'$gt': since}}),
            self.ref_files.count_documents({'uploaded_at': {'$gt': since}}),
        )
        return bs + refs


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
    }

    # ماتریس مجوزها برای هر نقش — استفاده در has_permission
    ROLE_PERMISSIONS = {
        'support':        {'tickets'},
        'content_admin':  {'content', 'questions_review'},
        'content_scoped': {'content_scoped', 'questions_review_scoped'},
        'broadcaster':    {'broadcast'},
        'reviewer':       {'reports_review'},                          # FIX جدید
        'bot_admin':      {'users', 'schedules', 'notifications'},      # FIX جدید
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

    async def log_action(self, actor_id: int, actor_name: str, actor_role: str,
                          action: str, module: str, category: str = 'admin',
                          severity: str = 'INFO', target_id: str = '',
                          before: dict = None, after: dict = None,
                          details: str = '') -> None:
        """
        FIX جدید — ساختار کامل Audit Log طبق استاندارد حرفه‌ای:
        زمان، شناسه/نام/رول ادمین، نوع عملیات، ماژول، هدف،
        تغییرات قبل/بعد (در صورت وجود)، و severity.

        category: 'admin' یا 'content' — کدام گروه تلگرام لاگ را ببیند.
        severity: INFO / WARNING / HIGH / CRITICAL
        before/after: dict ساده مثل {'field': 'status', 'value': 'open'}
        برای نگه‌داشتن مقدار قبل و بعد تغییر — نه کل سند.
        """
        await self.audit_logs.insert_one({
            'actor_id':   actor_id,
            'actor_name': actor_name,
            'actor_role': actor_role,
            'action':     action,
            'module':     module,
            'category':   category,
            'severity':   severity,
            'target_id':  target_id,
            'before':     before or {},
            'after':      after or {},
            'details':    details,
            'at':         datetime.now().isoformat(),
        })

    async def get_recent_logs(self, category: str = None, min_severity: str = None,
                               limit: int = 30) -> list:
        q = {}
        if category:
            q['category'] = category
        if min_severity:
            order = ['INFO', 'WARNING', 'HIGH', 'CRITICAL']
            idx = order.index(min_severity) if min_severity in order else 0
            q['severity'] = {'$in': order[idx:]}
        return await self.audit_logs.find(q).sort('at', -1).to_list(limit)

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
        all_appr = await self.users.find({'approved': True}).to_list(5000)
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


db = DB()

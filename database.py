"""
🗄️ Database — نسخه نهایی بهینه‌شده
  ✅ MONGODB_URI اجباری
  ✅ ensure_indexes برای سرعت
  ✅ weekly_activity برای نمودار آمار
  ✅ get_leaderboard برای جدول برترین‌ها
  ✅ search_resources برای جستجوی محتوا
  ✅ تمام متدهای مورد نیاز همه ماژول‌ها
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
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            maxPoolSize=50,
            minPoolSize=5,
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

    # ══════════════════════════════════════════════════
    #  ایندکس‌ها — فراخوانی یک‌بار در startup
    # ══════════════════════════════════════════════════

    async def ensure_indexes(self):
        """ایجاد ایندکس‌های بهینه برای سرعت کوئری"""
        try:
            await asyncio.gather(
                self.users.create_index('user_id', unique=True, background=True),
                self.users.create_index('approved', background=True),
                self.users.create_index('role', background=True),
                self.users.create_index('registered_at', background=True),

                self.questions.create_index('approved', background=True),
                self.questions.create_index([('lesson', 1), ('topic', 1)], background=True),
                self.questions.create_index('creator_id', background=True),

                self.bs_lessons.create_index([('term', 1), ('order', 1)], background=True),
                self.bs_sessions.create_index([('lesson_id', 1), ('number', 1)], background=True),
                self.bs_content.create_index([('session_id', 1), ('order', 1)], background=True),

                self.ref_subjects.create_index('order', background=True),
                self.ref_books.create_index([('subject_id', 1), ('order', 1)], background=True),
                self.ref_files.create_index([('book_id', 1), ('lang', 1), ('volume', 1)], background=True),

                self.schedules.create_index([('date', 1), ('type', 1)], background=True),
                self.schedules.create_index('group', background=True),

                self.stats_col.create_index([('user_id', 1), ('timestamp', -1)], background=True),
                self.stats_col.create_index('action', background=True),

                self.tickets.create_index('ticket_id', unique=True, background=True),
                self.tickets.create_index([('user_id', 1), ('status', 1)], background=True),
                self.tickets.create_index('status', background=True),

                self.qbank_files.create_index([('lesson', 1), ('topic', 1)], background=True),
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
                          group: str, username: str = None):
        doc = {
            'user_id':    uid,
            'name':       name,
            'student_id': student_id,
            'group':      group,
            'username':   username,
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
        }
        await self.users.insert_one(doc)

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
        return bool(u and u.get('role') in ('content_admin', 'admin'))

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
        """جدول برترین‌ها بر اساس پاسخ صحیح"""
        return await self.users.find(
            {'approved': True, 'total_answers': {'$gt': 0}}
        ).sort('correct_answers', -1).limit(limit).to_list(limit)

    # ══════════════════════════════════════════════════
    #  علوم پایه — درس‌ها
    # ══════════════════════════════════════════════════

    async def bs_get_lessons(self, term: str):
        return await self.bs_lessons.find(
            {'term': term}
        ).sort('order', 1).to_list(50)

    async def bs_add_lesson(self, term: str, name: str, teacher: str = ''):
        if await self.bs_lessons.find_one({'term': term, 'name': name}):
            return None
        count = await self.bs_lessons.count_documents({'term': term})
        r = await self.bs_lessons.insert_one({
            'term':       term,
            'name':       name,
            'teacher':    teacher,
            'order':      count,
            'created_at': datetime.now().isoformat(),
        })
        return r.inserted_id

    async def bs_get_lesson(self, lesson_id: str):
        try:
            return await self.bs_lessons.find_one({'_id': ObjectId(lesson_id)})
        except Exception:
            return None

    async def bs_update_lesson(self, lesson_id: str, data: dict) -> bool:
        try:
            await self.bs_lessons.update_one(
                {'_id': ObjectId(lesson_id)}, {'$set': data}
            )
            return True
        except Exception:
            return False

    async def bs_delete_lesson(self, lesson_id: str):
        try:
            await self.bs_lessons.delete_one({'_id': ObjectId(lesson_id)})
            sessions = await self.bs_sessions.find(
                {'lesson_id': lesson_id}
            ).to_list(200)
            for s in sessions:
                await self.bs_content.delete_many({'session_id': str(s['_id'])})
            await self.bs_sessions.delete_many({'lesson_id': lesson_id})
        except Exception as e:
            logger.warning(f"bs_delete_lesson: {e}")

    # ══════════════════════════════════════════════════
    #  علوم پایه — جلسات
    # ══════════════════════════════════════════════════

    async def bs_get_sessions(self, lesson_id: str):
        return await self.bs_sessions.find(
            {'lesson_id': lesson_id}
        ).sort('number', 1).to_list(200)

    async def bs_add_session(self, lesson_id: str, number: int,
                             topic: str, teacher: str):
        existing = await self.bs_sessions.find_one(
            {'lesson_id': lesson_id, 'number': number}
        )
        if existing:
            await self.bs_sessions.update_one(
                {'_id': existing['_id']},
                {'$set': {'topic': topic, 'teacher': teacher}}
            )
            return str(existing['_id'])
        r = await self.bs_sessions.insert_one({
            'lesson_id':  lesson_id,
            'number':     number,
            'topic':      topic,
            'teacher':    teacher,
            'created_at': datetime.now().isoformat(),
        })
        return str(r.inserted_id)

    async def bs_get_session(self, sid: str):
        try:
            return await self.bs_sessions.find_one({'_id': ObjectId(sid)})
        except Exception:
            return None

    async def bs_update_session(self, session_id: str, data: dict) -> bool:
        try:
            await self.bs_sessions.update_one(
                {'_id': ObjectId(session_id)}, {'$set': data}
            )
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
        return await self.bs_content.find(
            {'session_id': session_id}
        ).sort('order', 1).to_list(50)

    async def bs_add_content(self, session_id: str, ctype: str, file_id: str,
                             description: str = '', extra_info: str = ''):
        count = await self.bs_content.count_documents({'session_id': session_id})
        r = await self.bs_content.insert_one({
            'session_id':  session_id,
            'type':        ctype,
            'file_id':     file_id,
            'description': description,
            'extra_info':  extra_info,
            'order':       count,
            'uploaded_at': datetime.now().isoformat(),
            'downloads':   0,
        })
        return r.inserted_id

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
            await self.bs_content.update_one(
                {'_id': ObjectId(cid)}, {'$inc': {'downloads': 1}}
            )
        except Exception:
            pass
        await self.log(uid, 'bs_download', {'content_id': cid})

    # ══════════════════════════════════════════════════
    #  جستجو در محتوای علوم پایه
    # ══════════════════════════════════════════════════

    async def search_resources(self, query_text: str):
        """جستجو در موضوع جلسات و توضیح فایل‌ها"""
        regex = {'$regex': query_text, '$options': 'i'}
        # جستجو در جلسات
        sessions = await self.bs_sessions.find(
            {'$or': [{'topic': regex}, {'teacher': regex}]}
        ).to_list(20)

        result = []
        for s in sessions:
            sid      = str(s['_id'])
            contents = await self.bs_content.find(
                {'session_id': sid}
            ).to_list(10)
            for c in contents:
                c['_session'] = s
                result.append(c)

        # جستجو مستقیم در توضیح فایل‌ها
        direct = await self.bs_content.find(
            {'description': regex}
        ).to_list(10)
        existing_ids = {str(r['_id']) for r in result}
        for c in direct:
            if str(c['_id']) not in existing_ids:
                sid = c.get('session_id', '')
                try:
                    c['_session'] = await self.bs_get_session(sid) or {}
                except Exception:
                    c['_session'] = {}
                result.append(c)

        return result[:15]

    # ══════════════════════════════════════════════════
    #  ترتیب‌بندی (Reorder)
    # ══════════════════════════════════════════════════

    async def _normalize_order(self, col, query_filter: dict):
        items = await col.find(query_filter).to_list(1000)
        items.sort(key=lambda x: (x.get('order', 99999), str(x['_id'])))
        updates = []
        for i, item in enumerate(items):
            if item.get('order') != i:
                updates.append(
                    col.update_one({'_id': item['_id']}, {'$set': {'order': i}})
                )
                item['order'] = i
        if updates:
            await asyncio.gather(*updates)
        return items

    async def reorder_up(self, collection: str, doc_id: str,
                         query_filter: dict) -> bool:
        try:
            col   = getattr(self, collection)
            items = await self._normalize_order(col, query_filter)
            ids   = [str(it['_id']) for it in items]
            if doc_id not in ids:
                return False
            idx = ids.index(doc_id)
            if idx == 0:
                return False
            await asyncio.gather(
                col.update_one({'_id': items[idx]['_id']},     {'$set': {'order': idx - 1}}),
                col.update_one({'_id': items[idx - 1]['_id']}, {'$set': {'order': idx}}),
            )
            return True
        except Exception as e:
            logger.warning(f"reorder_up: {e}")
            return False

    async def reorder_down(self, collection: str, doc_id: str,
                           query_filter: dict) -> bool:
        try:
            col   = getattr(self, collection)
            items = await self._normalize_order(col, query_filter)
            ids   = [str(it['_id']) for it in items]
            if doc_id not in ids:
                return False
            idx = ids.index(doc_id)
            if idx >= len(items) - 1:
                return False
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
            items = await self._normalize_order(
                self.bs_content, {'session_id': session_id}
            )
            ids = [str(it['_id']) for it in items]
            if content_id not in ids:
                return False
            idx = ids.index(content_id)
            if idx == 0:
                return False
            await asyncio.gather(
                self.bs_content.update_one(
                    {'_id': items[idx]['_id']},     {'$set': {'order': idx - 1}}),
                self.bs_content.update_one(
                    {'_id': items[idx - 1]['_id']}, {'$set': {'order': idx}}),
            )
            return True
        except Exception:
            return False

    async def reorder_content_down(self, content_id: str, session_id: str) -> bool:
        try:
            items = await self._normalize_order(
                self.bs_content, {'session_id': session_id}
            )
            ids = [str(it['_id']) for it in items]
            if content_id not in ids:
                return False
            idx = ids.index(content_id)
            if idx >= len(items) - 1:
                return False
            await asyncio.gather(
                self.bs_content.update_one(
                    {'_id': items[idx]['_id']},     {'$set': {'order': idx + 1}}),
                self.bs_content.update_one(
                    {'_id': items[idx + 1]['_id']}, {'$set': {'order': idx}}),
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
        if await self.ref_subjects.find_one({'name': name}):
            return None
        count = await self.ref_subjects.count_documents({})
        r = await self.ref_subjects.insert_one({
            'name':       name,
            'order':      count,
            'created_at': datetime.now().isoformat(),
        })
        return r.inserted_id

    async def ref_get_subject(self, sid: str):
        try:
            return await self.ref_subjects.find_one({'_id': ObjectId(sid)})
        except Exception:
            return None

    async def ref_update_subject(self, subject_id: str, data: dict) -> bool:
        try:
            await self.ref_subjects.update_one(
                {'_id': ObjectId(subject_id)}, {'$set': data}
            )
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
        return await self.ref_books.find(
            {'subject_id': subject_id}
        ).sort('order', 1).to_list(50)

    async def ref_add_book(self, subject_id: str, name: str):
        count = await self.ref_books.count_documents({'subject_id': subject_id})
        r = await self.ref_books.insert_one({
            'subject_id': subject_id,
            'name':       name,
            'order':      count,
            'created_at': datetime.now().isoformat(),
        })
        return r.inserted_id

    async def ref_get_book(self, bid: str):
        try:
            return await self.ref_books.find_one({'_id': ObjectId(bid)})
        except Exception:
            return None

    async def ref_update_book(self, book_id: str, data: dict) -> bool:
        try:
            await self.ref_books.update_one(
                {'_id': ObjectId(book_id)}, {'$set': data}
            )
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
        return await self.ref_files.find(
            {'book_id': book_id}
        ).sort('order', 1).to_list(20)

    async def ref_add_file(self, book_id: str, lang: str, file_id: str,
                           volume: int = 1, description: str = ''):
        existing = await self.ref_files.find_one(
            {'book_id': book_id, 'lang': lang, 'volume': volume}
        )
        if existing:
            await self.ref_files.update_one(
                {'_id': existing['_id']},
                {'$set': {
                    'file_id':     file_id,
                    'description': description,
                    'uploaded_at': datetime.now().isoformat(),
                }}
            )
            return str(existing['_id'])
        count = await self.ref_files.count_documents({'book_id': book_id})
        r = await self.ref_files.insert_one({
            'book_id':     book_id,
            'lang':        lang,
            'volume':      volume,
            'description': description,
            'file_id':     file_id,
            'uploaded_at': datetime.now().isoformat(),
            'downloads':   0,
            'order':       count,
        })
        return str(r.inserted_id)

    async def ref_get_file(self, fid: str):
        try:
            return await self.ref_files.find_one({'_id': ObjectId(fid)})
        except Exception:
            return None

    async def ref_inc_download(self, fid: str, uid: int):
        try:
            await self.ref_files.update_one(
                {'_id': ObjectId(fid)}, {'$inc': {'downloads': 1}}
            )
        except Exception:
            pass
        await self.log(uid, 'ref_download', {'file_id': fid})

    async def ref_delete_file(self, fid: str):
        try:
            await self.ref_files.delete_one({'_id': ObjectId(fid)})
        except Exception:
            pass

    # ══════════════════════════════════════════════════
    #  بانک سوال — فایل‌ها
    # ══════════════════════════════════════════════════

    async def add_qbank_file(self, lesson: str, topic: str, file_id: str,
                             description: str, file_type: str = 'document'):
        r = await self.qbank_files.insert_one({
            'lesson':      lesson,
            'topic':       topic,
            'file_id':     file_id,
            'file_type':   file_type,
            'description': description,
            'upload_date': datetime.now().isoformat(),
            'downloads':   0,
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
            await self.qbank_files.update_one(
                {'_id': ObjectId(fid)}, {'$inc': {'downloads': 1}}
            )
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
                           explanation: str, creator: int,
                           auto_approve: bool = False):
        r = await self.questions.insert_one({
            'lesson':         lesson,
            'topic':          topic,
            'difficulty':     difficulty,
            'question':       question,
            'options':        options,
            'correct_answer': correct,
            'explanation':    explanation,
            'creator_id':     creator,
            'approved':       auto_approve,
            'created_at':     datetime.now().isoformat(),
            'attempt_count':  0,
            'correct_count':  0,
        })
        return r.inserted_id

    async def get_questions(self, lesson: str = None, topic: str = None,
                            difficulty: str = None, limit: int = 1,
                            exclude: list = None):
        q = {'approved': True}
        if lesson:    q['lesson'] = lesson
        if topic and topic != 'همه': q['topic'] = topic
        if difficulty: q['difficulty'] = difficulty
        if exclude:
            try:
                q['_id'] = {'$nin': [ObjectId(i) for i in exclude]}
            except Exception:
                pass
        return await self.questions.find(q).limit(limit).to_list(limit)

    async def get_weak_questions(self, uid: int, limit: int = 1):
        user = await self.get_user(uid)
        weak = user.get('weak_topics', []) if user else []
        if not weak:
            return await self.get_questions(limit=limit)
        return await self.questions.find(
            {'approved': True, 'topic': {'$in': weak}}
        ).limit(limit).to_list(limit)

    async def get_question_by_id(self, qid: str):
        try:
            return await self.questions.find_one({'_id': ObjectId(qid)})
        except Exception:
            return None

    async def get_questions_for_pdf(self, lesson: str = None,
                                    topic: str = None, count: int = 20):
        q = {'approved': True}
        if lesson: q['lesson'] = lesson
        if topic and topic != 'همه': q['topic'] = topic
        return await self.questions.find(q).to_list(count)

    async def pending_questions(self):
        return await self.questions.find({'approved': False}).to_list(50)

    async def approve_question(self, qid: str):
        try:
            await self.questions.update_one(
                {'_id': ObjectId(qid)}, {'$set': {'approved': True}}
            )
        except Exception:
            pass

    async def delete_question(self, qid: str):
        try:
            await self.questions.delete_one({'_id': ObjectId(qid)})
        except Exception:
            pass

    async def save_answer(self, uid: int, qid: str, selected: int,
                          is_correct: bool):
        await self.answers.insert_one({
            'user_id':     uid,
            'question_id': qid,
            'selected':    selected,
            'is_correct':  is_correct,
            'answered_at': datetime.now().isoformat(),
        })
        inc = {'total_answers': 1}
        if is_correct:
            inc['correct_answers'] = 1
        await self.users.update_one({'user_id': uid}, {'$inc': inc})
        try:
            await self.questions.update_one(
                {'_id': ObjectId(qid)},
                {'$inc': {
                    'attempt_count': 1,
                    'correct_count': 1 if is_correct else 0,
                }}
            )
        except Exception:
            pass
        if not is_correct:
            try:
                q_doc = await self.questions.find_one({'_id': ObjectId(qid)})
                if q_doc:
                    await self.users.update_one(
                        {'user_id': uid},
                        {'$addToSet': {'weak_topics': q_doc['topic']}}
                    )
            except Exception:
                pass
        await self.log(uid, 'answer', {'qid': qid, 'correct': is_correct})

    async def get_lessons(self):
        return await self.questions.distinct('lesson', {'approved': True})

    async def get_topics(self, lesson: str = None):
        q = {'approved': True}
        if lesson: q['lesson'] = lesson
        return await self.questions.distinct('topic', q)

    # ══════════════════════════════════════════════════
    #  برنامه
    # ══════════════════════════════════════════════════

    async def add_schedule(self, stype: str, lesson: str, teacher: str,
                           date: str, time: str, location: str,
                           notes: str = '', group: str = 'هر دو',
                           is_weekly: bool = False):
        r = await self.schedules.insert_one({
            'type':         stype,
            'lesson':       lesson,
            'teacher':      teacher,
            'date':         date,
            'time':         time,
            'location':     location,
            'notes':        notes,
            'group':        group,
            'is_weekly':    is_weekly,
            'created_at':   datetime.now().isoformat(),
            'notified_days': [],
        })
        return r.inserted_id

    async def get_schedules(self, stype: str = None, upcoming: bool = True,
                            group: str = None):
        q = {}
        if stype:    q['type'] = stype
        if upcoming: q['date'] = {'$gte': datetime.now().strftime('%Y-%m-%d')}
        if group:
            q['$or'] = [
                {'group': group},
                {'group': 'هر دو'},
                {'group': {'$exists': False}},
            ]
        return await self.schedules.find(q).sort('date', 1).to_list(200)

    async def delete_schedule(self, sid: str):
        try:
            await self.schedules.delete_one({'_id': ObjectId(sid)})
        except Exception:
            pass

    async def upcoming_exams(self, days: int = 7):
        today  = datetime.now().strftime('%Y-%m-%d')
        future = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
        return await self.schedules.find({
            'type': 'exam',
            'date': {'$gte': today, '$lte': future},
        }).sort('date', 1).to_list(20)

    async def get_exams_for_reminder(self, remind_days: int):
        target = (datetime.now() + timedelta(days=remind_days)).strftime('%Y-%m-%d')
        key    = f'd{remind_days}'
        return await self.schedules.find({
            'type': 'exam',
            'date': target,
            'notified_days': {'$ne': key},
        }).to_list(50)

    async def mark_exam_notified(self, sid: str, remind_days: int):
        key = f'd{remind_days}'
        try:
            await self.schedules.update_one(
                {'_id': ObjectId(sid)},
                {'$addToSet': {'notified_days': key}}
            )
        except Exception:
            pass

    # ══════════════════════════════════════════════════
    #  FAQ
    # ══════════════════════════════════════════════════

    async def faq_get_all(self):
        return await self.faq.find({}).sort('order', 1).to_list(100)

    async def faq_add(self, question: str, answer: str, category: str = 'عمومی'):
        count = await self.faq.count_documents({})
        await self.faq.insert_one({
            'question':   question,
            'answer':     answer,
            'category':   category,
            'order':      count,
            'created_at': datetime.now().isoformat(),
        })

    async def faq_delete(self, fid: str):
        try:
            await self.faq.delete_one({'_id': ObjectId(fid)})
        except Exception:
            pass

    async def faq_get_categories(self):
        docs = await self.faq.distinct('category')
        return docs or []

    # ══════════════════════════════════════════════════
    #  تیکت‌ها
    # ══════════════════════════════════════════════════

    async def ticket_create(self, uid: int, name: str, subject: str,
                            message: str) -> int:
        count = await self.tickets.count_documents({})
        tid   = count + 1
        await self.tickets.insert_one({
            'ticket_id':  tid,
            'user_id':    uid,
            'user_name':  name,
            'subject':    subject,
            'message':    message,
            'status':     'open',
            'created_at': datetime.now().isoformat(),
            'replies':    [],
        })
        return tid

    async def ticket_get(self, ticket_id: int):
        return await self.tickets.find_one({'ticket_id': ticket_id})

    async def ticket_get_all(self, status: str = None):
        q = {'status': status} if status else {}
        return await self.tickets.find(q).sort('created_at', -1).to_list(100)

    async def ticket_get_user(self, uid: int):
        return await self.tickets.find(
            {'user_id': uid}
        ).sort('created_at', -1).to_list(20)

    async def ticket_add_reply(self, ticket_id: int, reply_text: str):
        await self.tickets.update_one(
            {'ticket_id': ticket_id},
            {
                '$push': {'replies': {
                    'text': reply_text,
                    'at':   datetime.now().isoformat(),
                }},
                '$set': {'last_reply_at': datetime.now().isoformat()},
            }
        )

    async def ticket_reply(self, ticket_id: int, reply: str):
        """alias برای سازگاری"""
        await self.ticket_add_reply(ticket_id, reply)

    async def ticket_close(self, ticket_id: int):
        await self.tickets.update_one(
            {'ticket_id': ticket_id},
            {'$set': {
                'status':    'closed',
                'closed_at': datetime.now().isoformat(),
            }}
        )

    # ══════════════════════════════════════════════════
    #  آمار
    # ══════════════════════════════════════════════════

    async def log(self, uid: int, action: str, data: dict = None):
        await self.stats_col.insert_one({
            'user_id':   uid,
            'action':    action,
            'data':      data or {},
            'timestamp': datetime.now().isoformat(),
        })

    async def user_stats(self, uid: int) -> dict:
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        week_act, downloads, user = await asyncio.gather(
            self.stats_col.count_documents({
                'user_id':   uid,
                'timestamp': {'$gt': week_ago},
            }),
            self.stats_col.count_documents({
                'user_id': uid,
                'action':  {'$in': ['bs_download', 'ref_download', 'qbank_download']},
            }),
            self.get_user(uid),
        )
        total   = user.get('total_answers', 0)   if user else 0
        correct = user.get('correct_answers', 0) if user else 0
        pct     = round(correct / total * 100, 1) if total > 0 else 0
        return {
            'downloads':      downloads,
            'total_answers':  total,
            'correct_answers': correct,
            'percentage':     pct,
            'week_activity':  week_act,
            'weak_topics':    user.get('weak_topics', []) if user else [],
        }

    async def weekly_activity(self, uid: int) -> list:
        """فعالیت ۷ روز گذشته به صورت [(تاریخ, تعداد)]"""
        result = []
        for i in range(6, -1, -1):
            day   = datetime.now() - timedelta(days=i)
            start = day.replace(hour=0, minute=0, second=0,
                                microsecond=0).isoformat()
            end   = day.replace(hour=23, minute=59, second=59,
                                microsecond=999999).isoformat()
            count = await self.stats_col.count_documents({
                'user_id':   uid,
                'timestamp': {'$gte': start, '$lte': end},
            })
            result.append((day.strftime('%m/%d'), count))
        return result

    async def global_stats(self) -> dict:
        week_ago  = (datetime.now() - timedelta(days=7)).isoformat()
        new_users = await self.users.count_documents(
            {'registered_at': {'$gt': week_ago}}
        )
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
            'users', 'pending', 'questions', 'qbank_files',
            'bs_lessons', 'bs_sessions', 'bs_content',
            'ref_subjects', 'ref_books', 'open_tickets', 'content_admins',
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
        counts = await asyncio.gather(
            *[col.count_documents(q) for _, col, q in keys_content]
        )
        result = {k: v for (k, col, q), v in zip(keys_content, counts)}

        pipeline   = [{'$group': {'_id': None, 'total': {'$sum': '$downloads'}}}]
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
    #  منابع درسی (resources.py)
    #  FIX: این متدها قبلاً وجود نداشتند — باعث کرش می‌شدند
    # ══════════════════════════════════════════════════

    async def add_resource(self, term: str, lesson: str, topic: str,
                           rtype: str, file_id: str, metadata: dict):
        """اضافه کردن منبع درسی جدید"""
        r = await self.bs_content.insert_one({
            'term':        term,
            'lesson':      lesson,
            'topic':       topic,
            'type':        rtype,
            'file_id':     file_id,
            'metadata':    metadata,
            'upload_date': datetime.now().isoformat(),
        })
        return r.inserted_id

    async def get_resources(self, term: str = None, lesson: str = None,
                             topic: str = None, rtype: str = None):
        """دریافت منابع با فیلتر"""
        q = {}
        if term   and term   != 'همه': q['term']   = term
        if lesson and lesson != 'همه': q['lesson'] = lesson
        if topic  and topic  != 'همه': q['topic']  = topic
        if rtype  and rtype  != 'همه': q['type']   = rtype
        return await self.bs_content.find(q).sort('upload_date', -1).to_list(50)

    async def get_resource(self, rid: str):
        """دریافت یک منبع با ID"""
        try:
            return await self.bs_content.find_one({'_id': ObjectId(rid)})
        except Exception:
            return None

    async def inc_download(self, rid: str, uid: int):
        """افزایش شمارنده دانلود منبع"""
        try:
            await self.bs_content.update_one(
                {'_id': ObjectId(rid)},
                {'$inc': {'metadata.downloads': 1}}
            )
        except Exception:
            pass
        await self.log(uid, 'resource_download', {'resource_id': rid})

    # ══════════════════════════════════════════════════
    #  ویدیوهای کلاس (archive.py)
    #  FIX: این متدها قبلاً وجود نداشتند
    # ══════════════════════════════════════════════════

    async def add_video(self, lesson: str, topic: str, teacher: str,
                        date: str, file_id: str, description: str = ''):
        """اضافه کردن ویدیوی کلاس"""
        r = await self.bs_content.insert_one({
            'lesson':      lesson,
            'topic':       topic,
            'teacher':     teacher,
            'date':        date,
            'file_id':     file_id,
            'description': description,
            'type':        'video',
            'upload_date': datetime.now().isoformat(),
            'downloads':   0,
        })
        return r.inserted_id

    async def get_videos(self, lesson: str = None, topic: str = None):
        """دریافت لیست ویدیوها"""
        q = {'type': 'video'}
        if lesson: q['lesson'] = lesson
        if topic:  q['topic']  = topic
        return await self.bs_content.find(q).sort('date', -1).to_list(100)

    async def get_video(self, vid: str):
        """دریافت یک ویدیو با ID"""
        try:
            return await self.bs_content.find_one({'_id': ObjectId(vid)})
        except Exception:
            return None


db = DB()

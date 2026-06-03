import os
import motor.motor_asyncio
from datetime import datetime, timedelta
from bson import ObjectId


class DB:
    def __init__(self):
        # === اتصال به MongoDB سرور ترکیه ===
        uri = os.getenv('MONGODB_URI')
        if not uri:
            raise ValueError("❌ MONGODB_URI در متغیرهای محیطی (Railway) تنظیم نشده است!")

        self.client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        
        # اسم دیتابیس دقیقاً مطابق چیزی که ساختی
        _db = self.client['medicalbot']          # ← مهم: medicalbot (نه medical_bot)

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

    # ====================== توابع کاربر ======================
    async def get_user(self, uid):
        return await self.users.find_one({'user_id': uid})

    async def create_user(self, uid, name, student_id, group, username=None):
        await self.users.insert_one({
            'user_id': uid,
            'name': name,
            'student_id': student_id,
            'group': group,
            'username': username,
            'registered_at': datetime.now().isoformat(),
            'approved': False,
            'role': 'student',
            'notification_settings': {
                'new_resources': True,
                'schedule': True,
                'exam': True,
                'daily_question': False
            },
            'total_answers': 0,
            'correct_answers': 0,
            'weak_topics': []
        })

    async def update_user(self, uid, data):
        await self.users.update_one({'user_id': uid}, {'$set': data})

    async def delete_user(self, uid):
        await self.users.delete_one({'user_id': uid})

    async def all_users(self, approved_only=True):
        q = {'approved': True} if approved_only else {}
        return await self.users.find(q).sort('registered_at', -1).to_list(5000)

    async def pending_users(self):
        return await self.users.find({'approved': False}).to_list(100)

    async def notif_users(self, ntype):
        return await self.users.find(
            {'approved': True, f'notification_settings.{ntype}': True}
        ).to_list(5000)

    async def get_content_admins(self):
        return await self.users.find({'role': 'content_admin', 'approved': True}).to_list(100)

    async def is_content_admin(self, uid):
        if uid == int(os.getenv('ADMIN_ID', '0')):
            return True
        u = await self.get_user(uid)
        return u and u.get('role') in ('content_admin', 'admin')

    async def search_users(self, query_text):
        regex = {'$regex': query_text, '$options': 'i'}
        return await self.users.find(
            {'$or': [{'name': regex}, {'student_id': regex}, {'username': regex}]}
        ).to_list(20)

    # ====================== علوم پایه ======================
    async def bs_get_lessons(self, term):
        return await self.bs_lessons.find({'term': term}).sort('order', 1).to_list(50)

    async def bs_add_lesson(self, term, name, teacher=''):
        if await self.bs_lessons.find_one({'term': term, 'name': name}):
            return None
        count = await self.bs_lessons.count_documents({'term': term})
        r = await self.bs_lessons.insert_one({
            'term': term, 'name': name, 'teacher': teacher,
            'order': count, 'created_at': datetime.now().isoformat()
        })
        return r.inserted_id

    async def bs_delete_lesson(self, lesson_id):
        try:
            await self.bs_lessons.delete_one({'_id': ObjectId(lesson_id)})
            sessions = await self.bs_sessions.find({'lesson_id': lesson_id}).to_list(200)
            for s in sessions:
                await self.bs_content.delete_many({'session_id': str(s['_id'])})
            await self.bs_sessions.delete_many({'lesson_id': lesson_id})
        except:
            pass

    async def bs_get_lesson(self, lesson_id):
        try:
            return await self.bs_lessons.find_one({'_id': ObjectId(lesson_id)})
        except:
            return None

    async def bs_get_sessions(self, lesson_id):
        return await self.bs_sessions.find({'lesson_id': lesson_id}).sort('number', 1).to_list(200)

    async def bs_add_session(self, lesson_id, number, topic, teacher):
        existing = await self.bs_sessions.find_one({'lesson_id': lesson_id, 'number': number})
        if existing:
            await self.bs_sessions.update_one({'_id': existing['_id']},
                                              {'$set': {'topic': topic, 'teacher': teacher}})
            return str(existing['_id'])
        r = await self.bs_sessions.insert_one({
            'lesson_id': lesson_id, 'number': number, 'topic': topic,
            'teacher': teacher, 'created_at': datetime.now().isoformat()
        })
        return str(r.inserted_id)

    async def bs_get_session(self, sid):
        try:
            return await self.bs_sessions.find_one({'_id': ObjectId(sid)})
        except:
            return None

    async def bs_delete_session(self, sid):
        try:
            await self.bs_sessions.delete_one({'_id': ObjectId(sid)})
            await self.bs_content.delete_many({'session_id': sid})
        except:
            pass

    async def bs_get_content(self, session_id):
        return await self.bs_content.find({'session_id': session_id}).sort('order', 1).to_list(50)

    async def bs_add_content(self, session_id, ctype, file_id, description='', extra_info=''):
        count = await self.bs_content.count_documents({'session_id': session_id})
        r = await self.bs_content.insert_one({
            'session_id': session_id,
            'type': ctype,
            'file_id': file_id,
            'description': description,
            'extra_info': extra_info,
            'order': count,
            'uploaded_at': datetime.now().isoformat(),
            'downloads': 0
        })
        return r.inserted_id

    async def bs_delete_content(self, cid):
        try:
            await self.bs_content.delete_one({'_id': ObjectId(cid)})
        except:
            pass

    async def bs_get_content_item(self, cid):
        try:
            return await self.bs_content.find_one({'_id': ObjectId(cid)})
        except:
            return None

    async def bs_inc_download(self, cid, uid):
        try:
            await self.bs_content.update_one({'_id': ObjectId(cid)}, {'$inc': {'downloads': 1}})
        except:
            pass
        await self.log(uid, 'bs_download', {'content_id': cid})

    # ====================== رفرنس‌ها ======================
    async def ref_get_subjects(self):
        return await self.ref_subjects.find({}).sort('order', 1).to_list(100)

    async def ref_add_subject(self, name):
        if await self.ref_subjects.find_one({'name': name}):
            return None
        count = await self.ref_subjects.count_documents({})
        r = await self.ref_subjects.insert_one({
            'name': name, 'order': count, 'created_at': datetime.now().isoformat()
        })
        return r.inserted_id

    async def ref_delete_subject(self, sid):
        try:
            await self.ref_subjects.delete_one({'_id': ObjectId(sid)})
            books = await self.ref_books.find({'subject_id': sid}).to_list(100)
            for b in books:
                await self.ref_files.delete_many({'book_id': str(b['_id'])})
            await self.ref_books.delete_many({'subject_id': sid})
        except:
            pass

    # ====================== بانک سوال ======================
    async def add_qbank_file(self, lesson, topic, file_id, description, file_type='document'):
        r = await self.qbank_files.insert_one({
            'lesson': lesson,
            'topic': topic,
            'file_id': file_id,
            'file_type': file_type,
            'description': description,
            'upload_date': datetime.now().isoformat(),
            'downloads': 0
        })
        return r.inserted_id

    async def get_qbank_files(self, lesson=None, topic=None):
        q = {}
        if lesson: q['lesson'] = lesson
        if topic: q['topic'] = topic
        return await self.qbank_files.find(q).sort('upload_date', -1).to_list(100)

    async def delete_qbank_file(self, fid):
        try:
            await self.qbank_files.delete_one({'_id': ObjectId(fid)})
        except:
            pass

    # ====================== تیکت ======================
    async def ticket_create(self, uid, name, subject, message):
        count = await self.tickets.count_documents({})
        r = await self.tickets.insert_one({
            'ticket_id': count + 1,
            'user_id': uid,
            'user_name': name,
            'subject': subject,
            'message': message,
            'status': 'open',
            'created_at': datetime.now().isoformat(),
            'replies': []
        })
        return count + 1

    async def ticket_add_reply(self, ticket_id, reply_text):
        await self.tickets.update_one(
            {'ticket_id': ticket_id},
            {
                '$push': {'replies': {'text': reply_text, 'at': datetime.now().isoformat()}},
                '$set': {'last_reply_at': datetime.now().isoformat()}
            }
        )

    async def ticket_close(self, ticket_id):
        await self.tickets.update_one(
            {'ticket_id': ticket_id},
            {'$set': {'status': 'closed', 'closed_at': datetime.now().isoformat()}}
        )

    async def ticket_get(self, ticket_id):
        return await self.tickets.find_one({'ticket_id': ticket_id})

    # ====================== آمار ======================
    async def global_stats(self):
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        new_users = await self.users.count_documents({'registered_at': {'$gt': week_ago}})
        return {
            'users': await self.users.count_documents({'approved': True}),
            'pending': await self.users.count_documents({'approved': False}),
            'questions': await self.questions.count_documents({'approved': True}),
            'qbank_files': await self.qbank_files.count_documents({}),
            'bs_lessons': await self.bs_lessons.count_documents({}),
            'bs_sessions': await self.bs_sessions.count_documents({}),
            'bs_content': await self.bs_content.count_documents({}),
            'ref_subjects': await self.ref_subjects.count_documents({}),
            'ref_books': await self.ref_books.count_documents({}),
            'open_tickets': await self.tickets.count_documents({'status': 'open'}),
            'content_admins': await self.users.count_documents({'role': 'content_admin'}),
            'new_users_week': new_users
        }

    async def user_stats(self, uid):
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        week_act = await self.stats_col.count_documents({'user_id': uid, 'timestamp': {'$gt': week_ago}})
        downloads = await self.stats_col.count_documents({
            'user_id': uid,
            'action': {'$in': ['bs_download', 'ref_download', 'qbank_download']}
        })
        user = await self.get_user(uid)
        total = user.get('total_answers', 0) if user else 0
        correct = user.get('correct_answers', 0) if user else 0
        pct = round(correct / total * 100, 1) if total > 0 else 0
        return {
            'downloads': downloads,
            'total_answers': total,
            'correct_answers': correct,
            'percentage': pct,
            'week_activity': week_act,
            'weak_topics': user.get('weak_topics', []) if user else []
        }

    async def log(self, uid, action, data=None):
        await self.stats_col.insert_one({
            'user_id': uid,
            'action': action,
            'data': data or {},
            'timestamp': datetime.now().isoformat()
        })


#インスタンス جهانی
db = DB()

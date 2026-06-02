import os
import motor.motor_asyncio
from datetime import datetime, timedelta
from bson import ObjectId


class DB:
    def __init__(self):
        uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
        self.client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        _db = self.client['medical_bot']
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

    async def get_user(self, uid):
        return await self.users.find_one({'user_id': uid})

    async def create_user(self, uid, name, student_id, group, username=None):
        await self.users.insert_one({
            'user_id': uid, 'name': name, 'student_id': student_id,
            'group': group, 'username': username,
            'registered_at': datetime.now().isoformat(),
            'approved': False, 'role': 'student',
            'notification_settings': {
                'new_resources': True, 'schedule': True,
                'exam': True, 'daily_question': False
            },
            'total_answers': 0, 'correct_answers': 0, 'weak_topics': []
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

    async def bs_get_lessons(self, term):
        return await self.bs_lessons.find({'term': term}).sort('order', 1).to_list(50)

    async def bs_add_lesson(self, term, name, teacher=''):
        if await self.bs_lessons.find_one({'term': term, 'name': name}):
            return None
        count = await self.bs_lessons.count_documents({'term': term})
        r = await self.bs_lessons.insert_one({'term': term, 'name': name, 'teacher': teacher, 'order': count, 'created_at': datetime.now().isoformat()})
        return r.inserted_id

    async def bs_delete_lesson(self, lesson_id):
        try:
            await self.bs_lessons.delete_one({'_id': ObjectId(lesson_id)})
            sessions = await self.bs_sessions.find({'lesson_id': lesson_id}).to_list(200)
            for s in sessions:
                await self.bs_content.delete_many({'session_id': str(s['_id'])})
            await self.bs_sessions.delete_many({'lesson_id': lesson_id})
        except: pass

    async def bs_get_lesson(self, lesson_id):
        try: return await self.bs_lessons.find_one({'_id': ObjectId(lesson_id)})
        except: return None

    async def bs_get_sessions(self, lesson_id):
        return await self.bs_sessions.find({'lesson_id': lesson_id}).sort('number', 1).to_list(200)

    async def bs_add_session(self, lesson_id, number, topic, teacher):
        existing = await self.bs_sessions.find_one({'lesson_id': lesson_id, 'number': number})
        if existing:
            await self.bs_sessions.update_one({'_id': existing['_id']}, {'$set': {'topic': topic, 'teacher': teacher}})
            return str(existing['_id'])
        r = await self.bs_sessions.insert_one({'lesson_id': lesson_id, 'number': number, 'topic': topic, 'teacher': teacher, 'created_at': datetime.now().isoformat()})
        return str(r.inserted_id)

    async def bs_get_session(self, sid):
        try: return await self.bs_sessions.find_one({'_id': ObjectId(sid)})
        except: return None

    async def bs_delete_session(self, sid):
        try:
            await self.bs_sessions.delete_one({'_id': ObjectId(sid)})
            await self.bs_content.delete_many({'session_id': sid})
        except: pass

    async def bs_get_content(self, session_id):
        return await self.bs_content.find({'session_id': session_id}).sort('order', 1).to_list(50)

    async def bs_add_content(self, session_id, ctype, file_id, description='', extra_info=''):
        count = await self.bs_content.count_documents({'session_id': session_id})
        r = await self.bs_content.insert_one({'session_id': session_id, 'type': ctype, 'file_id': file_id, 'description': description, 'extra_info': extra_info, 'order': count, 'uploaded_at': datetime.now().isoformat(), 'downloads': 0})
        return r.inserted_id

    async def bs_delete_content(self, cid):
        try: await self.bs_content.delete_one({'_id': ObjectId(cid)})
        except: pass

    async def bs_get_content_item(self, cid):
        try: return await self.bs_content.find_one({'_id': ObjectId(cid)})
        except: return None

    async def bs_inc_download(self, cid, uid):
        try: await self.bs_content.update_one({'_id': ObjectId(cid)}, {'$inc': {'downloads': 1}})
        except: pass
        await self.log(uid, 'bs_download', {'content_id': cid})


    async def bs_update_lesson(self, lesson_id, data: dict):
        try:
            await self.bs_lessons.update_one({'_id': ObjectId(lesson_id)}, {'$set': data})
            return True
        except: return False

    async def bs_update_session(self, session_id, data: dict):
        try:
            await self.bs_sessions.update_one({'_id': ObjectId(session_id)}, {'$set': data})
            return True
        except: return False

    async def ref_update_subject(self, subject_id, data: dict):
        try:
            await self.ref_subjects.update_one({'_id': ObjectId(subject_id)}, {'$set': data})
            return True
        except: return False

    async def ref_update_book(self, book_id, data: dict):
        try:
            await self.ref_books.update_one({'_id': ObjectId(book_id)}, {'$set': data})
            return True
        except: return False


    # ════ ترتیب‌بندی (Reorder) ════

    async def _normalize_order(self, col, query_filter):
        """همه آیتم‌ها رو sort کن و order رو از 0 بده — همیشه اجرا میشه"""
        # اول بر اساس order موجود sort کن، اگه نداشتن بر اساس _id
        items = await col.find(query_filter).to_list(1000)
        # sort: اول اونایی که order دارن، بقیه آخر
        items.sort(key=lambda x: (x.get('order', 99999), str(x['_id'])))
        # همه order ها رو از صفر بنویس تا یکتا و پیوسته باشن
        for i, item in enumerate(items):
            if item.get('order') != i:
                await col.update_one({'_id': item['_id']}, {'$set': {'order': i}})
                item['order'] = i
        return items

    async def reorder_up(self, collection, doc_id, query_filter):
        """یک آیتم رو یه پله بالاتر بیار — با normalize خودکار"""
        from bson import ObjectId as OID
        try:
            col   = getattr(self, collection)
            items = await self._normalize_order(col, query_filter)
            ids   = [str(it['_id']) for it in items]
            if doc_id not in ids: return False
            idx = ids.index(doc_id)
            if idx == 0: return False
            # جابجایی با آیتم قبلی
            prev_id = items[idx - 1]['_id']
            curr_id = items[idx]['_id']
            await col.update_one({'_id': curr_id}, {'$set': {'order': idx - 1}})
            await col.update_one({'_id': prev_id}, {'$set': {'order': idx}})
            return True
        except Exception as e:
            return False

    async def reorder_down(self, collection, doc_id, query_filter):
        """یک آیتم رو یه پله پایین‌تر ببر — با normalize خودکار"""
        from bson import ObjectId as OID
        try:
            col   = getattr(self, collection)
            items = await self._normalize_order(col, query_filter)
            ids   = [str(it['_id']) for it in items]
            if doc_id not in ids: return False
            idx = ids.index(doc_id)
            if idx >= len(items) - 1: return False
            next_id = items[idx + 1]['_id']
            curr_id = items[idx]['_id']
            await col.update_one({'_id': curr_id}, {'$set': {'order': idx + 1}})
            await col.update_one({'_id': next_id}, {'$set': {'order': idx}})
            return True
        except Exception as e:
            return False

    async def reorder_content_up(self, content_id, session_id):
        """فایل محتوا رو بالاتر ببر — با normalize خودکار"""
        try:
            qf    = {'session_id': session_id}
            items = await self._normalize_order(self.bs_content, qf)
            ids   = [str(it['_id']) for it in items]
            if content_id not in ids: return False
            idx = ids.index(content_id)
            if idx == 0: return False
            await self.bs_content.update_one({'_id': items[idx]['_id']},     {'$set': {'order': idx - 1}})
            await self.bs_content.update_one({'_id': items[idx-1]['_id']},   {'$set': {'order': idx}})
            return True
        except: return False

    async def reorder_content_down(self, content_id, session_id):
        """فایل محتوا رو پایین‌تر ببر — با normalize خودکار"""
        try:
            qf    = {'session_id': session_id}
            items = await self._normalize_order(self.bs_content, qf)
            ids   = [str(it['_id']) for it in items]
            if content_id not in ids: return False
            idx = ids.index(content_id)
            if idx >= len(items) - 1: return False
            await self.bs_content.update_one({'_id': items[idx]['_id']},     {'$set': {'order': idx + 1}})
            await self.bs_content.update_one({'_id': items[idx+1]['_id']},   {'$set': {'order': idx}})
            return True
        except: return False

    async def ref_get_subjects(self):
        return await self.ref_subjects.find({}).sort('order', 1).to_list(100)

    async def ref_add_subject(self, name):
        if await self.ref_subjects.find_one({'name': name}): return None
        count = await self.ref_subjects.count_documents({})
        r = await self.ref_subjects.insert_one({'name': name, 'order': count, 'created_at': datetime.now().isoformat()})
        return r.inserted_id

    async def ref_delete_subject(self, sid):
        try:
            await self.ref_subjects.delete_one({'_id': ObjectId(sid)})
            books = await self.ref_books.find({'subject_id': sid}).to_list(100)
            for b in books:
                await self.ref_files.delete_many({'book_id': str(b['_id'])})
            await self.ref_books.delete_many({'subject_id': sid})
        except: pass

    async def ref_get_subject(self, sid):
        try: return await self.ref_subjects.find_one({'_id': ObjectId(sid)})
        except: return None

    async def ref_get_books(self, subject_id):
        return await self.ref_books.find({'subject_id': subject_id}).sort('order', 1).to_list(50)

    async def ref_add_book(self, subject_id, name):
        count = await self.ref_books.count_documents({'subject_id': subject_id})
        r = await self.ref_books.insert_one({'subject_id': subject_id, 'name': name, 'order': count, 'created_at': datetime.now().isoformat()})
        return r.inserted_id

    async def ref_delete_book(self, bid):
        try:
            await self.ref_books.delete_one({'_id': ObjectId(bid)})
            await self.ref_files.delete_many({'book_id': bid})
        except: pass

    async def ref_get_book(self, bid):
        try: return await self.ref_books.find_one({'_id': ObjectId(bid)})
        except: return None

    async def ref_get_files(self, book_id):
        return await self.ref_files.find({'book_id': book_id}).sort('order', 1).to_list(20)

    async def ref_add_file(self, book_id, lang, file_id, volume=1, description=''):
        """اضافه یا جایگزین کردن فایل — هر جلد جداست"""
        existing = await self.ref_files.find_one({'book_id': book_id, 'lang': lang, 'volume': volume})
        if existing:
            await self.ref_files.update_one({'_id': existing['_id']}, {'$set': {'file_id': file_id, 'description': description, 'uploaded_at': datetime.now().isoformat()}})
            return str(existing['_id'])
        count = await self.ref_files.count_documents({'book_id': book_id})
        r = await self.ref_files.insert_one({'book_id': book_id, 'lang': lang, 'volume': volume, 'description': description, 'file_id': file_id, 'uploaded_at': datetime.now().isoformat(), 'downloads': 0, 'order': count})
        return str(r.inserted_id)

    async def ref_get_file(self, fid):
        try: return await self.ref_files.find_one({'_id': ObjectId(fid)})
        except: return None

    async def ref_inc_download(self, fid, uid):
        try: await self.ref_files.update_one({'_id': ObjectId(fid)}, {'$inc': {'downloads': 1}})
        except: pass
        await self.log(uid, 'ref_download', {'file_id': fid})

    async def ref_delete_file(self, fid):
        try: await self.ref_files.delete_one({'_id': ObjectId(fid)})
        except: pass

    async def faq_get_all(self):
        return await self.faq.find({}).sort('order', 1).to_list(100)

    async def faq_add(self, question, answer, category='عمومی'):
        count = await self.faq.count_documents({})
        await self.faq.insert_one({'question': question, 'answer': answer, 'category': category, 'order': count, 'created_at': datetime.now().isoformat()})

    async def faq_delete(self, fid):
        try: await self.faq.delete_one({'_id': ObjectId(fid)})
        except: pass

    async def faq_get_categories(self):
        docs = await self.faq.distinct('category')
        return docs if docs else []

    async def ticket_create(self, uid, name, subject, message):
        count = await self.tickets.count_documents({})
        r = await self.tickets.insert_one({
            'ticket_id': count + 1, 'user_id': uid, 'user_name': name,
            'subject': subject, 'message': message, 'status': 'open',
            'created_at': datetime.now().isoformat(), 'reply': None, 'replied_at': None
        })
        return count + 1

    async def ticket_get_all(self, status=None):
        q = {'status': status} if status else {}
        return await self.tickets.find(q).sort('created_at', -1).to_list(100)

    async def ticket_get_user(self, uid):
        return await self.tickets.find({'user_id': uid}).sort('created_at', -1).to_list(20)

    async def ticket_reply(self, ticket_id, reply):
        await self.ticket_add_reply(ticket_id, reply)

    async def ticket_add_reply(self, ticket_id, reply_text):
        await self.tickets.update_one(
            {'ticket_id': ticket_id},
            {'$push': {'replies': {'text': reply_text, 'at': datetime.now().isoformat()}},
             '$set': {'last_reply_at': datetime.now().isoformat()}}
        )

    async def ticket_close(self, ticket_id):
        await self.tickets.update_one(
            {'ticket_id': ticket_id},
            {'$set': {'status': 'closed', 'closed_at': datetime.now().isoformat()}}
        )

    async def ticket_get(self, ticket_id):
        return await self.tickets.find_one({'ticket_id': ticket_id})

    async def add_qbank_file(self, lesson, topic, file_id, description, file_type='document'):
        r = await self.qbank_files.insert_one({'lesson': lesson, 'topic': topic, 'file_id': file_id, 'file_type': file_type, 'description': description, 'upload_date': datetime.now().isoformat(), 'downloads': 0})
        return r.inserted_id

    async def get_qbank_files(self, lesson=None, topic=None):
        q = {}
        if lesson: q['lesson'] = lesson
        if topic: q['topic'] = topic
        return await self.qbank_files.find(q).sort('upload_date', -1).to_list(100)

    async def get_qbank_file(self, fid):
        try: return await self.qbank_files.find_one({'_id': ObjectId(fid)})
        except: return None

    async def inc_qbank_download(self, fid, uid):
        try: await self.qbank_files.update_one({'_id': ObjectId(fid)}, {'$inc': {'downloads': 1}})
        except: pass
        await self.log(uid, 'qbank_download', {'file_id': fid})

    async def delete_qbank_file(self, fid):
        try: await self.qbank_files.delete_one({'_id': ObjectId(fid)})
        except: pass

    async def add_question(self, lesson, topic, difficulty, question, options, correct, explanation, creator, auto_approve=False):
        r = await self.questions.insert_one({'lesson': lesson, 'topic': topic, 'difficulty': difficulty, 'question': question, 'options': options, 'correct_answer': correct, 'explanation': explanation, 'creator_id': creator, 'approved': auto_approve, 'created_at': datetime.now().isoformat(), 'attempt_count': 0, 'correct_count': 0})
        return r.inserted_id

    async def get_questions(self, lesson=None, topic=None, difficulty=None, limit=1, exclude=None):
        q = {'approved': True}
        if lesson: q['lesson'] = lesson
        if topic and topic != 'همه': q['topic'] = topic
        if difficulty: q['difficulty'] = difficulty
        if exclude:
            try: q['_id'] = {'$nin': [ObjectId(i) for i in exclude]}
            except: pass
        return await self.questions.find(q).limit(limit).to_list(limit)

    async def get_weak_questions(self, uid, limit=1):
        user = await self.get_user(uid)
        weak = user.get('weak_topics', []) if user else []
        if not weak: return await self.get_questions(limit=limit)
        return await self.questions.find({'approved': True, 'topic': {'$in': weak}}).limit(limit).to_list(limit)

    async def pending_questions(self):
        return await self.questions.find({'approved': False}).to_list(50)

    async def approve_question(self, qid):
        try: await self.questions.update_one({'_id': ObjectId(qid)}, {'$set': {'approved': True}})
        except: pass

    async def delete_question(self, qid):
        try: await self.questions.delete_one({'_id': ObjectId(qid)})
        except: pass

    async def save_answer(self, uid, qid, selected, is_correct):
        await self.answers.insert_one({'user_id': uid, 'question_id': qid, 'selected': selected, 'is_correct': is_correct, 'answered_at': datetime.now().isoformat()})
        await self.users.update_one({'user_id': uid}, {'$inc': {'total_answers': 1, 'correct_answers': 1 if is_correct else 0}})
        try: await self.questions.update_one({'_id': ObjectId(qid)}, {'$inc': {'attempt_count': 1, 'correct_count': 1 if is_correct else 0}})
        except: pass
        if not is_correct:
            try:
                q = await self.questions.find_one({'_id': ObjectId(qid)})
                if q: await self.users.update_one({'user_id': uid}, {'$addToSet': {'weak_topics': q['topic']}})
            except: pass
        await self.log(uid, 'answer', {'qid': qid, 'correct': is_correct})

    async def get_lessons(self):
        return await self.questions.distinct('lesson', {'approved': True})

    async def get_topics(self, lesson=None):
        q = {'approved': True}
        if lesson: q['lesson'] = lesson
        return await self.questions.distinct('topic', q)

    async def add_schedule(self, stype, lesson, teacher, date, time, location, notes='', group='هر دو', is_weekly=False):
        r = await self.schedules.insert_one({
            'type': stype, 'lesson': lesson, 'teacher': teacher,
            'date': date, 'time': time, 'location': location, 'notes': notes,
            'group': group, 'is_weekly': is_weekly,
            'created_at': datetime.now().isoformat(), 'notified_days': []
        })
        return r.inserted_id

    async def get_schedules(self, stype=None, upcoming=True, group=None):
        q = {}
        if stype: q['type'] = stype
        if upcoming: q['date'] = {'$gte': datetime.now().strftime('%Y-%m-%d')}
        if group:
            q['$or'] = [{'group': group}, {'group': 'هر دو'}, {'group': {'$exists': False}}]
        return await self.schedules.find(q).sort('date', 1).to_list(200)

    async def delete_schedule(self, sid):
        try: await self.schedules.delete_one({'_id': ObjectId(sid)})
        except: pass

    async def upcoming_exams(self, days=7):
        today = datetime.now().strftime('%Y-%m-%d')
        future = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
        return await self.schedules.find({'type': 'exam', 'date': {'$gte': today, '$lte': future}}).sort('date', 1).to_list(20)

    async def get_exams_for_reminder(self, remind_days):
        target = (datetime.now() + timedelta(days=remind_days)).strftime('%Y-%m-%d')
        key = f'd{remind_days}'
        return await self.schedules.find({'type': 'exam', 'date': target, 'notified_days': {'$ne': key}}).to_list(50)

    async def mark_exam_notified(self, sid, remind_days):
        key = f'd{remind_days}'
        try: await self.schedules.update_one({'_id': ObjectId(sid)}, {'$addToSet': {'notified_days': key}})
        except: pass

    async def log(self, uid, action, data=None):
        await self.stats_col.insert_one({'user_id': uid, 'action': action, 'data': data or {}, 'timestamp': datetime.now().isoformat()})

    async def user_stats(self, uid):
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        week_act = await self.stats_col.count_documents({'user_id': uid, 'timestamp': {'$gt': week_ago}})
        downloads = await self.stats_col.count_documents({'user_id': uid, 'action': {'$in': ['bs_download', 'ref_download', 'qbank_download']}})
        user = await self.get_user(uid)
        total = user.get('total_answers', 0) if user else 0
        correct = user.get('correct_answers', 0) if user else 0
        pct = round(correct / total * 100, 1) if total > 0 else 0
        return {'downloads': downloads, 'total_answers': total, 'correct_answers': correct, 'percentage': pct, 'week_activity': week_act, 'weak_topics': user.get('weak_topics', []) if user else []}

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

    async def new_resources_count(self, days=7):
        since = (datetime.now() - timedelta(days=days)).isoformat()
        bs = await self.bs_content.count_documents({'uploaded_at': {'$gt': since}})
        refs = await self.ref_files.count_documents({'uploaded_at': {'$gt': since}})
        return bs + refs

    async def content_admin_stats(self):
        """آمار جامع برای پنل ادمین محتوا"""
        bs_lessons  = await self.bs_lessons.count_documents({})
        bs_sessions = await self.bs_sessions.count_documents({})
        bs_total    = await self.bs_content.count_documents({})
        bs_video    = await self.bs_content.count_documents({'type': 'video'})
        bs_pdf      = await self.bs_content.count_documents({'type': 'pdf'})
        bs_ppt      = await self.bs_content.count_documents({'type': 'ppt'})
        bs_voice    = await self.bs_content.count_documents({'type': 'voice'})
        bs_note     = await self.bs_content.count_documents({'type': 'note'})
        bs_test     = await self.bs_content.count_documents({'type': 'test'})
        ref_subjects = await self.ref_subjects.count_documents({})
        ref_books    = await self.ref_books.count_documents({})
        ref_files    = await self.ref_files.count_documents({})
        ref_fa       = await self.ref_files.count_documents({'lang': 'fa'})
        ref_en       = await self.ref_files.count_documents({'lang': 'en'})
        q_total    = await self.questions.count_documents({'approved': True})
        q_pending  = await self.questions.count_documents({'approved': False})
        q_by_bot   = await self.questions.count_documents({'approved': True, 'by_bot': True})
        q_by_users = await self.questions.count_documents({'approved': True, 'by_bot': {'$ne': True}})
        # آمار دانلود کل
        pipeline_dl = [{'$group': {'_id': None, 'total': {'$sum': '$downloads'}}}]
        r_bs  = await self.bs_content.aggregate(pipeline_dl).to_list(1)
        r_ref = await self.ref_files.aggregate(pipeline_dl).to_list(1)
        total_dl = (r_bs[0]['total'] if r_bs else 0) + (r_ref[0]['total'] if r_ref else 0)
        # کاربران تأیید شده
        users_count = await self.users.count_documents({'approved': True})
        return {
            'bs_lessons': bs_lessons, 'bs_sessions': bs_sessions,
            'bs_total': bs_total, 'bs_video': bs_video, 'bs_pdf': bs_pdf,
            'bs_ppt': bs_ppt, 'bs_voice': bs_voice, 'bs_note': bs_note, 'bs_test': bs_test,
            'ref_subjects': ref_subjects, 'ref_books': ref_books, 'ref_files': ref_files,
            'ref_fa': ref_fa, 'ref_en': ref_en,
            'q_total': q_total, 'q_pending': q_pending,
            'q_by_bot': q_by_bot, 'q_by_users': q_by_users,
            'total_downloads': total_dl, 'users_count': users_count,
        }

    async def get_question_by_id(self, qid):
        try:
            return await self.questions.find_one({'_id': ObjectId(qid)})
        except: return None

    async def get_questions_for_pdf(self, lesson=None, topic=None, count=20):
        q = {'approved': True}
        if lesson: q['lesson'] = lesson
        if topic and topic != 'همه': q['topic'] = topic
        return await self.questions.find(q).to_list(count)



db = DB()

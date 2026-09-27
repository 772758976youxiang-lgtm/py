import asyncio
import json
import os
import secrets
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import ai
from .runner import Runner
from .store import Store, now


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class NoteCreate(Model):
    title: str = Field('新脚本', min_length=1, max_length=120)
    content: str = Field('', max_length=200_000)


class NoteUpdate(NoteCreate):
    revision: int = Field(ge=1)


class Settings(Model):
    fontSize: float = Field(13.5, ge=11, le=22)
    theme: Literal['light', 'dark', 'system'] = 'system'
    tabSize: Literal[2, 4, 8] = 4
    language: Literal['zh', 'en'] = 'zh'
    providerId: str = Field('deepseek', max_length=64)
    model: str = Field('deepseek-chat', max_length=200)
    timeout: int = Field(30, ge=2, le=60)


class Provider(Model):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    name: str = Field(min_length=1, max_length=80)
    url: str = Field(max_length=2000)
    protocol: Literal['openai-chat', 'openai-responses', 'anthropic-messages']
    key: Optional[str] = Field(None, max_length=4000)
    clear_key: bool = False
    models: list[str] = Field(default_factory=list, max_length=500)

    @field_validator('url')
    @classmethod
    def valid_url(cls, value):
        value = value.strip().rstrip('/')
        try:
            u = urlsplit(value)
            port = u.port
        except ValueError:
            raise ValueError('API 地址格式错误')
        if (u.scheme not in ('https', 'http') or not u.hostname or u.username or u.password
                or u.query or u.fragment):
            raise ValueError('请填写不含凭据和参数的 HTTP(S) API 根地址')
        if u.scheme == 'http' and u.hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('远程模型服务请使用 HTTPS')
        return value

    @field_validator('models')
    @classmethod
    def valid_models(cls, values):
        values = list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if any(len(v) > 200 for v in values):
            raise ValueError('模型 ID 过长')
        return values


class Run(Model):
    note_id: Optional[str] = None
    code: str = Field(min_length=1, max_length=200_000)
    timeout: int = Field(30, ge=2, le=60)


class Input(Model):
    text: str = Field('', max_length=10_000)
    eof: bool = False


class Chat(Model):
    message: str = Field(min_length=1, max_length=20_000)
    code: str = Field('', max_length=100_000)
    provider_id: str = Field(max_length=64)
    model: str = Field(min_length=1, max_length=200)


class ImportNote(NoteCreate):
    pass


class ImportData(Model):
    notes: list[ImportNote] = Field(max_length=1000)


def create_app(data_dir=None):
    directory = data_dir or os.environ.get('LAB_DATA_DIR') or Path(__file__).parent / 'data'
    store = Store(directory)
    runner = Runner()
    token = secrets.token_urlsafe(32)
    chat_busy = set()
    origins = [f'http://{host}:{port}' for host in ('localhost', '127.0.0.1') for port in (5173, 4173, 8000)]

    @asynccontextmanager
    async def lifespan(app):
        yield
        await runner.close()

    app = FastAPI(title='Python 学习工具 API', version='1.0.0', lifespan=lifespan)
    app.state.store = store
    app.state.runner = runner
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET', 'POST', 'PUT', 'DELETE'],
                       allow_headers=['Content-Type', 'X-Lab-Token'])

    @app.middleware('http')
    async def local_guard(request: Request, call_next):
        if request.url.path.startswith('/api/'):
            origin = request.headers.get('origin')
            if origin and origin not in origins:
                return JSONResponse({'detail': '不允许的请求来源。'}, status_code=403)
            # Protect even read APIs; the public session endpoint is origin-checked above.
            if request.method != 'OPTIONS' and request.url.path not in ('/api/session', '/api/health'):
                if not secrets.compare_digest(request.headers.get('x-lab-token', ''), token):
                    return JSONResponse({'detail': '连接已失效，请刷新页面。'}, status_code=401)
            if int(request.headers.get('content-length', '0') or '0') > 8 * 1024 * 1024:
                return JSONResponse({'detail': '请求文件过大（上限 8 MB）。'}, status_code=413)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'testserver'])

    @app.get('/api/health')
    def health():
        import platform
        return dict(status='ok', python=platform.python_version())

    @app.get('/api/session')
    def session():
        return dict(token=token)

    def get_note(db, note_id):
        row = db.execute('SELECT * FROM notes WHERE id=?', (note_id,)).fetchone()
        if row is None:
            raise HTTPException(404, '脚本不存在。')
        return dict(row)

    @app.get('/api/notes')
    def notes():
        with store.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM notes ORDER BY updated_at DESC, id')]

    @app.post('/api/notes', status_code=201)
    def create_note(data: NoteCreate):
        note_id, stamp = uuid.uuid4().hex, now()
        with store.connect() as db:
            db.execute('INSERT INTO notes VALUES (?,?,?,?,?,1)', (note_id, data.title, data.content, stamp, stamp))
            return get_note(db, note_id)

    @app.put('/api/notes/{note_id}')
    def update_note(note_id: str, data: NoteUpdate):
        with store.connect() as db:
            get_note(db, note_id)
            result = db.execute('UPDATE notes SET title=?,content=?,updated_at=?,revision=revision+1 WHERE id=? AND revision=?',
                                (data.title, data.content, now(), note_id, data.revision))
            if result.rowcount == 0:
                raise HTTPException(409, '脚本已在其他窗口更新。请导出当前内容后刷新，避免覆盖。')
            return get_note(db, note_id)

    @app.delete('/api/notes/{note_id}')
    async def delete_note(note_id: str):
        if note_id in chat_busy:
            raise HTTPException(409, 'AI 正在回复此脚本，请稍后删除。')
        with store.connect() as db:
            get_note(db, note_id)
            db.execute('DELETE FROM notes WHERE id=?', (note_id,))
        return dict(ok=True)

    @app.post('/api/import')
    def import_notes(data: ImportData):
        ids = []
        with store.connect() as db:
            for note in data.notes:
                nid, stamp = uuid.uuid4().hex, now()
                db.execute('INSERT INTO notes VALUES (?,?,?,?,?,1)', (nid, note.title, note.content, stamp, stamp))
                ids.append(nid)
        return dict(ids=ids)

    @app.get('/api/export')
    def export_notes():
        return dict(version=1, exported_at=now(), notes=notes())

    @app.get('/api/settings')
    def settings():
        return store.settings()

    @app.put('/api/settings')
    def save_settings(data: Settings):
        with store.connect() as db:
            db.execute('UPDATE settings SET value=? WHERE id=1', (data.model_dump_json(),))
        return data

    @app.get('/api/providers')
    def providers():
        with store.connect() as db:
            return [store.public_provider(r) for r in db.execute('SELECT * FROM providers ORDER BY name')]

    def get_provider(provider_id):
        with store.connect() as db:
            row = db.execute('SELECT * FROM providers WHERE id=?', (provider_id,)).fetchone()
        if row is None:
            raise HTTPException(404, '请先添加模型提供商。')
        return dict(row)

    @app.post('/api/providers', status_code=201)
    def create_provider(data: Provider):
        try:
            with store.connect() as db:
                db.execute('INSERT INTO providers VALUES (?,?,?,?,?,?)',
                           (data.id, data.name, data.url, data.protocol, store.encrypt(data.key or ''), json.dumps(data.models)))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Provider ID 已存在。')
        return store.public_provider(get_provider(data.id))

    @app.put('/api/providers/{provider_id}')
    def save_provider(provider_id: str, data: Provider):
        if data.id != provider_id:
            raise HTTPException(422, '不能修改 Provider ID。')
        old = get_provider(provider_id)
        secret = '' if data.clear_key else (store.encrypt(data.key) if data.key else old['secret'])
        with store.connect() as db:
            db.execute('UPDATE providers SET name=?,url=?,protocol=?,secret=?,models=? WHERE id=?',
                       (data.name, data.url, data.protocol, secret, json.dumps(data.models), provider_id))
        return store.public_provider(get_provider(provider_id))

    @app.delete('/api/providers/{provider_id}')
    def delete_provider(provider_id: str):
        get_provider(provider_id)
        with store.connect() as db:
            db.execute('DELETE FROM providers WHERE id=?', (provider_id,))
        return dict(ok=True)

    @app.post('/api/providers/{provider_id}/models')
    async def fetch_models(provider_id: str):
        provider = get_provider(provider_id)
        model_ids = await ai.models(provider, store.decrypt(provider['secret']))
        with store.connect() as db:
            db.execute('UPDATE providers SET models=? WHERE id=?', (json.dumps(model_ids), provider_id))
        return dict(models=model_ids)

    @app.post('/api/runs', status_code=201)
    async def start_run(data: Run):
        if data.note_id:
            with store.connect() as db:
                get_note(db, data.note_id)
        return await runner.start(data.code, data.timeout, data.note_id)

    @app.get('/api/runs/active')
    async def active_run():
        for job in runner.jobs.values():
            if not job['task'].done():
                return dict(run=runner.public(job), code=job['code'], note_id=job['note_id'])
        return dict(run=None)

    @app.get('/api/runs/{run_id}')
    async def get_run(run_id: str):
        return runner.public(runner.get(run_id))

    @app.post('/api/runs/{run_id}/stop')
    async def stop_run(run_id: str):
        return await runner.stop(run_id)

    @app.post('/api/runs/{run_id}/input')
    async def input_run(run_id: str, data: Input):
        return await runner.write(run_id, data.text, data.eof)

    @app.get('/api/notes/{note_id}/messages')
    def messages(note_id: str):
        with store.connect() as db:
            get_note(db, note_id)
            return [dict(r) for r in db.execute('SELECT id,role,content,created_at,model FROM messages WHERE note_id=? ORDER BY id', (note_id,))]

    @app.delete('/api/notes/{note_id}/messages')
    async def clear_messages(note_id: str):
        if note_id in chat_busy:
            raise HTTPException(409, '请等待当前 AI 回复完成。')
        with store.connect() as db:
            get_note(db, note_id)
            db.execute('DELETE FROM messages WHERE note_id=?', (note_id,))
        return dict(ok=True)

    @app.post('/api/notes/{note_id}/chat')
    async def send_chat(note_id: str, data: Chat):
        if not data.message.strip() or not data.model.strip():
            raise HTTPException(422, '消息和模型 ID 不能为空。')
        if note_id in chat_busy:
            raise HTTPException(409, '此脚本已有 AI 请求正在处理。')
        if len(chat_busy) >= 3:
            raise HTTPException(429, '同时进行的 AI 请求过多。')
        chat_busy.add(note_id)
        try:
            provider = get_provider(data.provider_id)
            with store.connect() as db:
                get_note(db, note_id)
                history = list(db.execute('SELECT role,content,context FROM messages WHERE note_id=? ORDER BY id DESC LIMIT 20', (note_id,)))
            turns = []
            # Preserve only complete recent turns inside a bounded context budget.
            size = 0
            for row in history:
                content = row['content'] + row['context']
                size += len(content)
                if size > 100_000:
                    break
                turns.insert(0, dict(role=row['role'], content=content))
            while turns and turns[0]['role'] != 'user':
                turns.pop(0)
            context = '\n\nCurrent Python code:\n```python\n' + data.code + '\n```' if data.code else ''
            turns.append(dict(role='user', content=data.message + context))
            reply = await ai.chat(provider, store.decrypt(provider['secret']), data.model, turns, store.settings()['language'])
            with store.connect() as db:
                stamp = now()
                db.executemany('INSERT INTO messages(note_id,role,content,context,created_at,model) VALUES (?,?,?,?,?,?)',
                               [(note_id, 'user', data.message, context, stamp, data.model),
                                (note_id, 'assistant', reply, '', stamp, data.model)])
            return dict(reply=reply, messages=messages(note_id))
        finally:
            chat_busy.discard(note_id)

    return app


app = create_app()

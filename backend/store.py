"""SQLite persistence. API keys never leave the server in plaintext."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from cryptography.fernet import Fernet


def now():
    return datetime.now(timezone.utc).isoformat()


DEFAULT_SETTINGS = dict(fontSize=13.5, theme='system', tabSize=4, language='zh',
                        providerId='deepseek', model='deepseek-chat', timeout=30)


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'lab.sqlite3'
        key_path = self.directory / '.key'
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'wb') as f:
                f.write(Fernet.generate_key())
        self.cipher = Fernet(key_path.read_bytes())
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS providers (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
                    protocol TEXT NOT NULL, secret TEXT NOT NULL DEFAULT '', models TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                    role TEXT NOT NULL, content TEXT NOT NULL, context TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, model TEXT NOT NULL
                );
            ''')
            db.execute('INSERT OR IGNORE INTO settings VALUES (1, ?)', (json.dumps(DEFAULT_SETTINGS),))
            # Defaults are inserted once, so deleting a provider survives a restart.
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='initialized'").fetchone():
                db.execute('CREATE TABLE initialized (version INTEGER)')
                db.execute('INSERT INTO initialized VALUES (1)')
                db.execute('INSERT INTO providers VALUES (?,?,?,?,?,?)', (
                    'deepseek', 'DeepSeek', 'https://api.deepseek.com/v1', 'openai-chat', '',
                    json.dumps(['deepseek-chat', 'deepseek-reasoner'])))
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def encrypt(self, value):
        return self.cipher.encrypt(value.encode()).decode() if value else ''

    def decrypt(self, value):
        return self.cipher.decrypt(value.encode()).decode() if value else ''

    def settings(self):
        with self.connect() as db:
            return {**DEFAULT_SETTINGS, **json.loads(db.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])}

    @staticmethod
    def public_provider(row):
        return dict(id=row['id'], name=row['name'], url=row['url'], protocol=row['protocol'],
                    has_key=bool(row['secret']), models=json.loads(row['models']))

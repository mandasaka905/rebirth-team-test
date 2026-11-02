"""Persistent account/session store for the separately enabled hosted entry point."""
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Accounts:
    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / 'accounts.sqlite3'
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, password TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS attempts(bucket TEXT NOT NULL, at INTEGER NOT NULL);
              CREATE INDEX IF NOT EXISTS attempt_bucket ON attempts(bucket,at);
            ''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path, timeout=20)
        try:
            db.row_factory = sqlite3.Row
            with db:yield db
        finally:db.close()

    @staticmethod
    def normalize(name):
        if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{3,40}', name):
            raise ValueError('账号请用3至40位英文字母、数字、下划线或短横线')
        return name.lower()

    @staticmethod
    def password_hash(password, salt):
        return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()

    @staticmethod
    def validate_password(password):
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            raise ValueError('密码请用12至256个字符，可包含空格或中文')

    def create(self, name, password, *, limit=None):
        name = self.normalize(name)
        self.validate_password(password)
        uid, salt = secrets.token_hex(16), secrets.token_hex(16)
        hashed = self.password_hash(password, salt)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if limit is not None and db.execute('SELECT count(*) FROM users').fetchone()[0]>=limit:
                raise ValueError('本轮测试名额已满，请联系项目负责人')
            try:
                db.execute('INSERT INTO users VALUES(?,?,?,?)', (uid, name, salt, hashed))
            except sqlite3.IntegrityError:
                raise ValueError('这个账号已经存在') from None
        return uid

    def register(self,name,password,peer,*,limit=30):
        name=self.normalize(name);self.validate_password(password)
        now=int(time.time());bucket='register:'+hashlib.sha256(peer.encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM attempts WHERE at<?',(now-900,))
            if db.execute('SELECT count(*) FROM attempts WHERE bucket=?',(bucket,)).fetchone()[0]>=10:
                raise ValueError('注册尝试较多，请15分钟后再试')
            db.execute('INSERT INTO attempts VALUES(?,?)',(bucket,now))
        return self.create(name,password,limit=limit)

    def login(self, name, password, peer):
        now = int(time.time())
        # Persistent attempt limits also cover nonexistent names; no account enumeration.
        name = name.lower() if isinstance(name, str) else ''
        key = hashlib.sha256(name.encode()).hexdigest()
        peer_key = 'peer:' + hashlib.sha256(peer.encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM attempts WHERE at < ?', (now - 900,))
            for bucket, maximum in ((key, 10), (peer_key, 100)):
                if db.execute('SELECT count(*) FROM attempts WHERE bucket=?', (bucket,)).fetchone()[0] >= maximum:
                    return None, '尝试次数较多，请15分钟后再试'
            db.executemany('INSERT INTO attempts VALUES(?,?)', [(key, now), (peer_key, now)])
        with self.connect() as db:
            user = db.execute('SELECT * FROM users WHERE name=?', (name,)).fetchone()
        salt = user['salt'] if user else '0' * 32
        hashed = self.password_hash(password if isinstance(password, str) else '', salt)
        if not user or not hmac.compare_digest(hashed, user['password']):
            return None, '账号或密码不正确'
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires<=?', (now,))
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (self.digest(token), user['id'], now + 43200))
            db.execute('DELETE FROM attempts WHERE bucket=?', (key,))
        return token, None

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def user(self, token):
        if not token or len(token) > 128:
            return None
        with self.connect() as db:
            row = db.execute('SELECT u.id,u.name FROM sessions s JOIN users u ON s.user_id=u.id WHERE s.token=? AND s.expires>?', (self.digest(token), int(time.time()))).fetchone()
        return dict(row) if row else None

    def logout(self, token):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (self.digest(token),))

    def reset_password(self, name, password):
        name = self.normalize(name)
        self.validate_password(password)
        salt = secrets.token_hex(16)
        hashed = self.password_hash(password, salt)
        with self.connect() as db:
            row = db.execute('SELECT id FROM users WHERE name=?', (name,)).fetchone()
            if not row:
                raise ValueError('账号不存在')
            db.execute('UPDATE users SET salt=?,password=? WHERE id=?', (salt, hashed, row['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))

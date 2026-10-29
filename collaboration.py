"""Single-server collaboration, authentication and SQLite transaction safeguards."""
import argparse
import contextvars
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('FINANCE_DATA_DIR', ROOT / 'data')).resolve()
STATE = Path(os.environ.get('FINANCE_STATE_DIR', ROOT / 'private')).resolve()
LOCK = threading.RLock()
RUN = contextvars.ContextVar('finance_run', default=None)


def security_db():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    c = sqlite3.connect(STATE / 'accounts.db', timeout=30)
    c.execute('PRAGMA foreign_keys=ON')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, display_name TEXT NOT NULL,
      password TEXT NOT NULL, admin INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, username TEXT NOT NULL,
      expires REAL NOT NULL, FOREIGN KEY(username) REFERENCES users(username));
    CREATE TABLE IF NOT EXISTS attempts(username TEXT PRIMARY KEY, failures INTEGER, blocked_until REAL);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at TEXT DEFAULT CURRENT_TIMESTAMP,
      actor TEXT, action TEXT, detail TEXT);
    ''')
    c.commit()
    return c


def password_hash(password):
    if len(password) < 12:
        raise ValueError('비밀번호는 12자 이상 입력하세요.')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000)
    return salt + ':' + digest.hex()


def password_ok(password, stored):
    salt, expected = stored.split(':')
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000)
    return hmac.compare_digest(digest.hex(), expected)


def event(c, actor, action, detail=''):
    c.execute('INSERT INTO events(actor,action,detail) VALUES (?,?,?)', (actor, action, detail))


def validate_session(token):
    if not token:
        return None
    with security_db() as c:
        row = c.execute('''SELECT u.username,u.display_name,u.admin FROM users u JOIN sessions s
          ON u.username=s.username WHERE s.token=? AND s.expires>? AND u.active=1''',
          (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    return dict(zip(('username', 'display_name', 'admin'), row)) if row else None


def require_admin(token):
    user = validate_session(token)
    if not user or not user['admin']:
        raise PermissionError('관리자만 실행할 수 있습니다.')
    return user


def create_user(actor_token, username, display_name, password, admin=False, bootstrap=False):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}', username):
        raise ValueError('아이디는 영문·숫자·밑줄·점·하이픈 3~40자로 입력하세요.')
    if not display_name.strip():
        raise ValueError('사용자 이름을 입력하세요.')
    hashed = password_hash(password)
    with LOCK, security_db() as c:
        c.execute('BEGIN IMMEDIATE')
        count = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if bootstrap:
            if count:
                raise PermissionError('최초 관리자 생성은 계정이 없을 때만 가능합니다.')
            actor = 'server-setup'
            admin = True
        else:
            actor = require_admin(actor_token)['username']
        if c.execute('SELECT COUNT(*) FROM users WHERE active=1').fetchone()[0] >= 10:
            raise ValueError('활성 계정은 관리자 포함 최대 10명입니다.')
        if c.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
            raise ValueError('이미 등록된 아이디입니다.')
        c.execute('INSERT INTO users VALUES (?,?,?,?,1)', (username, display_name.strip(), hashed, int(admin)))
        event(c, actor, '계정 생성', username)


def login(username, password):
    username = username.strip()
    with LOCK, security_db() as c:
        c.execute('BEGIN IMMEDIATE')
        now = time.time()
        attempt = c.execute('SELECT failures,blocked_until FROM attempts WHERE username=?', (username,)).fetchone()
        if attempt and attempt[1] > now:
            return None
        row = c.execute('SELECT password,active FROM users WHERE username=?', (username,)).fetchone()
        # Match work for unknown names to reduce account enumeration via response time.
        dummy = '00' * 16 + ':' + '00' * 32
        valid = password_ok(password, row[0] if row else dummy)
        if not row or not row[1] or not valid:
            failures = (attempt[0] if attempt and attempt[1] == 0 else 0) + 1
            c.execute('INSERT OR REPLACE INTO attempts VALUES (?,?,?)',
                      (username, failures, now + 900 if failures >= 5 else 0))
            event(c, username, '로그인 실패')
            return None
        c.execute('DELETE FROM attempts WHERE username=?', (username,))
        c.execute('DELETE FROM sessions WHERE expires<=?', (now,))
        token = secrets.token_urlsafe(32)
        c.execute('INSERT INTO sessions VALUES (?,?,?)',
                  (hashlib.sha256(token.encode()).hexdigest(), username, now + 8 * 3600))
        event(c, username, '로그인')
        return token


def logout(token):
    if token:
        with security_db() as c:
            c.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),))


def change_password(token, old, new):
    user = validate_session(token)
    if not user:
        raise PermissionError('다시 로그인하세요.')
    hashed = password_hash(new)
    with LOCK, security_db() as c:
        row = c.execute('SELECT password FROM users WHERE username=?', (user['username'],)).fetchone()
        if not password_ok(old, row[0]):
            raise ValueError('현재 비밀번호가 일치하지 않습니다.')
        c.execute('UPDATE users SET password=? WHERE username=?', (hashed, user['username']))
        c.execute('DELETE FROM sessions WHERE username=?', (user['username'],))
        event(c, user['username'], '본인 비밀번호 변경')


def manage_user(token, username, active, admin, new_password=''):
    actor = require_admin(token)
    hashed = password_hash(new_password) if new_password else None
    with LOCK, security_db() as c:
        c.execute('BEGIN IMMEDIATE')
        old = c.execute('SELECT active,admin FROM users WHERE username=?', (username,)).fetchone()
        if not old:
            raise ValueError('등록되지 않은 계정입니다.')
        if username == actor['username'] and (not active or not admin):
            raise ValueError('본인 관리자 권한이나 활성 상태는 해제할 수 없습니다.')
        if active and not old[0] and c.execute('SELECT COUNT(*) FROM users WHERE active=1').fetchone()[0] >= 10:
            raise ValueError('활성 계정은 최대 10명입니다.')
        c.execute('UPDATE users SET active=?,admin=? WHERE username=?', (int(active), int(admin), username))
        if hashed:
            c.execute('UPDATE users SET password=? WHERE username=?', (hashed, username))
        c.execute('DELETE FROM sessions WHERE username=?', (username,))
        event(c, actor['username'], '계정 변경', json.dumps({'username': username, 'active': active, 'admin': admin, 'password_reset': bool(hashed)}))


class StaleData(BaseException):
    """Cannot be swallowed by legacy broad except Exception handlers."""


def revision(c):
    return c.execute('SELECT version FROM collaboration_revision WHERE id=1').fetchone()[0]


class SafeConnection(sqlite3.Connection):
    guarded = False

    def _before(self, sql):
        if not self.guarded or not re.match(r'\s*(INSERT|UPDATE|DELETE|REPLACE)\b', sql, re.I):
            return
        ctx = RUN.get()
        if not ctx or not validate_session(ctx['token']):
            raise PermissionError('로그인 세션이 만료되었습니다. 다시 로그인하세요.')
        if not self.in_transaction:
            super().execute('BEGIN IMMEDIATE')
            current = revision(self)
            if current != self.expected:
                super().rollback()
                raise StaleData('다른 사용자가 자료를 변경했습니다. 입력 내용을 따로 보관한 뒤 최신 자료를 다시 불러오세요.')
            backup_database(self.path, daily=True)

    def execute(self, sql, parameters=()):
        self._before(sql)
        return super().execute(sql, parameters)

    def executemany(self, sql, parameters):
        self._before(sql)
        return super().executemany(sql, parameters)

    def commit(self):
        super().commit()
        if self.guarded:
            self.expected = revision(self)

    def __exit__(self, *args):
        result = super().__exit__(*args)
        if self.guarded:
            self.expected = revision(self)
        return result


def connect(path):
    c = sqlite3.connect(path, timeout=30, factory=SafeConnection)
    c.path = Path(path)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA recursive_triggers=ON')
    ctx = RUN.get()
    if ctx:
        ctx['connections'].append(c)
    return c


def protect(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS collaboration_revision(id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL);
    INSERT OR IGNORE INTO collaboration_revision VALUES(1,0);
    CREATE TABLE IF NOT EXISTS change_history(id INTEGER PRIMARY KEY, at TEXT DEFAULT CURRENT_TIMESTAMP,
      actor TEXT NOT NULL, table_name TEXT NOT NULL, operation TEXT NOT NULL, before_json TEXT, after_json TEXT);
    ''')
    ctx = RUN.get()
    actor = ctx['user']['username'] if ctx else 'system'
    c.create_function('current_actor', 0, lambda: actor)
    tables = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    for (table,) in tables:
        if table in ('change_history', 'collaboration_revision') or table.startswith('_'):
            continue
        columns = [row[1] for row in c.execute(f'PRAGMA table_info("{table}")')]
        def json_row(prefix):
            return 'json_object(' + ','.join("'" + col + "'," + prefix + '."' + col + '"' for col in columns) + ')'
        for op in ('INSERT', 'UPDATE', 'DELETE'):
            before = 'NULL' if op == 'INSERT' else json_row('OLD')
            after = 'NULL' if op == 'DELETE' else json_row('NEW')
            c.execute(f'''CREATE TRIGGER IF NOT EXISTS "audit_{table}_{op}" AFTER {op} ON "{table}"
              BEGIN
                INSERT INTO change_history(actor,table_name,operation,before_json,after_json)
                VALUES(current_actor(),'{table}','{op}',{before},{after});
                UPDATE collaboration_revision SET version=version+1 WHERE id=1;
              END''')
    c.commit()
    key = str(c.path.resolve())
    c.expected = ctx['snapshots'].get(key, revision(c)) if ctx else revision(c)
    if ctx and c.expected != revision(c):
        raise StaleData('다른 사용자가 자료를 변경했습니다. 입력을 보관하고 최신 자료를 다시 불러오세요.')
    c.guarded = True
    return c


def backup_database(path, daily=False):
    """SQLite backup API includes committed WAL data; never copy a live DB file."""
    path = Path(path)
    folder = STATE / 'backups'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = time.strftime('%Y%m%d') if daily else time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3)
    target = folder / f'{path.stem}-{stamp}.sqlite'
    if daily and target.exists():
        return target
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=30) as source:
        with sqlite3.connect(target) as dest:
            source.backup(dest)
    return target


def restore_database(token, path, payload, expected):
    actor = require_admin(token)
    path = Path(path)
    temp = STATE / ('restore-' + secrets.token_hex(12) + '.sqlite')
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        temp.write_bytes(payload)
        with sqlite3.connect(f'file:{temp}?mode=ro', uri=True) as src:
            if src.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('백업 파일의 무결성 검사에 실패했습니다.')
            with LOCK, sqlite3.connect(path) as dest:
                if revision(dest) != expected:
                    raise ValueError('자료가 변경되었습니다. 최신 자료를 확인한 뒤 다시 시도하세요.')
                # Only known business tables/data are restored. Never import uploaded triggers/schema.
                tables = [r[0] for r in dest.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'") if r[0] not in ('change_history','collaboration_revision') and not r[0].startswith('_')]
                for table in tables:
                    cols = [r[1] for r in dest.execute(f'PRAGMA table_info("{table}")')]
                    other = [r[1] for r in src.execute(f'PRAGMA table_info("{table}")')]
                    if cols != other:
                        raise ValueError('현재 버전과 다른 백업입니다. 동일 버전의 연도별 백업을 사용하세요.')
                    if 'fiscal_year' in cols:
                        year = int(path.stem.split('_')[-1])
                        if src.execute(f'SELECT 1 FROM "{table}" WHERE fiscal_year IS NULL OR fiscal_year<>? LIMIT 1', (year,)).fetchone():
                            raise ValueError('선택한 회계연도와 백업 자료의 연도가 다릅니다.')
                saved = backup_database(path)
                dest.create_function('current_actor', 0, lambda: actor['username'])
                dest.execute('BEGIN IMMEDIATE')
                # Preserve audit triggers; temporarily open the year inside the restore transaction.
                if 'accounting_close' in tables:
                    dest.execute('UPDATE accounting_close SET closed=0')
                ordered=[t for t in tables if t!='accounting_close'] + (['accounting_close'] if 'accounting_close' in tables else [])
                for table in ordered:
                    cols = [r[1] for r in dest.execute(f'PRAGMA table_info("{table}")')]
                    dest.execute(f'DELETE FROM "{table}"')
                    marks = ','.join('?' for _ in cols)
                    dest.executemany(f'INSERT INTO "{table}" VALUES ({marks})', src.execute(f'SELECT * FROM "{table}"'))
                dest.execute('UPDATE collaboration_revision SET version=version+1 WHERE id=1')
            with security_db() as c:
                event(c, actor['username'], '백업 복원', path.name + '; 복원 전 백업: ' + saved.name)
            return saved
    finally:
        temp.unlink(missing_ok=True)


if __name__ == '__main__':
    from getpass import getpass
    parser = argparse.ArgumentParser(description='최초 관리자 생성 (서버에서 한 번 실행)')
    parser.add_argument('command', choices=['create-admin'])
    args = parser.parse_args()
    username = input('관리자 아이디: ').strip()
    name = input('사용자 이름: ').strip()
    password = getpass('비밀번호 (12자 이상): ')
    if password != getpass('비밀번호 확인: '):
        raise SystemExit('비밀번호가 일치하지 않습니다.')
    create_user(None, username, name, password, bootstrap=True)
    print('관리자 계정 생성 완료. streamlit run multiuser_app.py 로 실행하세요.')

#!/usr/bin/env python3
"""Optional opaque-envelope mailbox. No message/session/decryption keys live here.

The WSGI app is production-gateway agnostic. `serve` is a loopback-only development
runner; deploy the app behind a bounded production WSGI gateway and HTTPS proxy.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
from wsgiref.simple_server import WSGIRequestHandler, make_server

MAX_ENVELOPE = 134000
DEFAULT_TTL = 7 * 24 * 3600
MAX_WRITERS = 64
MAX_RECIPIENTS = 256
KEY = re.compile(r'[0-9a-f]{64}\Z')


def private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError('mailbox data directory must be private and owned by this user')
    return path


class Storage:
    def __init__(self, directory: Path, max_messages=1000, max_bytes=128 * 1024 * 1024,
                 total_bytes=512 * 1024 * 1024, ttl=DEFAULT_TTL):
        self.directory = private_directory(directory)
        self.path = directory / 'mailbox.sqlite3'
        if self.path.exists() or self.path.is_symlink():
            info = self.path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ValueError('unsafe mailbox database')
        self.max_messages, self.max_bytes, self.total_bytes, self.ttl = max_messages, max_bytes, total_bytes, ttl
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS recipients (id TEXT PRIMARY KEY, reader TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS writers (recipient TEXT, sender TEXT, credential TEXT NOT NULL,
                    PRIMARY KEY (recipient,sender));
                CREATE TABLE IF NOT EXISTS messages (recipient TEXT, id TEXT, sender TEXT NOT NULL,
                    body BLOB NOT NULL, created INTEGER NOT NULL, expires INTEGER NOT NULL,
                    PRIMARY KEY (recipient,id));
                CREATE INDEX IF NOT EXISTS expires_index ON messages(expires);
            ''')
        os.chmod(self.path, 0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA journal_mode=WAL')
        return db

    @staticmethod
    def credential(token: str) -> str:
        return hashlib.sha256(token.encode('ascii')).hexdigest()

    def authorized(self, db, token, recipient, sender=None):
        if not KEY.fullmatch(token):
            return False
        if sender is None:
            cursor = db.execute('SELECT reader FROM recipients WHERE id=?', (recipient,))
        else:
            cursor = db.execute('SELECT credential FROM writers WHERE recipient=? AND sender=?', (recipient, sender))
        try:row = cursor.fetchone()
        finally:cursor.close()
        return hmac.compare_digest(self.credential(token), row[0] if row else '0' * 64)


class Application:
    def __init__(self, storage: Storage):
        self.storage = storage

    def __call__(self, env, start_response):
        try:
            status, payload, media = self.handle(env)
        except (sqlite3.Error, OSError):
            status, payload, media = 503, b'{"error":"storage_unavailable"}', 'application/json'
        except (ValueError, UnicodeError, json.JSONDecodeError):
            status, payload, media = 400, b'{"error":"invalid_request"}', 'application/json'
        reasons = {200: 'OK', 201: 'Created', 204: 'No Content', 400: 'Bad Request',
                   403: 'Forbidden', 404: 'Not Found', 409: 'Conflict', 413: 'Content Too Large',
                   429: 'Too Many Requests', 503: 'Service Unavailable'}
        headers = [('Content-Type', media), ('Content-Length', str(len(payload))),
                   ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')]
        if status in (429, 503):
            headers.append(('Retry-After', '5'))
        start_response(f'{status} {reasons[status]}', headers)
        return [payload]

    @staticmethod
    def result(status, value=None):
        return status, json.dumps(value, separators=(',', ':')).encode() if value is not None else b'', 'application/json'

    def handle(self, env):
        method = env['REQUEST_METHOD']
        parts = env.get('PATH_INFO', '').split('/')
        if len(parts) < 4 or parts[:2] != ['', 'v1'] or not KEY.fullmatch(parts[2]) or env.get('QUERY_STRING'):
            return self.result(404)
        recipient = parts[2]
        auth = env.get('HTTP_AUTHORIZATION', '')
        token = auth[7:] if auth.startswith('Bearer ') else ''
        length = env.get('CONTENT_LENGTH') or '0'
        if not length.isascii() or not length.isdecimal() or len(length) > 10 or env.get('HTTP_TRANSFER_ENCODING'):
            return self.result(400)
        length = int(length)
        if length > MAX_ENVELOPE:
            return self.result(413)
        s = self.storage
        with s.connect() as db:
            if len(parts) == 5 and parts[3] == 'writers' and KEY.fullmatch(parts[4]) and method in ('PUT', 'DELETE'):
                if not s.authorized(db, token, recipient):
                    return self.result(403)
                if length:
                    return self.result(400)
                if method == 'DELETE':
                    db.execute('DELETE FROM writers WHERE recipient=? AND sender=?', (recipient, parts[4]))
                    return self.result(204)
                db.execute('BEGIN IMMEDIATE')
                if not s.authorized(db, token, recipient):
                    return self.result(403)
                existing = db.execute('SELECT 1 FROM writers WHERE recipient=? AND sender=?', (recipient, parts[4])).fetchone()
                count = db.execute('SELECT COUNT(*) FROM writers WHERE recipient=?', (recipient,)).fetchone()[0]
                if not existing and count >= MAX_WRITERS:
                    return self.result(429)
                writer = secrets.token_hex(32)
                db.execute('INSERT INTO writers VALUES (?,?,?) ON CONFLICT(recipient,sender) DO UPDATE SET credential=excluded.credential',
                           (recipient, parts[4], s.credential(writer)))
                return self.result(201, {'sender': parts[4], 'token': writer})
            if parts[3] != 'messages':
                return self.result(404)
            if len(parts) == 6 and method == 'PUT' and KEY.fullmatch(parts[4]) and KEY.fullmatch(parts[5]):
                sender, identifier = parts[4:6]
                if not s.authorized(db, token, recipient, sender):
                    return self.result(403)
                if not length:
                    return self.result(400)
                body = env['wsgi.input'].read(length)
                if len(body) != length or hashlib.sha256(body).hexdigest() != identifier:
                    return self.result(400)
                # Serialize quota check and insertion, including concurrent retries.
                db.execute('BEGIN IMMEDIATE')
                # A grant may have been revoked while the bounded body arrived.
                if not s.authorized(db, token, recipient, sender):
                    return self.result(403)
                db.execute('DELETE FROM messages WHERE expires<=?', (int(time.time()),))
                previous = db.execute('SELECT sender,body FROM messages WHERE recipient=? AND id=?', (recipient, identifier)).fetchone()
                if previous:
                    return self.result(200 if previous[0] == sender and previous[1] == body else 409)
                count, size = db.execute('SELECT COUNT(*),COALESCE(SUM(length(body)),0) FROM messages WHERE recipient=?', (recipient,)).fetchone()
                total = db.execute('SELECT COALESCE(SUM(length(body)),0) FROM messages').fetchone()[0]
                if count >= s.max_messages or size + length > s.max_bytes or total + length > s.total_bytes:
                    return self.result(429)
                created = int(time.time())
                db.execute('INSERT INTO messages VALUES (?,?,?,?,?,?)', (recipient, identifier, sender, body, created, created + s.ttl))
                return self.result(201)
            if not s.authorized(db, token, recipient):
                return self.result(403)
            if length:
                return self.result(400)
            db.execute('DELETE FROM messages WHERE expires<=?', (int(time.time()),))
            if len(parts) == 4 and method == 'GET':
                rows = db.execute('SELECT id,sender,length(body),created,expires FROM messages WHERE recipient=? ORDER BY created,id LIMIT 32', (recipient,)).fetchall()
                return self.result(200, {'items': [dict(zip(('id', 'sender', 'size', 'created', 'expires'), row)) for row in rows]})
            if len(parts) == 5 and KEY.fullmatch(parts[4]):
                if method == 'GET':
                    row = db.execute('SELECT body FROM messages WHERE recipient=? AND id=?', (recipient, parts[4])).fetchone()
                    return (200, row[0], 'application/octet-stream') if row else self.result(404)
                if method == 'DELETE':
                    db.execute('DELETE FROM messages WHERE recipient=? AND id=?', (recipient, parts[4]))
                    return self.result(204)
            return self.result(404)


def create_app():
    """WSGI gateway entry point; data path is configuration, never a token."""
    path = os.environ.get('HARBOR_MAILBOX_DATA')
    if not path:
        raise ValueError('set HARBOR_MAILBOX_DATA to a private directory')
    return Application(Storage(Path(path)))


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *_):
        pass

    def setup(self):
        self.request.settimeout(5)
        super().setup()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    initialize = actions.add_parser('init', help='create a recipient and private read credential file')
    initialize.add_argument('--data', type=Path, required=True)
    initialize.add_argument('--recipient', required=True)
    initialize.add_argument('--credentials', type=Path, required=True)
    serve = actions.add_parser('serve', help='loopback development runner; use a production WSGI gateway for deployment')
    serve.add_argument('--data', type=Path, required=True)
    serve.add_argument('--bind', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=3137)
    serve.add_argument('--max-messages', type=int, default=1000)
    args = parser.parse_args()
    if args.action == 'init':
        if not KEY.fullmatch(args.recipient):
            parser.error('recipient must be a canonical 32-byte public key')
        storage = Storage(args.data)
        try:
            fd = os.open(args.credentials, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            token = None
        else:
            with os.fdopen(fd, 'r') as saved:
                info = os.fstat(saved.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size > 512:
                    parser.error('existing credential file is unsafe; it was preserved')
                value = json.load(saved)
                if not isinstance(value, dict) or set(value) != {'recipient', 'token'} or value['recipient'] != args.recipient or not isinstance(value['token'], str) or not KEY.fullmatch(value['token']):
                    parser.error('credential file does not match this recipient; it was preserved')
                token = value['token']
                os.fsync(saved.fileno())
        with storage.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT reader FROM recipients WHERE id=?', (args.recipient,)).fetchone()
            if existing and (token is None or not hmac.compare_digest(existing[0], storage.credential(token))):
                parser.error('recipient already exists; existing credential was preserved')
            if not existing and db.execute('SELECT COUNT(*) FROM recipients').fetchone()[0] >= MAX_RECIPIENTS:
                parser.error('recipient limit reached')
            if token is None:
                token = secrets.token_hex(32)
                fd = os.open(args.credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                ready = False
                try:
                    with os.fdopen(fd, 'w') as output:
                        json.dump({'recipient': args.recipient, 'token': token}, output)
                        output.write('\n');output.flush();os.fsync(output.fileno())
                    ready = True
                finally:
                    if not ready:
                        args.credentials.unlink(missing_ok=True)
            parent = os.open(args.credentials.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:os.fsync(parent)
            finally:os.close(parent)
            if not existing:
                db.execute('INSERT INTO recipients VALUES (?,?)', (args.recipient, storage.credential(token)))
            # Keep the valid private file if COMMIT fails: this exact command can
            # resume the same credential instead of replacing an active secret.
            db.commit()
        print(json.dumps({'event': 'initialized', 'credentials': str(args.credentials)}))
        return
    if not ipaddress.ip_address(args.bind).is_loopback or not 0 <= args.port <= 65535 or not 1 <= args.max_messages <= 10000:
        parser.error('development server requires a loopback bind, valid port and bounded queue')
    app = Application(Storage(args.data, max_messages=args.max_messages))
    with make_server(args.bind, args.port, app, handler_class=QuietHandler) as server:
        print(json.dumps({'event': 'ready', 'port': server.server_port}), flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()

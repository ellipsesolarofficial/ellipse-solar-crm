#!/usr/bin/env python3
"""Local server for the open-source Ellipse Solar CRM."""

import json
import os
import secrets
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import store

HOST = '127.0.0.1'
PORT = 8787
ROOT = os.path.dirname(os.path.abspath(__file__))
SESSIONS = {}
FAILURES = {}
SESSION_SECONDS = 12 * 60 * 60

PAGES = {
    '/': 'leads.html',
    '/login': 'login.html',
    '/admin': 'admin.html',
}
FILES = {
    '/app.css': 'text/css; charset=utf-8',
    '/app.js': 'text/javascript; charset=utf-8',
}


def read_body(handler):
    length = int(handler.headers.get('Content-Length') or 0)
    if length > 100000:
        raise ValueError('Request is too large')
    raw = handler.rfile.read(length) if length else b''
    if not raw:
        return {}
    try:
        return json.loads(raw.decode('utf-8'))
    except json.JSONDecodeError:
        raise ValueError('Invalid JSON')


def current_user(handler):
    cookie = handler.headers.get('Cookie') or ''
    token = ''
    for part in cookie.split(';'):
        name, _, value = part.strip().partition('=')
        if name == 'session':
            token = value
    record = SESSIONS.get(token)
    if not record or record['expires'] < time.time():
        SESSIONS.pop(token, None)
        return None
    return record['user']


class App(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, status, body, content_type, extra_headers=None):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status, payload, extra_headers=None):
        self._send(status, json.dumps(payload), 'application/json; charset=utf-8', extra_headers)

    def _file(self, name, content_type):
        path = os.path.join(ROOT, 'static', name)
        with open(path, 'rb') as handle:
            self._send(200, handle.read(), content_type)

    def _error(self, status, message):
        self._json(status, {'error': message})

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == '/api/session':
                user = current_user(self)
                if not user:
                    self._error(401, 'Sign in required')
                    return
                self._json(200, {'user': user})
                return
            if path == '/api/leads':
                user = current_user(self)
                if not user:
                    self._error(401, 'Sign in required')
                    return
                self._json(200, store.dashboard(user))
                return
            if path == '/api/admin':
                user = current_user(self)
                if not user:
                    self._error(401, 'Sign in required')
                    return
                self._json(200, {'users': store.list_users(user), 'activity': store.activity_for(user)})
                return
            if path in PAGES:
                self._file(PAGES[path], 'text/html; charset=utf-8')
                return
            if path in FILES:
                self._file(path[1:], FILES[path])
                return
            self._error(404, 'Not found')
        except ValueError as error:
            self._error(403, str(error))
        except Exception:
            traceback.print_exc()
            self._error(500, 'Something went wrong')

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = read_body(self)
            if path == '/api/login':
                self._login(body)
                return
            if path == '/api/logout':
                self._logout()
                return
            user = current_user(self)
            if not user:
                self._error(401, 'Sign in required')
                return
            if path == '/api/leads':
                self._json(200, store.create_lead(user, body))
                return
            if path == '/api/users':
                created = store.create_user(user, body.get('name'), body.get('role'), body.get('pin'))
                self._json(200, {'user': created})
                return
            self._error(404, 'Not found')
        except ValueError as error:
            self._error(400, str(error))
        except Exception:
            traceback.print_exc()
            self._error(500, 'Something went wrong')

    def do_PATCH(self):
        path = urlparse(self.path).path
        try:
            user = current_user(self)
            if not user:
                self._error(401, 'Sign in required')
                return
            prefix = '/api/leads/'
            if not path.startswith(prefix):
                self._error(404, 'Not found')
                return
            lead = store.update_lead(user, path[len(prefix):], read_body(self))
            self._json(200, {'lead': lead})
        except ValueError as error:
            self._error(400, str(error))
        except Exception:
            traceback.print_exc()
            self._error(500, 'Something went wrong')

    def do_DELETE(self):
        path = urlparse(self.path).path
        try:
            user = current_user(self)
            if not user:
                self._error(401, 'Sign in required')
                return
            prefix = '/api/users/'
            if not path.startswith(prefix):
                self._error(404, 'Not found')
                return
            store.delete_user(user, path[len(prefix):])
            self._json(200, {'ok': True})
        except ValueError as error:
            self._error(400, str(error))
        except Exception:
            traceback.print_exc()
            self._error(500, 'Something went wrong')

    def _login(self, body):
        name = str(body.get('name') or '').strip()
        pin = str(body.get('pin') or '')
        key = store.norm(name)
        record = FAILURES.get(key) or {'count': 0, 'since': time.time()}
        if time.time() - record['since'] > 900:
            record = {'count': 0, 'since': time.time()}
        if record['count'] >= 8:
            self._error(429, 'Too many attempts. Try again in 15 minutes.')
            return
        try:
            user = store.authenticate(name, pin)
        except ValueError:
            record['count'] += 1
            FAILURES[key] = record
            self._error(401, 'Invalid name or PIN')
            return
        FAILURES.pop(key, None)
        token = secrets.token_urlsafe(32)
        SESSIONS[token] = {'user': user, 'expires': time.time() + SESSION_SECONDS}
        cookie = 'session=%s; HttpOnly; Path=/; SameSite=Lax; Max-Age=%d' % (token, SESSION_SECONDS)
        self._json(200, {'user': user}, {'Set-Cookie': cookie})

    def _logout(self):
        cookie = self.headers.get('Cookie') or ''
        for part in cookie.split(';'):
            name, _, value = part.strip().partition('=')
            if name == 'session':
                SESSIONS.pop(value, None)
        self._json(200, {'ok': True}, {'Set-Cookie': 'session=; HttpOnly; Path=/; Max-Age=0'})


def main():
    store.ensure_seed()
    server = ThreadingHTTPServer((HOST, PORT), App)
    print('Ellipse Solar CRM')
    print('http://%s:%d' % (HOST, PORT))
    print('Local admin PIN: %s' % store.PIN_PATH)
    server.serve_forever()


if __name__ == '__main__':
    main()

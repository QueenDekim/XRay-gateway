"""Authenticated same-origin management API. No external web dependencies."""
import collections
import hmac
import http.cookies
import http.server
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit
from controller import routeros
from accounts import Accounts
from version import build_info
from localization import translate_message


class Panel(http.server.BaseHTTPRequestHandler):
    controller = None
    snapshot = None
    sessions = {}
    failures = collections.defaultdict(list)
    assets = Path(__file__).parent / 'web'
    defaults = []

    def accounts(self):
        return Accounts(self.controller.directory / 'auth.json', self.controller.lock)

    def update_session_user(self, token, user):
        if token in self.sessions:
            self.sessions[token].update(user_id=user['id'], user_revision=user['revision'],
                                        username=user['username'], user=user)

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *args):
        pass

    def respond(self, status, data, cookie=None, content_type='application/json'):
        if isinstance(data,dict):
            language=self.headers.get('Accept-Language','ru')
            data=dict(data)
            for key in ('error','last_error','stats_error'):
                if key in data:
                    data[key]=translate_message(data[key],language)
            if 'warnings' in data:
                data['warnings']=[translate_message(value,language) for value in data['warnings']]
        raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        for key, value in {'Content-Type': content_type, 'Content-Length': str(len(raw)), 'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items():
            self.send_header(key, value)
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(raw)

    def session(self):
        try:
            cookie = http.cookies.SimpleCookie(self.headers.get('Cookie', ''))
            token = cookie['xray_session'].value
            with self.controller.lock:
                session = self.sessions.get(token)
                if session and session['expires'] > time.time():
                    user = self.accounts().session_user(session.get('user_id'), session.get('user_revision'))
                    if user:
                        self.update_session_user(token, user)
                        return token, session
                self.sessions.pop(token, None)
        except (KeyError, http.cookies.CookieError):
            pass
        return None, None

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/locales.js':
            self.respond(200, b'window.XrayMessages = ' + (self.assets / 'locales.json').read_bytes() + b';\n', content_type='text/javascript; charset=utf-8')
            return
        if path == '/api/version':
            self.respond(200, build_info())
            return
        if path in ('/', '/app.js', '/theme.js', '/i18n.js', '/locales.json', '/style.css', '/favicon.png'):
            filename = 'index.html' if path == '/' else path[1:]
            kind = {'html':'text/html; charset=utf-8', 'js':'text/javascript; charset=utf-8',
                    'css':'text/css; charset=utf-8', 'png':'image/png', 'json':'application/json; charset=utf-8'}[filename.rsplit('.', 1)[1]]
            self.respond(200, (self.assets / filename).read_bytes(), content_type=kind)
            return
        _, session = self.session()
        if not session:
            self.respond(401, {'error': 'Требуется вход.'})
        elif path == '/api/state':
            with self.controller.lock:
                self.respond(200, self.snapshot() | {'csrf': session['csrf'], 'username': session['username'],
                    'user':session['user'], 'settings':self.controller.settings(),
                    'users':self.accounts().users() if session['user']['role'] == 'admin' else [],
                    'ip_lists': self.controller.ip_lists(self.defaults)})
        else:
            self.respond(404, {'error': 'Не найдено.'})

    def do_POST(self):
        try:
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                self.respond(403, {'error': 'Недопустимый источник запроса.'})
                return
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 262144 or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('JSON required')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Object required')
            path = urlsplit(self.path).path
            if path == '/api/login':
                self.login(data)
                return
            token, session = self.session()
            if not session:
                self.respond(401, {'error': 'Требуется вход.'})
                return
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf']):
                self.respond(403, {'error': 'Недействительный CSRF-токен.'})
                return
            if path == '/api/logout':
                with self.controller.lock:
                    self.sessions.pop(token, None)
                self.respond(200, {'ok': True}, cookie='xray_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            elif path in ('/api/profiles/add', '/api/profiles/edit', '/api/profiles/delete'):
                self.controller.change(path.rsplit('/', 1)[1], data, str(data.get('id', '')))
                self.respond(200, {'ok': True})
            elif path == '/api/routeros':
                settings = self.controller.settings()
                data = {key:settings[key] for key in ('source', 'interface', 'local_networks')} | data
                # Infrastructure addresses come from saved administration settings.
                data.update(gateway=settings['gateway'], host=settings['host'])
                selected = data.get('list_id')
                values = self.defaults
                if selected:
                    item = next((item for item in self.controller.ip_lists(self.defaults) if item['id'] == selected), None)
                    if item is None:
                        self.respond(400, {'error': 'Выбранный IP-список не найден'})
                        return
                    # An explicitly selected list must not silently fall back to inventory.
                    if not item['addresses']:
                        self.respond(400, {'error': 'Выбранный IP-список пуст'})
                        return
                    data = dict(data, destinations='\n'.join(item['addresses']),
                                list_key=item['id'], list_name=item['name'])
                elif not str(data.get('destinations', '')).strip():
                    self.respond(400, {'error': 'Укажите адреса или выберите IP-список'})
                    return
                else:
                    data = dict(data, list_key='manual', list_name='manual')
                warnings = []
                script = routeros(data, values, warnings=warnings)
                self.respond(200, {'script': script, 'warnings': warnings})
            elif path in ('/api/ip-lists/add', '/api/ip-lists/edit', '/api/ip-lists/delete'):
                try:
                    item = self.controller.change_ip_list(path.rsplit('/', 1)[1], data, self.defaults)
                except ValueError as exc:
                    self.respond(400, {'error': str(exc)})
                    return
                self.respond(200, {'ok': True, 'list': item})
            elif path == '/api/password':
                try:
                    with self.controller.lock:
                        user = self.accounts().change_password(session['user'], data.get('current_password'), data.get('password'))
                        self.update_session_user(token, user)
                    self.respond(200, {'ok':True})
                except ValueError as exc:
                    self.respond(400, {'error':str(exc)})
            elif path == '/api/settings' or path in ('/api/users/add', '/api/users/edit', '/api/users/delete'):
                try:
                    with self.controller.lock:
                        _, current = self.session()
                        if not current or current['user']['role'] != 'admin':
                            self.respond(403, {'error':'Требуются права администратора.'})
                            return
                        if path == '/api/settings':
                            settings = self.controller.change_settings(data)
                            self.respond(200, {'ok':True, 'settings':settings})
                        else:
                            user = self.accounts().change(path.rsplit('/', 1)[1], data, current['user'])
                            if user and user['id'] == current['user']['id']:
                                self.update_session_user(token, user)
                            self.respond(200, {'ok':True, 'user':user})
                except PermissionError as exc:
                    self.respond(403, {'error':str(exc)})
                except ValueError as exc:
                    self.respond(400, {'error':str(exc)})
            else:
                self.respond(404, {'error': 'Не найдено.'})
        except (ValueError, KeyError, TypeError):
            self.respond(400, {'error': 'Некорректные данные. Проверьте поля, VLESS URI и актуальность страницы.'})
        except Exception:
            self.respond(503, {'error': 'Не удалось применить конфигурацию. Проверьте состояние шлюза.'})

    def login(self, data):
        now, ip = time.time(), self.client_address[0]
        with self.controller.lock:
            if len(self.failures) > 1024:
                self.failures.clear()
            self.failures[ip] = [t for t in self.failures[ip] if t > now - 60]
            if len(self.failures[ip]) >= 5:
                self.respond(429, {'error': 'Слишком много попыток. Повторите через минуту.'})
                return
            self.failures[ip].append(now)
        auth = self.accounts().authenticate(data.get('username', ''), data.get('password', ''))
        if auth is None:
            self.respond(401, {'error': 'Неверный логин или пароль.'})
            return
        token = secrets.token_urlsafe(32)
        with self.controller.lock:
            self.failures.pop(ip, None)
            for expired in list(self.sessions):
                if self.sessions[expired]['expires'] <= now:
                    self.sessions.pop(expired)
            if len(self.sessions) >= 128:
                self.sessions.pop(next(iter(self.sessions)))
            self.sessions[token] = {'expires': now + 43200, 'csrf': secrets.token_urlsafe(32)}
            self.update_session_user(token, auth)
        self.respond(200, {'ok': True}, cookie=f'xray_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200')

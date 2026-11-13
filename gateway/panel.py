"""Authenticated same-origin management API. No external web dependencies."""
import collections
import hmac
import http.cookies
import http.server
import json
import secrets
import time
import io
import re
from pathlib import Path
from urllib.parse import urlsplit
from controller import routeros, profile_sources
from accounts import Accounts
from version import build_info
from localization import translate_message


class Panel(http.server.BaseHTTPRequestHandler):
    controller = None
    snapshot = None
    sessions = {}
    failures = collections.defaultdict(list)
    pending_logins = {}
    security_attempts = {}
    assets = Path(__file__).parent / 'web'
    defaults = []

    def accounts(self):
        return Accounts(self.controller.directory / 'auth.json', self.controller.lock)

    def router(self):
        from router_service import RouterService
        with self.controller.lock:
            if not hasattr(self.controller,'router_service'):self.controller.router_service=RouterService(self.controller)
            return self.controller.router_service

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
            if 'logs' in data:data['logs']=[translate_message(value,language) for value in data['logs']]
        raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        for key, value in {'Content-Type': content_type, 'Content-Length': str(len(raw)), 'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items():
            self.send_header(key, value)
        if cookie:
            if self.headers.get('X-Forwarded-Proto','').split(',')[0].strip()=='https':cookie+='; Secure'
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
                if hasattr(self.controller,'router_service'):self.controller.router_service.logout(token)
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
        if path.startswith('/vendor/') and re.fullmatch(r'/vendor/[a-zA-Z0-9_.-]+',path):
            asset=self.assets/path[1:]
            if asset.is_file() and asset.suffix in ('.js','.css'):
                self.respond(200,asset.read_bytes(),content_type='text/javascript' if asset.suffix=='.js' else 'text/css')
                return
        if path in ('/', '/app.js', '/management.js', '/terminal-stream.js', '/theme.js', '/i18n.js', '/locales.json', '/style.css', '/favicon.png'):
            filename = 'index.html' if path == '/' else path[1:]
            kind = {'html':'text/html; charset=utf-8', 'js':'text/javascript; charset=utf-8',
                    'css':'text/css; charset=utf-8', 'png':'image/png', 'json':'application/json; charset=utf-8'}[filename.rsplit('.', 1)[1]]
            self.respond(200, (self.assets / filename).read_bytes(), content_type=kind)
            return
        token, session = self.session()
        if not session:
            self.respond(401, {'error': 'Требуется вход.'})
        elif path.startswith('/api/avatar/') and re.fullmatch(r'/api/avatar/[a-zA-Z0-9_-]{1,64}',path):
            avatar=self.controller.directory/'avatars'/(path.rsplit('/',1)[1]+'.png')
            self.respond(200,avatar.read_bytes(),content_type='image/png') if avatar.is_file() else self.respond(404,{'error':'Не найдено.'})
        elif path=='/api/account/2fa/qr':
            import qrcode
            try:
                uri=self.accounts().pending_factor(session['user'])
                output=io.BytesIO();qrcode.make(uri).save(output,format='PNG')
                self.respond(200,output.getvalue(),content_type='image/png')
            except ValueError as exc:self.respond(400,{'error':str(exc)})
        elif path.startswith('/api/routeros/'):
            try:
                router=self.router()
                if path=='/api/routeros/config':
                    if session['user']['role']!='admin':self.respond(403,{'error':'Требуются права администратора.'});return
                    self.respond(200,router.public_config())
                elif path=='/api/routeros/jobs':self.respond(200,{'jobs':router.recent(session['user'])})
                elif path.startswith('/api/routeros/jobs/'):
                    from urllib.parse import parse_qs
                    cursor=parse_qs(urlsplit(self.path).query).get('cursor',['0'])[0]
                    self.respond(200,router.job(path.rsplit('/',1)[1],session['user'],cursor))
                elif path.startswith('/api/routeros/terminal/'):
                    if session['user']['role']!='admin':self.respond(403,{'error':'Требуются права администратора.'});return
                    from urllib.parse import parse_qs
                    cursor=parse_qs(urlsplit(self.path).query).get('cursor',['0'])[0]
                    self.respond(200,router.read_terminal(path.rsplit('/',1)[1],session['user'],token,cursor))
                else:self.respond(404,{'error':'Не найдено.'})
            except ValueError as exc:self.respond(400,{'error':str(exc)})
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
            limit=2_800_000 if urlsplit(self.path).path=='/api/account/avatar' else 262144
            if not 0 < length <= limit or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('JSON required')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Object required')
            path = urlsplit(self.path).path
            if path == '/api/login':
                self.login(data)
                return
            if path=='/api/login/2fa':
                self.login_factor(data)
                return
            token, session = self.session()
            if not session:
                self.respond(401, {'error': 'Требуется вход.'})
                return
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf']):
                self.respond(403, {'error': 'Недействительный CSRF-токен.'})
                return
            shared_write=path=='/api/settings' or path.startswith(('/api/profiles/','/api/ip-lists/','/api/routeros/','/api/users/'))
            if shared_write and session['user']['role']!='admin':
                self.respond(403,{'error':'Требуются права администратора.'})
                return
            if path == '/api/logout':
                with self.controller.lock:
                    self.sessions.pop(token, None)
                if hasattr(self.controller,'router_service'):self.router().logout(token)
                self.respond(200, {'ok': True}, cookie='xray_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            elif path.startswith('/api/account/'):
                try:
                    accounts=self.accounts();actor=session['user'];codes=None
                    if path.startswith('/api/account/2fa/'):
                        with self.controller.lock:
                            now=time.time()
                            attempts=[stamp for stamp in self.security_attempts.get(actor['id'],[]) if stamp>now-60]
                            if len(attempts)>=5:
                                self.respond(429,{'error':'Слишком много попыток. Повторите через минуту.'});return
                            if len(self.security_attempts)>1024:self.security_attempts.clear()
                            self.security_attempts[actor['id']]=attempts+[now]
                    if path=='/api/account/profile':user=accounts.profile(actor,data)
                    elif path=='/api/account/avatar':user=accounts.avatar(actor,data.get('image',''))
                    elif path=='/api/account/2fa/setup':
                        self.respond(200,accounts.setup_factor(actor,data.get('password')));return
                    elif path=='/api/account/2fa/enable':user,codes=accounts.enable_factor(actor,data.get('code',''))
                    elif path in ('/api/account/2fa/disable','/api/account/2fa/recovery'):
                        user,codes=accounts.manage_factor(actor,data.get('password'),data.get('code',''),path.endswith('/disable'))
                    else:self.respond(404,{'error':'Не найдено.'});return
                    with self.controller.lock:self.update_session_user(token,user)
                    self.respond(200,{'ok':True,'user':user}|({'recovery_codes':codes} if codes is not None else {}))
                except ValueError as exc:self.respond(400,{'error':str(exc)})
            elif path == '/api/profiles/preview':
                try:
                    source=str(data.get('uri','')).strip()
                    entries,skipped=profile_sources(source)
                    with self.controller.lock:
                        _,live=self.session()
                        if live is not session or live['user']['role']!='admin':
                            self.respond(401,{'error':'Требуется вход.'});return
                        preview={'token':secrets.token_urlsafe(24),'source':source,'expires':time.time()+300,'profiles':entries}
                        session['subscription_preview']=preview
                    public=[]
                    for entry in entries:
                        node=entry['node'];endpoint=node['settings']['vnext'][0];stream=node['streamSettings']
                        public.append({key:entry[key] for key in ('id','name')}|{'address':endpoint['address'],
                            'port':endpoint['port'],'transport':stream['network'],'security':stream['security']})
                    self.respond(200,{'token':preview['token'],'profiles':public,'skipped':skipped})
                except ValueError as exc:self.respond(400,{'error':str(exc)})
            elif path in ('/api/profiles/add', '/api/profiles/edit', '/api/profiles/delete'):
                try:
                    prepared=None
                    if data.get('subscription_token'):
                        with self.controller.lock:
                            preview=session.get('subscription_preview',{})
                            if (preview.get('expires',0)<=time.time() or preview.get('token')!=data['subscription_token']
                                or preview.get('source')!=str(data.get('uri','')).strip()):
                                raise ValueError('Выбор подписки устарел. Загрузите подписку повторно.')
                            selected=data.get('subscription_profiles')
                            if (not isinstance(selected,list) or not selected or any(not isinstance(v,str) for v in selected)
                                or len(set(selected))!=len(selected)):
                                raise ValueError('Выберите хотя бы один профиль подписки.')
                            entries={entry['id']:entry for entry in preview['profiles']}
                            if any(value not in entries for value in selected):
                                raise ValueError('Выбор подписки устарел. Загрузите подписку повторно.')
                            prepared=[entries[value] for value in selected]
                    self.controller.change(path.rsplit('/', 1)[1], data, str(data.get('id', '')),source_profiles=prepared)
                    if prepared is not None and session.get('subscription_preview',{}).get('token')==data.get('subscription_token'):
                        session.pop('subscription_preview',None)
                except ValueError as exc:
                    self.respond(400, {'error': str(exc)})
                    return
                self.respond(200, {'ok': True})
            elif path == '/api/profiles/reset-checks':
                self.controller.reset_profile_checks()
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
            elif path.startswith('/api/routeros/'):
                try:
                    router=self.router();actor=session['user']
                    if path=='/api/routeros/apply':
                        self.respond(202,router.start('apply',str(data.get('id','')),data.get('version',-1),actor,self.defaults))
                    elif actor['role']!='admin':self.respond(403,{'error':'Требуются права администратора.'})
                    elif path=='/api/routeros/config':self.respond(200,router.save(data))
                    elif path=='/api/routeros/host-key':self.respond(200,router.scan(data))
                    elif path=='/api/routeros/terminal/open':
                        opened=router.open_terminal(actor,token,data.get('cols',100),data.get('rows',30))
                        _,active=self.session()
                        if not active:
                            router.close_terminal(opened['id']);self.respond(401,{'error':'Требуется вход.'});return
                        self.respond(200,opened)
                    elif path=='/api/routeros/terminal/input':
                        router.write_terminal(str(data.get('id','')),actor,token,data.get('data',''));self.respond(200,{'ok':True})
                    elif path=='/api/routeros/terminal/resize':
                        router.resize_terminal(str(data.get('id','')),actor,token,data.get('cols',100),data.get('rows',30));self.respond(200,{'ok':True})
                    elif path=='/api/routeros/terminal/close':
                        identifier=str(data.get('id',''));router.terminal(identifier,actor,token);router.close_terminal(identifier);self.respond(200,{'ok':True})
                    else:self.respond(404,{'error':'Не найдено.'})
                except ValueError as exc:self.respond(400,{'error':str(exc)})
            elif path in ('/api/ip-lists/add', '/api/ip-lists/edit', '/api/ip-lists/delete'):
                try:
                    if path.endswith('/delete'):
                        self.respond(202,self.router().start('delete',str(data.get('id','')),data.get('version',-1),session['user'],self.defaults));return
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
        if auth.get('two_factor_enabled'):
            challenge=secrets.token_urlsafe(32)
            with self.controller.lock:
                for key in list(self.pending_logins):
                    if self.pending_logins[key]['expires']<now:self.pending_logins.pop(key,None)
                if len(self.pending_logins)>=128:self.pending_logins.pop(next(iter(self.pending_logins)))
                self.pending_logins[challenge]={'user_id':auth['id'],'revision':auth['revision'],'expires':now+180,'attempts':0,'ip':ip}
            self.respond(200,{'requires_2fa':True,'challenge':challenge})
            return
        self.issue_session(auth)

    def login_factor(self,data):
        now,ip=time.time(),self.client_address[0]
        with self.controller.lock:
            challenge=str(data.get('challenge',''));pending=self.pending_logins.get(challenge)
            if not pending or pending['expires']<=now or pending['attempts']>=5 or pending['ip']!=ip:
                self.pending_logins.pop(challenge,None)
                self.respond(401,{'error':'Вход истёк. Введите логин и пароль заново.'});return
            pending['attempts']+=1
            accounts=self.accounts()
            if not accounts.verify_factor(pending['user_id'],pending['revision'],data.get('code','')):
                self.respond(401,{'error':'Неверный или использованный код 2FA.'});return
            auth=accounts.session_user(pending['user_id'],pending['revision'])
            self.pending_logins.pop(challenge,None)
            if not auth:self.respond(401,{'error':'Требуется повторный вход.'});return
        self.issue_session(auth)

    def issue_session(self,auth):
        now,ip=time.time(),self.client_address[0]
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

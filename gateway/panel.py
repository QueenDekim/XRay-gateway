"""Session and Bearer authentication for the management API and web panel."""
import hmac
import http.cookies
import http.server
import json
import secrets
import time
import io
import re
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, quote
from controller import routeros, profile_sources, subscription_group, profile_node_id
from accounts import Accounts
from auth_rate import AuthRate, AuthRateLimit
from version import build_info
from localization import translate_message
import web_pages
import session_store


class Panel(http.server.BaseHTTPRequestHandler):
    controller = None
    snapshot = None
    sessions = {}
    token_sessions = {}
    pending_logins = {}
    assets = Path(__file__).parent / 'web'
    defaults = []

    def accounts(self):
        return Accounts(self.controller.directory / 'auth.json', self.controller.lock)

    def rate(self):
        with self.controller.lock:
            if not hasattr(self.controller, 'auth_rate'):self.controller.auth_rate = AuthRate(self.controller.directory, self.controller.lock)
            return self.controller.auth_rate

    def peer(self):
        return self.rate().peer(self.client_address[0], self.headers.get('X-Forwarded-For', ''))

    def rate_response(self, error):
        self.respond(429, {'error': 'Слишком много попыток авторизации. Повторите позже.', 'retry_after': error.seconds}, retry_after=error.seconds)

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

    def respond(self, status, data, cookie=None, content_type='application/json', retry_after=None):
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
        if status == 401 and urlsplit(self.path).path.startswith('/api/'):
            self.send_header('WWW-Authenticate', 'Bearer realm="Xray Gateway"')
        if retry_after is not None:self.send_header('Retry-After', str(retry_after))
        if cookie:
            if self.headers.get('X-Forwarded-Proto','').split(',')[0].strip()=='https':cookie+='; Secure'
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(raw)

    def session(self):
        authorization = self.headers.get('Authorization')
        if authorization is not None and urlsplit(self.path).path.startswith('/api/'):
            from api_tokens import ApiTokens
            peer = self.peer()
            self.rate().before('bearer', peer, count=not getattr(self, '_bearer_counted', False))
            self._bearer_counted = True
            match = re.fullmatch(r'(?i:Bearer) (\S{1,128})', authorization)
            with self.controller.lock:
                authenticated = ApiTokens(self.accounts()).authenticate(match[1]) if match else None
                if not authenticated:
                    self.rate().failed('bearer', peer)
                    return None, None
                key = 'api:' + authenticated['id']
                if key not in self.token_sessions:
                    if len(self.token_sessions) >= 256:
                        self.token_sessions.pop(next(iter(self.token_sessions)))
                    self.token_sessions[key] = {'csrf': '', 'auth_method': 'token'}
                session = self.token_sessions[key]
                user = authenticated['user']
                session.update(expires=authenticated['expires'], user_id=user['id'], user_revision=user['revision'],
                               username=user['username'], user=user)
                return key, session
        return self.browser_session()

    def browser_session(self):
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
                if self.sessions.pop(token, None) is not None:session_store.save(self.controller,self.sessions)
                if hasattr(self.controller,'router_service'):self.controller.router_service.logout(token)
        except (KeyError, http.cookies.CookieError):
            pass
        return None, None

    def redirect(self, target):
        self.send_response(303);self.send_header('Location',target)
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length','0');self.end_headers()

    def updates(self):
        from updates import Updates
        with self.controller.lock:
            if not hasattr(self.controller,'updates'):self.controller.updates=Updates(self.controller)
            return self.controller.updates

    def page_state(self, session):
        with self.controller.lock:
            return self.snapshot() | {'csrf':session['csrf'],'username':session['username'],'user':session['user'],
                'settings':self.controller.settings(),'users':self.accounts().users() if session['user']['role']=='admin' else [],
                'ip_lists':self.controller.ip_lists(self.defaults),'updates':self.updates().snapshot(session['user']['role']=='admin')}

    def do_GET(self):
        self._bearer_counted = False
        try:self.handle_get()
        except AuthRateLimit as error:self.rate_response(error)

    def handle_get(self):
        path = urlsplit(self.path).path
        if path in ('/api/login', '/api/login/2fa', '/api/logout'):
            self.respond(404, {'error': 'Не найдено.'});return
        page,topic=web_pages.route(path)
        if path in ('/','/login') or page:
            _,session=self.browser_session()
            if path=='/':self.redirect('/overview' if session else '/login');return
            if path=='/login':
                if session:self.redirect(web_pages.safe_next(parse_qs(urlsplit(self.path).query).get('next',['/overview'])[0]))
                else:self.respond(200,web_pages.render(self.assets,'login',None),content_type='text/html; charset=utf-8')
                return
            if not session:self.redirect('/login?next='+quote(path,safe=''));return
            if page in ('routeros','settings') and session['user']['role']!='admin':
                self.redirect('/account' if page=='settings' else '/overview');return
            self.respond(200,web_pages.render(self.assets,page,self.page_state(session),topic),content_type='text/html; charset=utf-8');return
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
        if path in ('/tokens.js', '/login.js', '/updates.js', '/app.js', '/management.js', '/terminal-stream.js', '/theme.js', '/i18n.js', '/locales.json', '/style.css', '/favicon.png'):
            filename = 'index.html' if path == '/' else path[1:]
            kind = {'html':'text/html; charset=utf-8', 'js':'text/javascript; charset=utf-8',
                    'css':'text/css; charset=utf-8', 'png':'image/png', 'json':'application/json; charset=utf-8'}[filename.rsplit('.', 1)[1]]
            self.respond(200, (self.assets / filename).read_bytes(), content_type=kind)
            return
        token, session = self.session()
        if not session:
            self.respond(401, {'error': 'Требуется вход.'})
        elif path == '/api/account/tokens':
            if session.get('auth_method') == 'token':
                self.respond(403, {'error': 'Управление API-токенами доступно после входа в панель.'});return
            from api_tokens import ApiTokens
            try:self.respond(200, {'tokens': ApiTokens(self.accounts()).list(session['user'])})
            except ValueError:self.respond(401, {'error': 'Требуется вход.'})
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
        elif path=='/api/updates':self.respond(200,self.updates().snapshot(session['user']['role']=='admin'))
        elif path.startswith('/api/routeros/'):
            try:
                router=self.router()
                if path=='/api/routeros/config':
                    if session['user']['role']!='admin':self.respond(403,{'error':'Требуются права администратора.'});return
                    self.respond(200,router.public_config())
                elif path=='/api/routeros/jobs':self.respond(200,{'jobs':router.recent(session['user'])})
                elif path.startswith('/api/routeros/jobs/'):
                    cursor=parse_qs(urlsplit(self.path).query).get('cursor',['0'])[0]
                    self.respond(200,router.job(path.rsplit('/',1)[1],session['user'],cursor))
                elif path.startswith('/api/routeros/terminal/'):
                    if session['user']['role']!='admin':self.respond(403,{'error':'Требуются права администратора.'});return
                    cursor=parse_qs(urlsplit(self.path).query).get('cursor',['0'])[0]
                    self.respond(200,router.read_terminal(path.rsplit('/',1)[1],session['user'],token,cursor))
                else:self.respond(404,{'error':'Не найдено.'})
            except ValueError as exc:self.respond(400,{'error':str(exc)})
        elif path == '/api/state':
            with self.controller.lock:
                self.respond(200,self.page_state(session))
        else:
            self.respond(404, {'error': 'Не найдено.'})

    def do_POST(self):
        self._bearer_counted = False
        updater=self.updates()
        if not updater.enter_write():
            self.respond(503,{'error':'Устанавливается обновление. Повторите запрос после перезапуска.'});return
        try:self.handle_post()
        finally:updater.leave_write()

    def handle_post(self):
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
            if self.updates().maintenance():
                self.respond(503,{'error':'Устанавливается обновление. Повторите запрос после перезапуска.'});return
            if path in ('/api/login', '/api/login/2fa', '/api/logout'):
                self.respond(404, {'error': 'Не найдено.'});return
            if path == '/auth/login':
                self.login(data)
                return
            if path=='/auth/login/2fa':
                self.login_factor(data)
                return
            token, session = self.session()
            if not session:
                self.respond(401, {'error': 'Требуется вход.'})
                return
            bearer = session.get('auth_method') == 'token'
            if bearer and (path.startswith('/api/account/tokens') or path == '/auth/logout'):
                self.respond(403, {'error': 'Управление API-токенами доступно после входа в панель.'});return
            if not bearer and not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf']):
                self.respond(403, {'error': 'Недействительный CSRF-токен.'})
                return
            shared_write=path=='/api/settings' or path.startswith(('/api/profiles/','/api/ip-lists/','/api/routeros/','/api/users/','/api/updates/'))
            if shared_write and session['user']['role']!='admin':
                self.respond(403,{'error':'Требуются права администратора.'})
                return
            if path == '/auth/logout':
                with self.controller.lock:
                    self.sessions.pop(token, None)
                    session_store.save(self.controller,self.sessions)
                if hasattr(self.controller,'router_service'):self.router().logout(token)
                self.respond(200, {'ok': True}, cookie='xray_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            elif path.startswith('/api/account/'):
                try:
                    accounts=self.accounts();actor=session['user'];codes=None
                    protected = path.startswith('/api/account/2fa/') or path in ('/api/account/tokens/create', '/api/account/tokens/reissue', '/api/account/tokens/revoke')
                    if protected:self.rate().before('security', actor['id'])
                    if path in ('/api/account/tokens/create', '/api/account/tokens/reissue', '/api/account/tokens/revoke'):
                        from api_tokens import ApiTokens
                        service = ApiTokens(accounts)
                        identifier = str(data.get('id', ''))
                        if path.endswith('/create'):result = service.create(actor, data)
                        elif path.endswith('/reissue'):result = service.reissue(actor, identifier, data.get('code', ''))
                        else:result = service.revoke(actor, identifier, data.get('code', ''))
                        if not path.endswith('/create'):
                            identity = 'api:' + identifier
                            with self.controller.lock:self.token_sessions.pop(identity, None)
                            if hasattr(self.controller, 'router_service'):self.router().logout(identity)
                        with self.controller.lock:self.update_session_user(token, result['user'])
                        self.respond(200 if path.endswith('/revoke') else 201, result);return
                    elif path=='/api/account/profile':user=accounts.profile(actor,data)
                    elif path=='/api/account/avatar':user=accounts.avatar(actor,data.get('image',''))
                    elif path=='/api/account/2fa/setup':
                        self.respond(200,accounts.setup_factor(actor,data.get('password')));return
                    elif path=='/api/account/2fa/enable':user,codes=accounts.enable_factor(actor,data.get('code',''))
                    elif path in ('/api/account/2fa/disable','/api/account/2fa/recovery'):
                        user,codes=accounts.manage_factor(actor,data.get('password'),data.get('code',''),path.endswith('/disable'))
                    else:self.respond(404,{'error':'Не найдено.'});return
                    with self.controller.lock:
                        self.update_session_user(token,user)
                        session_store.save(self.controller,self.sessions)
                    self.respond(200,{'ok':True,'user':user}|({'recovery_codes':codes} if codes is not None else {}))
                except ValueError as exc:
                    if protected:self.rate().failed('security', actor['id'])
                    self.respond(400,{'error':str(exc)})
            elif path.startswith('/api/updates/'):
                try:
                    updater=self.updates()
                    if path=='/api/updates/check':self.respond(202,updater.start_check())
                    elif path=='/api/updates/settings':self.respond(200,updater.save_settings(data))
                    elif path=='/api/updates/install':self.respond(202,updater.install(str(data.get('tag',''))))
                    else:self.respond(404,{'error':'Не найдено.'})
                except ValueError as exc:self.respond(400,{'error':str(exc)})
            elif path == '/api/profiles/preview':
                try:
                    source=str(data.get('uri','')).strip()
                    entries,skipped=profile_sources(source)
                    with self.controller.lock:
                        _,live=self.session()
                        if live is not session or live['user']['role']!='admin':
                            self.respond(401,{'error':'Требуется вход.'});return
                        group=subscription_group(source)
                        saved_profiles=self.controller.list_profiles()
                        existing={p.get('subscription',{}).get('node_id'):p for p in saved_profiles
                            if group and p.get('subscription',{}).get('id')==group['id']}
                        if existing:group['name']=next(iter(existing.values()))['subscription']['name']
                        if group:
                            for entry in entries:
                                legacy=[p for p in saved_profiles if not p.get('subscription') and profile_node_id(p['node'])==entry['id']]
                                if entry['id'] not in existing and len(legacy)==1:existing[entry['id']]=legacy[0]

                        preview={'token':secrets.token_urlsafe(24),'source':source,'expires':time.time()+300,'profiles':entries,'group':group}
                        session['subscription_preview']=preview
                    public=[]
                    for entry in entries:
                        node=entry['node'];endpoint=node['settings']['vnext'][0];stream=node['streamSettings']
                        saved=existing.get(entry['id'])
                        public.append({key:entry[key] for key in ('id','name')}|({'name':saved['name'],'priority':saved['priority']} if saved else {})|{'address':endpoint['address'],
                            'port':endpoint['port'],'transport':stream['network'],'security':stream['security']})
                    self.respond(200,{'token':preview['token'],'profiles':public,'skipped':skipped,'group':group})
                except ValueError as exc:self.respond(400,{'error':str(exc)})
            elif path in ('/api/profiles/add', '/api/profiles/edit', '/api/profiles/delete'):
                try:
                    prepared=None;group=None
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
                            options=data.get('subscription_options',{})
                            if not isinstance(options,dict) or any(key not in selected for key in options):
                                raise ValueError('Некорректные параметры профилей подписки.')
                            prepared=[]
                            for value in selected:
                                entry=entries[value].copy()
                                if value in options:
                                    option=options[value]
                                    if not isinstance(option,dict) or not isinstance(option.get('name'),str) or not 1<=len(option['name'].strip())<=80:
                                        raise ValueError('Название должно содержать от 1 до 80 символов.')
                                    priority=option.get('priority')
                                    if isinstance(priority,bool) or not isinstance(priority,int) or not 1<=priority<=1000:
                                        raise ValueError('Некорректные приоритет или состояние профиля.')
                                    entry.update(name=option['name'].strip(),priority=priority,customized=True)
                                prepared.append(entry)
                            if preview['group']:
                                group=preview['group'].copy()
                                label=data.get('subscription_name',group['name'])
                                if not isinstance(label,str) or not 1<=len(label.strip())<=80:
                                    raise ValueError('Название должно содержать от 1 до 80 символов.')
                                group['name']=label.strip()
                    self.controller.change(path.rsplit('/', 1)[1], data, str(data.get('id', '')),source_profiles=prepared,source_group=group)
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
                        try:_,active=self.session()
                        except AuthRateLimit:
                            router.close_terminal(opened['id']);raise
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
                    self.rate().before('security', session['user']['id'])
                    with self.controller.lock:
                        user = self.accounts().change_password(session['user'], data.get('current_password'), data.get('password'))
                        self.update_session_user(token, user)
                        session_store.save(self.controller,self.sessions)
                    self.respond(200, {'ok':True})
                except ValueError as exc:
                    self.rate().failed('security', session['user']['id'])
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
                                session_store.save(self.controller,self.sessions)
                            self.respond(200, {'ok':True, 'user':user})
                except PermissionError as exc:
                    self.respond(403, {'error':str(exc)})
                except ValueError as exc:
                    self.respond(400, {'error':str(exc)})
            else:
                self.respond(404, {'error': 'Не найдено.'})
        except AuthRateLimit as error:self.rate_response(error)
        except (ValueError, KeyError, TypeError):
            self.respond(400, {'error': 'Некорректные данные. Проверьте поля, VLESS URI и актуальность страницы.'})
        except Exception:
            self.respond(503, {'error': 'Не удалось применить конфигурацию. Проверьте состояние шлюза.'})

    def login(self, data):
        now, ip = time.time(), self.peer()
        username = str(data.get('username', ''))
        self.rate().before('login', ip, username)
        # Serialize the password check with quota updates so concurrent failures cannot bypass the threshold.
        with self.controller.lock:
            self.rate().before('login', ip, username, count=False)
            auth = self.accounts().authenticate(username, data.get('password', ''))
            if auth is None:
                self.rate().failed('login', ip, username)
                self.respond(401, {'error': 'Неверный логин или пароль.'});return
            if auth.get('two_factor_enabled'):
                challenge = secrets.token_urlsafe(32)
                for key in list(self.pending_logins):
                    if self.pending_logins[key]['expires'] < now:self.pending_logins.pop(key, None)
                if len(self.pending_logins) >= 128:self.pending_logins.pop(next(iter(self.pending_logins)))
                self.pending_logins[challenge] = {'user_id': auth['id'], 'revision': auth['revision'],
                    'username': auth['username'], 'expires': now + 180, 'attempts': 0, 'ip': ip}
                self.respond(200, {'requires_2fa': True, 'challenge': challenge});return
        self.issue_session(auth)

    def login_factor(self,data):
        now,ip=time.time(),self.peer()
        with self.controller.lock:
            challenge=str(data.get('challenge',''));pending=self.pending_logins.get(challenge)
            username = pending.get('username') if pending and pending['ip'] == ip else None
            self.rate().before('login', ip, username)
            if not pending or pending['expires']<=now or pending['attempts']>=5 or pending['ip']!=ip:
                self.pending_logins.pop(challenge,None)
                self.rate().failed('login', ip)
                self.respond(401,{'error':'Вход истёк. Введите логин и пароль заново.'});return
            pending['attempts']+=1
            accounts=self.accounts()
            if not accounts.verify_factor(pending['user_id'],pending['revision'],data.get('code','')):
                self.rate().failed('login', ip, username)
                self.respond(401,{'error':'Неверный или использованный код 2FA.'});return
            auth=accounts.session_user(pending['user_id'],pending['revision'])
            self.pending_logins.pop(challenge,None)
            if not auth:self.respond(401,{'error':'Требуется повторный вход.'});return
        self.issue_session(auth)

    def issue_session(self,auth):
        now,ip=time.time(),self.client_address[0]
        token = secrets.token_urlsafe(32)
        with self.controller.lock:
            self.rate().succeeded(auth['username'])
            for expired in list(self.sessions):
                if self.sessions[expired]['expires'] <= now:
                    self.sessions.pop(expired)
            if len(self.sessions) >= 128:
                self.sessions.pop(next(iter(self.sessions)))
            self.sessions[token] = {'expires': now + 43200, 'csrf': secrets.token_urlsafe(32)}
            self.update_session_user(token, auth)
            session_store.save(self.controller,self.sessions)
        self.respond(200, {'ok': True}, cookie=f'xray_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200')

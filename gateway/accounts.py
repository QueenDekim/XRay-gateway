"""Persistent panel accounts, legacy migration and session-version revocation."""
import hashlib
import hmac
import json
import secrets
import time
import uuid
import base64
import io
from pathlib import Path
from controller import atomic_json
from secure_store import SecretStore
from two_factor import new_secret,match_step,recovery_codes,recovery_hash,provisioning_uri

ITERATIONS = 600000


def password_hash(password):
    if not isinstance(password, str) or not 8 <= len(password) <= 1024:
        raise ValueError('Пароль должен содержать от 8 до 1024 символов.')
    salt = secrets.token_hex(24)
    return {'salt':salt, 'iterations':ITERATIONS,
            'hash':hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()}


def password_matches(user, password):
    if not isinstance(password, str) or len(password) > 1024:
        return False
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(user['salt']), user['iterations']).hex()
    return hmac.compare_digest(actual, user['hash'])


def public_user(user):
    return {key:user[key] for key in ('id', 'username', 'role', 'revision')} | {
        'display_name':user.get('display_name') or user['username'],
        'avatar':('/api/avatar/'+user['id']+'?v='+user['avatar_hash']) if user.get('avatar_hash') else '',
        'preferences':user.get('preferences',{}), 'two_factor_enabled':bool(user.get('totp_secret')),
        'recovery_remaining':len(user.get('recovery_hashes',[]))}


class Accounts:
    def __init__(self, path, lock):
        self.path, self.lock = Path(path), lock
        self.secrets=SecretStore(self.path.parent)

    def own(self,stored,actor):
        user=next((u for u in stored['users'] if u['id']==actor['id']),None)
        if not user or user['revision']!=actor['revision']:raise ValueError('Требуется повторный вход.')
        return user

    def factor(self,user,code):
        if not user.get('totp_secret'):return False
        secret=self.secrets.open(user['totp_secret'],user['id']+':totp')
        step=match_step(secret,code,user.get('totp_last_step',-1))
        if step is not None:
            user['totp_last_step']=step
            return True
        value=recovery_hash(user['id'],code)
        for saved in user.get('recovery_hashes',[]):
            if hmac.compare_digest(saved,value):
                user['recovery_hashes'].remove(saved)
                return True
        return False

    def verify_factor(self,identifier,revision,code):
        with self.lock:
            stored=self.load()
            user=next((u for u in stored['users'] if u['id']==identifier and u['revision']==revision),None)
            if not user or not self.factor(user,code):return False
            atomic_json(self.path,stored)
            return True

    def setup_factor(self,actor,password):
        with self.lock:
            stored=self.load();user=self.own(stored,actor)
            if not password_matches(user,password):raise ValueError('Текущий пароль неверен.')
            if user.get('totp_secret'):raise ValueError('Двухфакторная защита уже включена.')
            secret=new_secret()
            user['totp_pending']={'secret':self.secrets.seal(secret,user['id']+':totp'),'expires':time.time()+600}
            atomic_json(self.path,stored)
            return {'secret':secret,'uri':provisioning_uri(secret,user['username'])}

    def pending_factor(self,actor):
        with self.lock:
            user=self.own(self.load(),actor);pending=user.get('totp_pending',{})
            if pending.get('expires',0)<time.time():raise ValueError('Настройка 2FA истекла. Начните заново.')
            secret=self.secrets.open(pending['secret'],user['id']+':totp')
            return provisioning_uri(secret,user['username'])

    def enable_factor(self,actor,code):
        with self.lock:
            stored=self.load();user=self.own(stored,actor);pending=user.get('totp_pending',{})
            if user.get('totp_secret') or pending.get('expires',0)<time.time():raise ValueError('Настройка 2FA истекла. Начните заново.')
            step=match_step(self.secrets.open(pending['secret'],user['id']+':totp'),code)
            if step is None:raise ValueError('Неверный или использованный код 2FA.')
            user.update(totp_secret=pending['secret'],totp_last_step=step,revision=user['revision']+1)
            user.pop('totp_pending',None)
            codes,user['recovery_hashes']=recovery_codes(user['id'])
            atomic_json(self.path,stored)
            return public_user(user),codes

    def manage_factor(self,actor,password,code,disable=False):
        with self.lock:
            stored=self.load();user=self.own(stored,actor)
            if not password_matches(user,password):raise ValueError('Текущий пароль неверен.')
            if not self.factor(user,code):raise ValueError('Неверный или использованный код 2FA.')
            codes=[]
            if disable:
                for key in ('totp_secret','totp_last_step','recovery_hashes','totp_pending'):user.pop(key,None)
            else:codes,user['recovery_hashes']=recovery_codes(user['id'])
            user['revision']+=1;atomic_json(self.path,stored)
            return public_user(user),codes

    def profile(self,actor,data):
        with self.lock:
            stored=self.load();user=self.own(stored,actor)
            if 'display_name' in data:
                name=str(data['display_name']).strip()
                if len(name)>80 or any(not c.isprintable() for c in name):raise ValueError('Имя: максимум 80 символов.')
                user['display_name']=name
            if 'preferences' in data:
                preferences=data['preferences']
                choices={'design':('titan','paper','console','contour'),'colorScheme':('light','dark'),'language':('ru','en')}
                if not isinstance(preferences,dict) or any(k not in choices or v not in choices[k] for k,v in preferences.items()):raise ValueError('Некорректные настройки пользователя.')
                user['preferences']=user.get('preferences',{})|preferences
            atomic_json(self.path,stored)
            return public_user(user)

    def avatar(self,actor,encoded):
        from PIL import Image,ImageOps
        with self.lock:
            stored=self.load();user=self.own(stored,actor)
            folder=self.path.parent/'avatars';folder.mkdir(exist_ok=True)
            target=folder/(user['id']+'.png')
            if encoded:
                try:
                    raw=base64.b64decode(encoded,validate=True)
                    if len(raw)>2_000_000:raise ValueError()
                    with Image.open(io.BytesIO(raw)) as image:
                        if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>16_000_000:raise ValueError()
                        image=ImageOps.exif_transpose(image)
                        image=ImageOps.fit(image.convert('RGBA'),(256,256))
                        image.info.clear()
                        output=io.BytesIO();image.save(output,format='PNG');content=output.getvalue()
                except Exception:raise ValueError('Выберите PNG, JPEG или WebP до 2 МБ.') from None
                temporary=target.with_suffix('.tmp');temporary.write_bytes(content);temporary.chmod(0o600);temporary.replace(target)
                user['avatar_hash']=hashlib.sha256(content).hexdigest()[:16]
            else:
                target.unlink(missing_ok=True);user.pop('avatar_hash',None)
            atomic_json(self.path,stored)
            return public_user(user)

    def load(self):
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if 'users' not in data:
            backup = self.path.with_name('auth-before-users.json')
            if not backup.exists():
                atomic_json(backup, data)
            data = {'version':2, 'users':[dict(data, id='user_' + uuid.uuid4().hex[:16],
                    role='admin', revision=1, created_at=time.time())]}
            atomic_json(self.path, data)
        return data

    def users(self):
        with self.lock:
            return sorted([public_user(u) for u in self.load()['users']], key=lambda u:u['username'].casefold())

    def authenticate(self, username, password):
        with self.lock:
            users = self.load()['users']
            username = str(username).strip().casefold()
            user = next((u for u in users if u['username'].casefold() == username), None)
            # Unknown usernames use the same hash work as an existing account.
            matched = password_matches(user or users[0], password)
            return public_user(user) if user and matched else None

    def session_user(self, identifier, revision):
        with self.lock:
            user = next((u for u in self.load()['users'] if u['id'] == identifier), None)
            return public_user(user) if user and user['revision'] == revision else None

    def change(self, action, data, actor):
        with self.lock:
            stored = self.load()
            users = stored['users']
            current_actor = next((u for u in users if u['id'] == actor['id']), None)
            if not current_actor or current_actor['revision'] != actor['revision'] or current_actor['role'] != 'admin':
                raise PermissionError('Требуются права администратора.')
            current = next((u for u in users if u['id'] == data.get('id')), None)
            if action != 'add':
                if current is None:
                    raise ValueError('Пользователь не найден.')
                if int(data.get('revision', -1)) != current['revision']:
                    raise ValueError('Пользователь изменился. Обновите страницу.')
            if action == 'delete':
                if current['id'] == actor['id']:
                    raise ValueError('Нельзя удалить собственную учётную запись.')
                users.remove(current)
            elif action in ('add', 'edit'):
                username = str(data.get('username', '')).strip()
                if not 1 <= len(username) <= 64 or any(c.isspace() or not c.isprintable() for c in username):
                    raise ValueError('Логин: от 1 до 64 символов без пробелов.')
                if any(u['id'] != data.get('id') and u['username'].casefold() == username.casefold() for u in users):
                    raise ValueError('Такой логин уже существует.')
                role = data.get('role', 'operator')
                if role not in ('admin', 'operator'):
                    raise ValueError('Некорректная роль.')
                if action == 'add':
                    if len(users) >= 100:
                        raise ValueError('Максимум 100 пользователей.')
                    current = dict(password_hash(data.get('password')), id='user_' + uuid.uuid4().hex[:16],
                                   revision=0, created_at=time.time())
                    users.append(current)
                elif data.get('password'):
                    current.update(password_hash(data['password']))
                current.update(username=username, role=role, revision=current['revision'] + 1)
            else:
                raise ValueError('Некорректное действие.')
            if not any(u['role'] == 'admin' for u in users):
                raise ValueError('Должен остаться хотя бы один администратор.')
            atomic_json(self.path, stored)
            return public_user(current) if action != 'delete' else None

    def change_password(self, actor, current_password, new_password):
        with self.lock:
            stored = self.load()
            user = next((u for u in stored['users'] if u['id'] == actor['id']), None)
            if not user or user['revision'] != actor['revision'] or not password_matches(user, current_password):
                raise ValueError('Текущий пароль неверен.')
            user.update(password_hash(new_password))
            user['revision'] += 1
            atomic_json(self.path, stored)
            return public_user(user)

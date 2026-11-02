"""Persistent panel accounts, legacy migration and session-version revocation."""
import hashlib
import hmac
import json
import secrets
import time
import uuid
from controller import atomic_json

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
    return {key:user[key] for key in ('id', 'username', 'role', 'revision')}


class Accounts:
    def __init__(self, path, lock):
        self.path, self.lock = path, lock

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

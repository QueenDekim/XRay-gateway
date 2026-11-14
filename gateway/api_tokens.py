"""Named, revocable API credentials bound to an account's security revision."""
import hashlib
import hmac
import re
import secrets
import time

from accounts import public_user
from controller import atomic_json


TOKEN = re.compile(r'xg_([0-9a-f]{16})\.[A-Za-z0-9_-]{43}')


class ApiTokens:
    def __init__(self, accounts):
        self.accounts = accounts

    @staticmethod
    def public(item, user):
        return {key: item[key] for key in ('id', 'name', 'prefix', 'created_at', 'expires_at')} | {
            'active': (item['expires_at'] is None or item['expires_at'] > time.time()) and item['revision'] == user['revision']}

    def list(self, actor):
        with self.accounts.lock:
            user = self.accounts.own(self.accounts.load(), actor)
            return [self.public(item, user) for item in user.get('api_tokens', [])]

    def create(self, actor, data):
        name = data.get('name', '')
        days = data.get('days', 90)
        no_expiry = data.get('no_expiry', False)
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or not all(c.isprintable() for c in name):
            raise ValueError('Название токена: от 1 до 80 символов.')
        if not isinstance(no_expiry, bool):
            raise ValueError('Параметр «Без окончания» должен быть логическим значением.')
        if not no_expiry and (isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365):
            raise ValueError('Срок действия токена: от 1 до 365 дней.')
        with self.accounts.lock:
            stored = self.accounts.load()
            user = self.accounts.own(stored, actor)
            active = [item for item in user.get('api_tokens', []) if self.public(item, user)['active']]
            if len(active) >= 20:
                raise ValueError('Максимум 20 действующих API-токенов.')
            if user.get('totp_secret') and not self.accounts.factor(user, str(data.get('code', ''))):
                raise ValueError('Неверный или использованный код 2FA.')
            identifier = secrets.token_hex(8)
            value = 'xg_' + identifier + '.' + secrets.token_urlsafe(32)
            now = time.time()
            item = {'id': identifier, 'name': name.strip(), 'prefix': 'xg_' + identifier,
                    'created_at': now, 'expires_at': None if no_expiry else now + days * 86400,
                    'revision': user['revision'], 'hash': hashlib.sha256(value.encode()).hexdigest()}
            user['api_tokens'] = active + [item]
            atomic_json(self.accounts.path, stored)
            return {'token': value, 'item': self.public(item, user), 'user': public_user(user)}

    def revoke(self, actor, identifier):
        with self.accounts.lock:
            stored = self.accounts.load()
            user = self.accounts.own(stored, actor)
            items = user.get('api_tokens', [])
            if not any(item['id'] == identifier for item in items):
                raise ValueError('API-токен не найден.')
            user['api_tokens'] = [item for item in items if item['id'] != identifier]
            atomic_json(self.accounts.path, stored)

    def authenticate(self, value):
        match = TOKEN.fullmatch(value)
        if not match:
            return None
        digest = hashlib.sha256(value.encode()).hexdigest()
        with self.accounts.lock:
            for user in self.accounts.load()['users']:
                item = next((item for item in user.get('api_tokens', []) if item['id'] == match[1]), None)
                if item and hmac.compare_digest(item['hash'], digest) and self.public(item, user)['active']:
                    return {'id': item['id'], 'expires': item['expires_at'], 'user': public_user(user)}
        return None

"""Bounded request quotas and persistent escalating authentication lockouts."""
import collections
import hashlib
import ipaddress
import json
import math
import os
import time

from controller import atomic_json


class AuthRateLimit(Exception):
    def __init__(self, seconds):
        self.seconds = max(1, math.ceil(seconds))


class AuthRate:
    DELAYS = (60, 300, 900, 3600, 86400)

    def __init__(self, directory, lock):
        self.path = directory / 'auth-rate.json'
        self.lock = lock
        self.limit = self.setting('AUTH_FAILURE_LIMIT', 5, 2, 100)
        self.requests = {}
        try:
            if self.path.stat().st_size > 2_000_000:raise ValueError('Oversized authentication state')
            self.records = json.loads(self.path.read_text())
            if not isinstance(self.records, dict) or len(self.records) > 8192:raise ValueError('Invalid authentication state')
        except FileNotFoundError:self.records = {}
        self.proxies = [ipaddress.ip_network(value.strip()) for value in os.environ.get('TRUSTED_PROXY_NETWORKS', '').split(',') if value.strip()]

    @staticmethod
    def setting(name, default, minimum, maximum):
        value = int(os.environ.get(name, default))
        if not minimum <= value <= maximum:raise ValueError('Invalid ' + name)
        return value

    def peer(self, address, forwarded=''):
        current = ipaddress.ip_address(address)
        for raw in reversed(forwarded.split(',')):
            if not any(current in network for network in self.proxies):break
            try:current = ipaddress.ip_address(raw.strip())
            except ValueError:break
        return str(current)

    @staticmethod
    def key(kind, value):
        return hashlib.sha256((kind + ':' + value).encode()).hexdigest()

    def keys(self, kind, peer, username=None):
        keys = [(self.key(kind + '-ip', peer), self.limit * (4 if kind == 'login' else 1))]
        if username is not None:keys.append((self.key('login-user', str(username).strip().casefold()[:1024]), self.limit))
        return keys

    def before(self, kind, peer, username=None, count=True):
        now = time.time()
        with self.lock:
            for key, _ in self.keys(kind, peer, username):
                if self.records.get(key, {}).get('until', 0) > now:raise AuthRateLimit(self.records[key]['until'] - now)
            if not count:return
            quota = self.setting('API_AUTH_REQUESTS_PER_MINUTE', 300, 10, 10000) if kind == 'bearer' else self.setting('AUTH_REQUESTS_PER_MINUTE', 30, 5, 1000)
            key = self.key(kind + '-requests', peer)
            if key not in self.requests:
                self.requests = {k:v for k,v in self.requests.items() if v and v[-1] > now - 60}
                if len(self.requests) >= 8192:raise AuthRateLimit(60)
            values = self.requests.setdefault(key, collections.deque())
            while values and values[0] <= now - 60:values.popleft()
            if len(values) >= quota:raise AuthRateLimit(values[0] + 60 - now)
            values.append(now)

    def failed(self, kind, peer, username=None):
        now = time.time()
        with self.lock:
            keys = self.keys(kind, peer, username)
            for key, limit in keys:
                if key not in self.records and len(self.records) >= 8192:
                    self.records = {k:v for k,v in self.records.items() if v.get('updated', 0) > now - 172800 or v.get('until', 0) > now}
                    if len(self.records) >= 8192:raise AuthRateLimit(60)
                record = self.records.setdefault(key, {})
                if record.get('until', 0) > now:continue
                if record.get('updated', 0) <= now - 86400:record.clear()
                failures = [stamp for stamp in record.get('failures', []) if stamp > now - 900]
                failures.append(now)
                if len(failures) >= limit:
                    level = record.get('level', 0)
                    record.update(level=min(level + 1, len(self.DELAYS)), until=now + self.DELAYS[min(level, len(self.DELAYS) - 1)])
                    failures = []
                record.update(failures=failures, updated=now)
            atomic_json(self.path, self.records)
            self.before(kind, peer, username, count=False)

    def succeeded(self, username):
        with self.lock:
            if self.records.pop(self.key('login-user', str(username).strip().casefold()[:1024]), None) is not None:
                atomic_json(self.path, self.records)

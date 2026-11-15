import http.client
import json
import os
import time
import unittest
from unittest.mock import patch

import test_panel
from auth_rate import AuthRate


class AuthenticationRateTests(unittest.TestCase):
    setUp = test_panel.PanelTest.setUp
    tearDown = test_panel.PanelTest.tearDown
    request = test_panel.PanelTest.request
    candidate = test_panel.PanelTest.candidate

    def call(self, path, data=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request('POST' if data is not None else 'GET', path,
            body=json.dumps(data) if data is not None else None,
            headers={'Content-Type': 'application/json'} | (headers or {}))
        response = connection.getresponse()
        result = response.status, json.loads(response.read()), dict(response.getheaders())
        connection.close()
        return result

    def test_password_lockout_escalates_and_persists_without_extending_on_retry(self):
        now = time.time()
        with patch('auth_rate.time.time', return_value=now) as clock:
            for level, seconds in enumerate([60, 300, 900]):
                for attempt in range(5):
                    status, body, headers = self.call('/auth/login', {'username': 'AdMiN', 'password': 'wrong'})
                    self.assertEqual(status, 429 if attempt == 4 else 401)
                self.assertEqual(body['retry_after'], seconds)
                self.assertEqual(int(headers['Retry-After']), seconds)
                # Reload the throttle to simulate a service restart.
                self.c.auth_rate = AuthRate(self.root, self.c.lock)
                clock.return_value += 10
                status, body, _ = self.call('/auth/login', {'username': 'admin', 'password': 'test-password'})
                self.assertEqual(status, 429)
                self.assertEqual(body['retry_after'], seconds - 10)
                clock.return_value += seconds - 9
            self.assertEqual(self.call('/auth/login', {'username': 'admin', 'password': 'test-password'})[0], 200)
            state = (self.root / 'auth-rate.json').read_text()
            self.assertNotIn('wrong', state)
            self.assertNotIn('admin', state)

    def test_login_request_quota_applies_to_successful_password_checks(self):
        with patch.dict(os.environ, {'AUTH_REQUESTS_PER_MINUTE': '5'}):
            for _ in range(5):self.assertEqual(self.call('/auth/login', {'username': 'admin', 'password': 'test-password'})[0], 200)
            status, body, headers = self.call('/auth/login', {'username': 'admin', 'password': 'test-password'})
            self.assertEqual(status, 429)
            self.assertGreater(body['retry_after'], 0)
            self.assertEqual(headers['Retry-After'], str(body['retry_after']))

    def test_bad_bearer_tokens_are_limited_without_password_fallback(self):
        for number in range(5):
            status, body, headers = self.call('/api/state', headers={'Authorization': 'Bearer invalid-' + str(number)})
            self.assertEqual(status, 401 if number < 4 else 429)
        self.assertEqual(int(headers['Retry-After']), 60)
        self.assertEqual(self.call('/api/state', headers={'Authorization': 'Bearer other'})[0], 429)
        # Web sign-in has a separate quota from token validation.
        self.assertEqual(self.call('/auth/login', {'username': 'admin', 'password': 'test-password'})[0], 200)

    def test_old_password_api_routes_do_not_authenticate(self):
        for path in ['/api/login', '/api/login/2fa', '/api/logout']:
            self.assertEqual(self.call(path, {'username': 'admin', 'password': 'test-password'})[0], 404)
            self.assertEqual(self.call(path)[0], 404)

    def test_valid_bearer_requests_have_a_separate_request_quota(self):
        from accounts import Accounts
        from api_tokens import ApiTokens
        accounts = Accounts(self.root / 'auth.json', self.c.lock)
        actor = accounts.authenticate('admin', 'test-password')
        token = ApiTokens(accounts).create(actor, {'name': 'Quota test'})['token']
        with patch.dict(os.environ, {'API_AUTH_REQUESTS_PER_MINUTE': '10'}):
            for _ in range(10):self.assertEqual(self.call('/api/state', headers={'Authorization': 'Bearer ' + token})[0], 200)
            status, _, headers = self.call('/api/state', headers={'Authorization': 'Bearer ' + token})
            self.assertEqual(status, 429)
            self.assertGreater(int(headers['Retry-After']), 0)

    def test_password_confirmation_is_limited_without_blocking_read_only_access(self):
        _, _, response = self.call('/auth/login', {'username': 'admin', 'password': 'test-password'})
        headers = {'Cookie': response['Set-Cookie'].split(';')[0]}
        headers['X-CSRF-Token'] = self.call('/api/state', headers=headers)[1]['csrf']
        for attempt in range(5):
            status = self.call('/api/password', {'current_password': 'wrong', 'password': 'replacement-password'}, headers)[0]
            self.assertEqual(status, 429 if attempt == 4 else 400)
        self.assertEqual(self.call('/api/state', headers=headers)[0], 200)

    def test_forwarded_addresses_are_used_only_for_explicitly_trusted_proxies(self):
        rate = AuthRate(self.root, self.c.lock)
        self.assertEqual(rate.peer('127.0.0.1', '198.51.100.7'), '127.0.0.1')
        with patch.dict(os.environ, {'TRUSTED_PROXY_NETWORKS': '127.0.0.1/32,10.0.0.0/24'}):
            rate = AuthRate(self.root, self.c.lock)
        self.assertEqual(rate.peer('127.0.0.1', '198.51.100.7,10.0.0.2'), '198.51.100.7')
        self.assertEqual(rate.peer('127.0.0.1', 'spoofed,198.51.100.7,10.0.0.2'), '198.51.100.7')
        self.assertEqual(rate.peer('192.0.2.4', '198.51.100.7'), '192.0.2.4')

    def test_renamed_accounts_and_unknown_names_do_not_bypass_address_failures(self):
        for number in range(20):
            status = self.call('/auth/login', {'username': 'unknown-' + str(number), 'password': 'wrong'})[0]
            self.assertEqual(status, 401 if number < 19 else 429)
        self.assertEqual(self.call('/auth/login', {'username': 'admin', 'password': 'test-password'})[0], 429)

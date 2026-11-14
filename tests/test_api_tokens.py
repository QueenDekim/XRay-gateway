import hashlib
import json
import time
import unittest
from unittest.mock import patch

import test_panel as panel_tests
URI = panel_tests.URI
from accounts import Accounts
from api_tokens import ApiTokens
from two_factor import totp


class ApiTokenTests(unittest.TestCase):
    setUp = panel_tests.PanelTest.setUp
    tearDown = panel_tests.PanelTest.tearDown
    request = panel_tests.PanelTest.request
    auth = panel_tests.PanelTest.auth
    candidate = panel_tests.PanelTest.candidate

    def initialize(self):
        self.handler.token_sessions = {}
        self.handler.security_attempts = {}
        headers = self.auth()
        self.accounts = Accounts(self.root / 'auth.json', self.c.lock)
        self.tokens = ApiTokens(self.accounts)
        return headers

    def issue(self, headers, **data):
        status, result, cookie = self.request('/api/account/tokens/create', {'name': 'Automation', 'days': 90} | data, headers)
        self.assertEqual(status, 201, result)
        self.assertIsNone(cookie)
        return result

    def test_bearer_reads_and_writes_without_cookie_or_csrf_and_keeps_browser_csrf(self):
        browser = self.initialize()
        created = self.issue(browser)
        bearer = {'Authorization': 'Bearer ' + created['token']}
        status, state, cookie = self.request('/api/state', headers=bearer)
        self.assertEqual(status, 200)
        self.assertEqual(state['user']['role'], 'admin')
        self.assertEqual(state['csrf'], '')
        self.assertIsNone(cookie)
        self.assertEqual(self.request('/api/ip-lists/add', {'name': 'Test', 'addresses': 'example.org\n1.1.1.1'}, bearer)[0], 200)
        self.assertEqual(self.request('/api/ip-lists/add', {'name': 'Blocked', 'addresses': '2.2.2.2'}, {'Cookie': browser['Cookie']})[0], 403)
        self.assertEqual(self.request('/api/state', headers=bearer | {'Origin': 'https://other.example'})[0], 200)
        self.assertEqual(self.request('/api/ip-lists/add', {'name': 'Blocked', 'addresses': '2.2.2.2'}, bearer | {'Origin': 'https://other.example'})[0], 403)

    def test_only_hash_is_persisted_and_secret_is_not_returned_by_list_or_state(self):
        browser = self.initialize()
        created = self.issue(browser)
        token = created['token']
        raw = (self.root / 'auth.json').read_text()
        self.assertNotIn(token, raw)
        self.assertNotIn(token.split('.')[1], raw)
        self.assertIn(hashlib.sha256(token.encode()).hexdigest(), raw)
        for path in ['/api/account/tokens', '/api/state']:
            status, value, _ = self.request(path, headers=browser)
            self.assertEqual(status, 200)
            self.assertNotIn(token, json.dumps(value))
            self.assertNotIn('"hash"', json.dumps(value))
        self.assertIsNotNone(ApiTokens(Accounts(self.root / 'auth.json', self.c.lock)).authenticate(token))

    def test_bad_expired_revoked_tokens_never_fall_back_to_valid_cookie(self):
        browser = self.initialize()
        created = self.issue(browser)
        good = {'Authorization': 'Bearer ' + created['token']}
        for value in ['Basic abc', 'Bearer bad', 'bearer ' + created['token'][:-1] + '!', 'Bearer ' + 'a' * 200]:
            self.assertEqual(self.request('/api/state', headers=browser | {'Authorization': value})[0], 401)
        self.assertEqual(self.request('/api/state', headers={'Authorization': 'bearer ' + created['token']})[0], 200)
        with patch('api_tokens.time.time', return_value=time.time() + 91 * 86400):
            self.assertEqual(self.request('/api/state', headers=good)[0], 401)
        self.assertEqual(self.request('/api/account/tokens/revoke', {'id': created['item']['id']}, browser)[0], 200)
        self.assertEqual(self.request('/api/state', headers=good)[0], 401)

    def test_token_cannot_manage_tokens_log_in_to_documents_or_increase_reader_permissions(self):
        browser = self.initialize()
        payload = {'username': 'reader', 'role': 'operator', 'password': 'reader-password'}
        self.assertEqual(self.request('/api/users/add', payload, browser)[0], 200)
        reader = self.auth('reader', 'reader-password')
        token = self.issue(reader)
        bearer = {'Authorization': 'Bearer ' + token['token']}
        self.assertEqual(self.request('/api/state', headers=bearer)[0], 200)
        self.assertEqual(self.request('/profiles', headers=bearer)[0], 303)
        self.assertEqual(self.request('/api/ip-lists/add', {'name': 'Forbidden', 'addresses': '1.1.1.1'}, bearer)[0], 403)
        self.assertEqual(self.request('/api/account/tokens', headers=bearer)[0], 403)
        for path in ['/api/account/tokens/create', '/api/account/tokens/revoke', '/api/logout']:
            self.assertEqual(self.request(path, {'name': 'Forbidden', 'id': token['item']['id']}, bearer)[0], 403)
        self.assertEqual(self.request('/api/account/tokens/revoke', {'id': token['item']['id']}, browser)[0], 400)
        self.assertEqual(self.request('/api/state', headers=bearer)[0], 200)

    def test_password_security_revision_and_user_deletion_invalidate_tokens(self):
        browser = self.initialize()
        token = self.issue(browser, no_expiry=True)['token']
        self.assertEqual(self.request('/api/password', {'current_password': 'test-password', 'password': 'replacement-password'}, browser)[0], 200)
        self.assertEqual(self.request('/api/state', headers={'Authorization': 'Bearer ' + token})[0], 401)
        status, result, _ = self.request('/api/users/add', {'username': 'reader', 'role': 'operator', 'password': 'reader-password'}, browser)
        self.assertEqual(status, 200)
        reader = self.auth('reader', 'reader-password')
        reader_token = self.issue(reader)['token']
        user = result['user']
        self.assertEqual(self.request('/api/users/delete', {'id': user['id'], 'revision': user['revision']}, browser)[0], 200)
        self.assertEqual(self.request('/api/state', headers={'Authorization': 'Bearer ' + reader_token})[0], 401)

    def test_mfa_required_on_every_issue_and_consumed_recovery_code_cannot_repeat(self):
        browser = self.initialize()
        _, setup, _ = self.request('/api/account/2fa/setup', {'password': 'test-password'}, browser)
        code = totp(setup['secret'], int(time.time() // 30))
        status, enabled, _ = self.request('/api/account/2fa/enable', {'code': code}, browser)
        self.assertEqual(status, 200)
        self.handler.security_attempts = {}
        for data in [{}, {'code': 'invalid'}, {'code': code}]:
            self.assertEqual(self.request('/api/account/tokens/create', {'name': 'Protected'} | data, browser)[0], 400)
        created = self.issue(browser, code=enabled['recovery_codes'][0], no_expiry=True)
        self.assertIsNone(created['item']['expires_at'])
        self.assertEqual(created['user']['recovery_remaining'], 9)
        self.assertEqual(self.request('/api/account/tokens/create', {'name': 'Replay', 'code': enabled['recovery_codes'][0]}, browser)[0], 400)
        self.assertEqual(len(self.tokens.list(created['user'])), 1)
        self.assertEqual(self.request('/api/account/tokens/create', {'name': 'Rate limit', 'code': enabled['recovery_codes'][1]}, browser)[0], 429)

    def test_fresh_totp_allows_issue_once_and_account_revision_invalidates_old_tokens(self):
        browser = self.initialize()
        old = self.issue(browser)['token']
        _, setup, _ = self.request('/api/account/2fa/setup', {'password': 'test-password'}, browser)
        step = int(time.time() // 30)
        self.assertEqual(self.request('/api/account/2fa/enable', {'code': totp(setup['secret'], step)}, browser)[0], 200)
        self.assertIsNone(self.tokens.authenticate(old))
        with patch('two_factor.time.time', return_value=(step + 1) * 30 + 1):
            fresh = totp(setup['secret'], step + 1)
            self.issue(browser, code=fresh)
            self.assertEqual(self.request('/api/account/tokens/create', {'name': 'Replay', 'code': fresh}, browser)[0], 400)

    def test_bearer_subscription_preview_remains_bound_to_credential(self):
        browser = self.initialize()
        a = {'Authorization': 'Bearer ' + self.issue(browser, name='A', no_expiry=True)['token']}
        b = {'Authorization': 'Bearer ' + self.issue(browser, name='B')['token']}
        source = 'https://example.org/sub/test'
        with patch('controller.fetch_subscription', return_value=URI.encode()):
            status, preview, _ = self.request('/api/profiles/preview', {'uri': source}, a)
        self.assertEqual(status, 200)
        payload = {'name': 'Primary', 'priority': 10, 'enabled': True, 'revision': self.c.revision,
                   'uri': source, 'subscription_token': preview['token'], 'subscription_profiles': [preview['profiles'][0]['id']]}
        self.assertEqual(self.request('/api/profiles/add', payload, b)[0], 400)
        self.assertEqual(self.request('/api/profiles/add', payload, a)[0], 200)

    def test_input_validation_and_active_token_limit(self):
        browser = self.initialize()
        user = self.request('/api/state', headers=browser)[1]['user']
        for data in [{'name': ''}, {'name': 'x', 'days': True}, {'name': 'x', 'days': 0}, {'name': 'x', 'days': 366},
                     {'name': 'x', 'no_expiry': 'true'}, {'name': 'x', 'no_expiry': 1}, {'name': 'x', 'no_expiry': None}]:
            with self.assertRaises(ValueError):self.tokens.create(user, data)
        for index in range(20):self.tokens.create(user, {'name': str(index), 'no_expiry': True})
        with self.assertRaises(ValueError):self.tokens.create(user, {'name': 'Too many'})

    def test_no_expiry_survives_time_and_reload_but_can_be_revoked(self):
        browser = self.initialize()
        created = self.issue(browser, no_expiry=True)
        self.assertIsNone(created['item']['expires_at'])
        bearer = {'Authorization': 'Bearer ' + created['token']}
        with patch('api_tokens.time.time', return_value=time.time() + 100 * 365 * 86400):
            self.assertEqual(self.request('/api/state', headers=bearer)[0], 200)
            loaded = ApiTokens(Accounts(self.root / 'auth.json', self.c.lock))
            self.assertIsNotNone(loaded.authenticate(created['token']))
            items = loaded.list(created['user'])
            self.assertTrue(items[0]['active'])
            self.assertIsNone(items[0]['expires_at'])
        self.assertEqual(self.request('/api/account/tokens/revoke', {'id': created['item']['id']}, browser)[0], 200)
        self.assertEqual(self.request('/api/state', headers=bearer)[0], 401)

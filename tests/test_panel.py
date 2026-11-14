import hashlib
import http.client
import http.server
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'gateway'), str(ROOT / 'scripts')]
from controller import Controller, configuration, atomic_json, routeros
from panel import Panel

URI = 'vless://00000000-0000-0000-0000-000000000000@example.org:443?type=tcp&security=reality&pbk=test&sid=aa&sni=example.com'


class PanelTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        atomic_json(self.root / 'config.json', {'outbounds': []})
        self.c = Controller(self.root)
        salt = bytes.fromhex('aa' * 24)
        atomic_json(self.root / 'auth.json', {'username': 'admin', 'salt': salt.hex(), 'iterations': 1000,
            'hash': hashlib.pbkdf2_hmac('sha256', b'test-password', salt, 1000).hex()})
        self.c.validate = lambda profiles: self.candidate(profiles)
        self.c.restart = lambda: None
        self.c.collect = lambda: None
        self.handler = type('TestPanel', (Panel,), {'controller': self.c, 'sessions': {}, 'defaults': ['1.1.1.1'],
            'snapshot': staticmethod(lambda: {'profiles': self.c.public_profiles(), 'revision': self.c.revision})})
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), self.handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def candidate(self, profiles):
        path = self.root / 'candidate.json'
        atomic_json(path, configuration(profiles))
        return path

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.c.db.close()
        self.temp.cleanup()

    def request(self, path, data=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request('POST' if data is not None else 'GET', path, body=json.dumps(data) if data is not None else None,
            headers={'Content-Type': 'application/json', **(headers or {})})
        response = conn.getresponse()
        raw = response.read()
        value = json.loads(raw) if 'json' in response.getheader('Content-Type', '') else raw
        result = response.status, value, response.getheader('Set-Cookie')
        conn.close()
        return result

    def auth(self, username='admin', password='test-password'):
        status, _, cookie = self.request('/api/login', {'username': username, 'password': password})
        self.assertEqual(status, 200)
        cookie = cookie.split(';')[0]
        _, data, _ = self.request('/api/state', headers={'Cookie': cookie})
        return {'Cookie': cookie, 'X-CSRF-Token': data['csrf']}

    def test_profile_accepts_blank_tcp_header_and_subscription_url(self):
        import base64
        headers=self.auth()
        payload={'name':'Primary','uri':URI+'&headerType=','priority':1,'enabled':True,'revision':self.c.revision}
        self.assertEqual(self.request('/api/profiles/add',payload,headers)[0],200)
        profile=self.c.list_profiles()[0]
        self.assertEqual(profile['node']['streamSettings']['tcpSettings']['header']['type'],'none')
        before=profile['id'],profile['slot']
        subscription='http://example.org/sub/private-token'
        payload.update(id=profile['id'],uri=subscription,revision=self.c.revision)
        with patch('controller.fetch_subscription',return_value=base64.b64encode((URI+'&headerType=').encode())) as fetch:
            self.assertEqual(self.request('/api/profiles/edit',payload,headers)[0],200)
            fetch.assert_called_once_with(subscription,allow_http=True)
        profile=self.c.list_profiles()[0]
        self.assertEqual((profile['id'],profile['slot']),before)
        self.assertNotIn(subscription,json.dumps(self.c.load('profiles',[])))

    def test_profile_subscription_errors_are_specific_localized_and_redacted(self):
        headers=self.auth()
        payload={'name':'Primary','uri':'https://example.org/sub/private-token','priority':1,'enabled':True,'revision':self.c.revision}
        with patch('controller.fetch_subscription',side_effect=OSError('connection failed '+payload['uri'])):
            status,result,_=self.request('/api/profiles/add',payload,headers|{'Accept-Language':'en'})
        self.assertEqual(status,400)
        self.assertEqual(result['error'],'Could not download the subscription. Check the URL and server availability.')
        self.assertNotIn('private-token',json.dumps(result))
        self.assertEqual(self.c.list_profiles(),[])
        with patch('controller.fetch_subscription',return_value=b'not a subscription'):
            status,result,_=self.request('/api/profiles/add',payload,headers)
        self.assertEqual(status,400)
        self.assertIn('В подписке нет поддерживаемого',result['error'])

    def test_subscription_fetch_rechecks_revision_and_does_not_lock_readers(self):
        headers=self.auth()
        def fetch(*args,**kwargs):
            acquired=threading.Event()
            def reader():
                with self.c.lock:acquired.set()
            thread=threading.Thread(target=reader);thread.start()
            self.assertTrue(acquired.wait(1));thread.join()
            with self.c.lock:self.c.revision+=1
            return URI.encode()
        payload={'name':'Primary','uri':'https://example.org/sub/token','priority':1,'enabled':True,'revision':self.c.revision}
        with patch('controller.fetch_subscription',side_effect=fetch):
            status,result,_=self.request('/api/profiles/add',payload,headers)
        self.assertEqual(status,400)
        self.assertEqual(result['error'],'Список уже изменился. Обновите страницу и повторите действие.')
        self.assertEqual(self.c.list_profiles(),[])

    def test_subscription_prefers_existing_transport(self):
        from controller import resolve_profile_source
        with patch('controller.fetch_subscription',return_value=(URI+'\n'+URI.replace('type=tcp','type=xhttp')).encode()):
            node=resolve_profile_source('https://example.org/sub/token','xhttp')
        self.assertEqual(node['streamSettings']['network'],'xhttp')

    def test_subscription_prefers_existing_security_and_api_exposes_it(self):
        from controller import resolve_profile_source
        tls=URI.replace('type=tcp','type=xhttp').replace('security=reality','security=tls')
        reality=URI.replace('type=tcp','type=xhttp')
        with patch('controller.fetch_subscription',return_value=(tls+'\n'+reality).encode()):
            node=resolve_profile_source('https://example.org/sub/token','xhttp','reality')
        self.assertEqual(node['streamSettings']['security'],'reality')
        headers=self.auth()
        payload={'name':'TLS profile','uri':tls+'&fp=firefox&alpn=h2%2Chttp%2F1.1','priority':1,'enabled':True,'revision':self.c.revision}
        self.assertEqual(self.request('/api/profiles/add',payload,headers)[0],200)
        public=self.request('/api/state',headers=headers)[1]['profiles'][0]
        self.assertEqual((public['transport'],public['security']),('xhttp','tls'))
        self.assertNotIn('node',public)
        self.assertNotIn('users',public)

    def test_reset_check_counters_keeps_traffic_health_and_profile_revision(self):
        headers=self.auth()
        self.c.change('add',{'name':'Primary','uri':URI,'priority':1,'enabled':True,'revision':self.c.revision})
        identifier=self.c.profiles[0]['id']
        self.c.stats={identifier:{'checks':12,'successful_checks':10,'uplink':1200,'downlink':9000,'downlink_bps':42},
                      'direct':{'downlink':300}}
        self.c.health={identifier:{'ok':True,'latency_ms':24}}
        revision=self.c.revision
        self.assertEqual(self.request('/api/profiles/reset-checks',{},headers|{'X-CSRF-Token':'invalid'})[0],403)
        self.assertEqual(self.c.stats[identifier]['checks'],12)
        with patch.object(self.c,'restart') as restart:
            self.assertEqual(self.request('/api/profiles/reset-checks',{},headers)[0],200)
        restart.assert_not_called()
        self.assertEqual(self.c.stats[identifier],{'checks':0,'successful_checks':0,'uplink':1200,'downlink':9000,'downlink_bps':42})
        self.assertEqual(self.c.health[identifier],{'ok':True,'latency_ms':24})
        self.assertEqual(self.c.stats['direct'],{'downlink':300})
        self.assertEqual(self.c.revision,revision)
        reopened=Controller(self.root)
        try:self.assertEqual(reopened.stats,self.c.stats)
        finally:reopened.db.close()

    def test_auth_csrf_logout(self):
        self.assertEqual(self.request('/api/state')[0], 401)
        self.assertEqual(self.request('/api/login', {'username': 'admin', 'password': 'wrong'})[0], 401)
        headers = self.auth()
        self.assertEqual(self.request('/api/routeros', {}, {'Cookie': headers['Cookie']})[0], 403)
        self.assertEqual(self.request('/api/logout', {}, headers)[0], 200)
        self.assertEqual(self.request('/api/state', headers=headers)[0], 401)

    def test_favicon_available_before_login_with_png_content_type(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request('GET', '/favicon.png')
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader('Content-Type'), 'image/png')
        self.assertEqual(response.read(), (ROOT / 'gateway/web/favicon.png').read_bytes())
        conn.close()
        self.assertIn(b'href="/favicon.png"', self.request('/login')[1])

    def test_legacy_account_migration_keeps_access_and_redacts_credentials(self):
        original = json.loads((self.root / 'auth.json').read_text())
        headers = self.auth()
        _, state, _ = self.request('/api/state', headers=headers)
        self.assertEqual(state['user']['role'], 'admin')
        self.assertEqual(state['users'][0]['username'], 'admin')
        migrated = json.loads((self.root / 'auth.json').read_text())
        self.assertEqual(migrated['version'], 2)
        self.assertEqual(migrated['users'][0]['hash'], original['hash'])
        self.assertEqual(json.loads((self.root / 'auth-before-users.json').read_text()), original)
        for secret in ('salt', 'iterations', 'hash', 'test-password'):
            self.assertNotIn(secret, json.dumps(state))

    def test_users_permissions_and_case_insensitive_duplicates(self):
        admin = self.auth()
        payload = {'username':'operator', 'password':'Operator-password-123', 'role':'operator'}
        status, data, _ = self.request('/api/users/add', payload, admin)
        self.assertEqual(status, 200)
        self.assertNotIn('hash', data['user'])
        self.assertEqual(self.request('/api/users/add', dict(payload, username='OPERATOR'), admin)[0], 400)
        operator = self.auth('operator', payload['password'])
        _, state, _ = self.request('/api/state', headers=operator)
        self.assertEqual(state['users'], [])
        self.assertEqual(self.request('/api/settings', {'revision':1, 'gateway':'192.168.50.90'}, operator)[0], 403)
        self.assertEqual(self.request('/api/users/add', dict(payload, username='forged', role='admin'), operator)[0], 403)
        self.assertEqual(self.request('/api/routeros', {'destinations':'1.1.1.1'}, operator)[0], 200)

    def test_eight_character_password_for_create_reset_and_self_change(self):
        admin = self.auth()
        self.assertEqual(self.request('/api/users/add', {'username':'short', 'password':'seven77', 'role':'operator'}, admin)[0], 400)
        status, response, _ = self.request('/api/users/add', {'username':'eight', 'password':'eight888', 'role':'operator'}, admin)
        self.assertEqual(status, 200)
        first = self.auth('eight', 'eight888')
        self.assertEqual(self.request('/api/password', {'current_password':'eight888','password':'next8888'}, first)[0], 200)
        self.auth('eight', 'next8888')
        _, current, _ = self.request('/api/state', headers=admin)
        user = next(u for u in current['users'] if u['id'] == response['user']['id'])
        self.assertEqual(self.request('/api/users/edit', dict(user, password='reset888'), admin)[0], 200)
        self.auth('eight', 'reset888')

    def test_password_change_revokes_other_sessions_and_keeps_current(self):
        admin = self.auth()
        self.request('/api/users/add', {'username':'operator', 'password':'Operator-password-123', 'role':'operator'}, admin)
        first = self.auth('operator', 'Operator-password-123')
        second = self.auth('operator', 'Operator-password-123')
        self.assertEqual(self.request('/api/password', {'current_password':'wrong', 'password':'Replacement-password-123'}, first)[0], 400)
        self.assertEqual(self.request('/api/password', {'current_password':'Operator-password-123', 'password':'short'}, first)[0], 400)
        self.assertEqual(self.request('/api/password', {'current_password':'Operator-password-123', 'password':'Replacement-password-123'}, first)[0], 200)
        self.assertEqual(self.request('/api/state', headers=first)[0], 200)
        self.assertEqual(self.request('/api/state', headers=second)[0], 401)
        self.assertEqual(self.request('/api/login', {'username':'operator', 'password':'Operator-password-123'})[0], 401)
        self.auth('operator', 'Replacement-password-123')

    def test_user_reset_delete_and_last_administrator(self):
        admin = self.auth()
        _, state, _ = self.request('/api/state', headers=admin)
        own = state['user']
        self.assertEqual(self.request('/api/users/delete', own, admin)[0], 400)
        self.assertEqual(self.request('/api/users/edit', dict(own, role='operator'), admin)[0], 400)
        _, data, _ = self.request('/api/users/add', {'username':'second', 'password':'Second-password-123', 'role':'admin'}, admin)
        user = data['user']
        session = self.auth('second', 'Second-password-123')
        _, changed, _ = self.request('/api/users/edit', dict(user, username='renamed', role='operator', password='Reset-password-123'), admin)
        self.assertEqual(self.request('/api/state', headers=session)[0], 401)
        self.assertEqual(self.request('/api/users/delete', user, admin)[0], 400)
        renamed = self.auth('renamed', 'Reset-password-123')
        self.assertEqual(self.request('/api/settings', {'revision':1}, renamed)[0], 403)
        self.assertEqual(self.request('/api/users/delete', changed['user'], admin)[0], 200)
        self.assertEqual(self.request('/api/state', headers=renamed)[0], 401)

    def test_settings_persist_validate_and_control_routeros_addresses(self):
        admin = self.auth()
        _, state, _ = self.request('/api/state', headers=admin)
        self.assertEqual(state['settings']['source'], '192.168.50.0/24')
        status, result, _ = self.request('/api/settings', {'revision':1, 'gateway':'192.168.50.90', 'host':'192.168.50.91',
            'source':'192.168.50.95/32', 'check_interval':15}, admin)
        self.assertEqual(status, 200)
        self.assertTrue(self.c.wake.is_set())
        settings = result['settings']
        other = Controller(self.root)
        try:
            self.assertEqual(other.settings(), settings)
        finally:
            other.db.close()
        _, generated, _ = self.request('/api/routeros', {'destinations':'1.1.1.1', 'gateway':'8.8.8.8', 'host':'9.9.9.9'}, admin)
        self.assertIn('gateway=192.168.50.90@main', generated['script'])
        self.assertIn('address=192.168.50.91', generated['script'])
        self.assertIn('src-address=192.168.50.95/32', generated['script'])
        self.assertNotIn('gateway=8.8.8.8', generated['script'])
        self.assertEqual(self.request('/api/settings', {'revision':1, 'source':'10.0.0.0/8'}, admin)[0], 400)
        for invalid in [{'source':'::/0'}, {'interface':'bridge; /quit'}, {'local_networks':'0.0.0.0/0'},
                        {'probe_url':'http://example.com'}, {'probe_url':'https://u:p@example.com'},
                        {'probe_url':'https://example.com/\n'}, {'check_interval':4}, {'fail_threshold':0}, {'recover_threshold':True}]:
            self.assertEqual(self.request('/api/settings', dict(invalid, revision=2), admin)[0], 400)
        self.assertEqual(self.c.settings(), settings)

    def test_crud_and_credentials_redaction(self):
        headers = self.auth()
        payload = {'name': 'Test', 'priority': 5, 'enabled': True, 'uri': URI, 'revision': 1}
        self.assertEqual(self.request('/api/profiles/add', payload, headers)[0], 200)
        _, data, _ = self.request('/api/state', headers=headers)
        self.assertNotIn('00000000', json.dumps(data))
        identifier = data['profiles'][0]['id']
        self.assertEqual(self.c.profiles[0]['slot'], 4)
        payload.update(id=identifier, name='Updated', uri='', revision=2, enabled=False)
        self.assertEqual(self.request('/api/profiles/edit', payload, headers)[0], 200)
        self.assertEqual(self.c.profiles[0]['name'], 'Updated')
        self.assertEqual(self.request('/api/profiles/delete', {'id': identifier, 'revision': 3}, headers)[0], 200)
        self.assertEqual(self.c.profiles, [])
        self.assertGreaterEqual(self.c.load('next_slot', 0), 5)

    def test_failed_restart_rolls_back_config_and_profiles(self):
        before = self.c.config.read_bytes()
        calls = []
        def restart():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError('failed restart')
        self.c.restart = restart
        with self.assertRaises(RuntimeError):
            self.c.change('add', {'name': 'Test', 'uri': URI, 'revision': 1})
        self.assertEqual(self.c.config.read_bytes(), before)
        self.assertEqual(self.c.profiles, [])
        self.assertEqual(len(calls), 2)

    def test_stale_revision_rejected(self):
        with self.assertRaises(ValueError):
            self.c.change('add', {'name': 'Test', 'uri': URI, 'revision': 0})

    def test_routeros_validation_and_safe_scope(self):
        script = routeros({}, ['1.1.1.1', '2606:4700:4700::1111'])
        self.assertIn('src-address=192.168.50.0/24', script)
        self.assertIn('disabled=yes comment=XRAY-GW-ROUTE', script)
        self.assertIn('/ipv6 firewall address-list add list=XRAY-DEST-manual address=2606:4700:4700::1111/128', script)
        self.assertIn('IPv6 VPN routing is not configured', script)
        for value in ('bridge; /quit', '$(bad)', 'br"local'):
            with self.assertRaises(ValueError):
                routeros({'interface': value}, ['1.1.1.1'])
        with self.assertRaises(ValueError):
            routeros({'destinations': '10.0.0.1'}, [])

    def test_routeros_local_destinations_never_get_vpn_mark(self):
        script = routeros({'local_networks': '203.0.113.0/24'}, ['1.1.1.1'])
        for prefix in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '203.0.113.0/24'):
            self.assertIn('list=XRAY-LOCAL-manual address=' + prefix, script)
        bypass = next(line for line in script.splitlines() if 'comment=XRAY-GW-LOCAL' in line and ' add ' in line)
        mark = next(line for line in script.splitlines() if 'action=mark-routing' in line)
        entry = next(line for line in script.splitlines() if 'chain=prerouting' in line and ' add ' in line)
        self.assertIn('action=return dst-address-list=XRAY-LOCAL-manual', bypass)
        self.assertIn('dst-address-list=!XRAY-LOCAL-manual', mark)
        self.assertIn('action=jump jump-target=XRAY-GW-POLICY-manual', entry)
        self.assertLess(script.index(bypass), script.index(mark))
        self.assertIn('/ip address find where disabled=no', script)
        self.assertIn('find list=XRAY-LOCAL-manual address=$subnet', script)
        self.assertNotIn('action=accept chain=prerouting', script)
        for bad in ('0.0.0.0/0', 'bad', '10.0.0.0/8; /quit'):
            with self.assertRaises(ValueError):
                routeros({'local_networks': bad}, ['1.1.1.1'])

    def test_persistent_profile_state(self):
        self.c.change('add', {'name': 'Test', 'uri': URI, 'revision': 1})
        other = Controller(self.root)
        self.assertEqual(other.profiles[0]['name'], 'Test')
        self.assertEqual(other.revision, 2)
        other.db.close()

    def test_ip_list_crud_and_routeros_selection(self):
        headers = self.auth()
        self.assertEqual(self.request('/api/ip-lists/add', {'name': 'No auth', 'addresses': ''})[0], 401)
        status, data, _ = self.request('/api/ip-lists/add', {'name': 'DNS', 'addresses': '\ufeff9.9.9.9\n9.9.9.9/32 # duplicate\n1.1.1.0/24'}, headers)
        self.assertEqual(status, 200)
        item = data['list']
        self.assertEqual(item['addresses'], ['1.1.1.0/24', '9.9.9.9'])
        status, result, _ = self.request('/api/routeros', {'list_id': item['id'], 'destinations': '8.8.8.8'}, headers)
        self.assertEqual(status, 200)
        self.assertIn('address=9.9.9.9/32', result['script'])
        self.assertNotIn('address=8.8.8.8', result['script'])
        self.assertIn('list=XRAY-DEST-' + item['id'], result['script'])
        self.assertIn('comment="XRAY-GW-DNS"', result['script'])
        original_scope = 'XRAY-DEST-' + item['id']
        item.update(name='DNS updated', addresses='8.8.8.8')
        self.assertEqual(self.request('/api/ip-lists/edit', item, headers)[0], 200)
        _, renamed, _ = self.request('/api/routeros', {'list_id':item['id'], 'list_name':'forged'}, headers)
        self.assertIn(original_scope, renamed['script'])
        self.assertIn('comment="XRAY-GW-DNS updated"', renamed['script'])
        self.assertNotIn('forged', renamed['script'])
        self.assertEqual(self.request('/api/ip-lists/edit', item, headers)[0], 400)
        from router_service import RouterService
        import time
        service=RouterService(self.c);service.public_config=lambda:{'configured':True};service.import_script=lambda script,log:None;self.c.router_service=service
        status,job,_=self.request('/api/ip-lists/delete', {'id': item['id'], 'version': 2}, headers)
        self.assertEqual(status,202)
        until=time.monotonic()+2
        while time.monotonic()<until and self.c.ip_lists():time.sleep(.01)
        self.assertEqual(service.job(job['id'],{'id':'test','role':'admin'})['status'],'done')
        self.assertEqual(self.request('/api/routeros', {'list_id': item['id']}, headers)[0], 400)

    def test_routeros_lists_have_disjoint_cleanup_and_allow_shared_ip(self):
        scripts = [routeros({'list_key': key, 'list_name': name}, ['1.1.1.1'])
                   for key, name in [('list_111111111111', 'First'), ('list_222222222222', 'Second')]]
        for own, other, script in [('111111111111', '222222222222', scripts[0]),
                                   ('222222222222', '111111111111', scripts[1])]:
            self.assertIn(f'list=XRAY-DEST-list_{own} address=1.1.1.1/32', script)
            self.assertNotIn(other, script)
            for line in script.splitlines():
                if ' remove ' in line:
                    self.assertIn('list_' + own, line)
            self.assertIn(f'/tool netwatch enable [find comment=XRAY-GW-WATCH-list_{own}]', script.splitlines())
            self.assertNotIn('/ip firewall address-list remove [find comment=XRAY-GW]', script)

    def test_routeros_display_names_cannot_inject_commands(self):
        script = routeros({'list_key':'list_111111111111', 'list_name':'Name"; $bad \\ path\nline'}, ['1.1.1.1'])
        line = next(line for line in script.splitlines() if 'list=XRAY-DEST-' in line and ' add ' in line)
        self.assertIn(r'comment="XRAY-GW-Name\"; \$bad \\ path line"', line)
        for bad in ('a; /quit', 'a"', '$bad', '../list'):
            with self.assertRaises(ValueError):
                routeros({'list_key':bad}, ['1.1.1.1'])

    def test_ip_list_validation_and_persistence(self):
        for raw in ('bad-ip', '2001:db8::gg', 'fe80::1%eth0', '2001:db8::/129', '1.1.1.1; /quit'):
            with self.assertRaises(ValueError):
                self.c.change_ip_list('add', {'name': 'Invalid', 'addresses': raw})
        item = self.c.change_ip_list('add', {'name': 'Saved', 'addresses': '1.1.1.1'})
        with self.assertRaises(ValueError):
            self.c.change_ip_list('add', {'name': 'saved', 'addresses': ''})
        other = Controller(self.root)
        self.assertTrue(any(row['id'] == item['id'] for row in other.ip_lists()))
        other.db.close()
        self.assertEqual(self.request('/api/routeros', {}, self.auth())[0], 400)

    def test_mixed_ip_lists_normalize_deduplicate_and_persist(self):
        headers = self.auth()
        status, result, _ = self.request('/api/ip-lists/add', {'name':'Mixed', 'addresses':
            '\ufeff2606:4700:4700:0000:0000:0000:0000:1111/128\n1.1.1.1/32\n'
            '2606:4700:4700::1111 # duplicate\n2001:db8:abcd:1234::42/64'}, headers)
        self.assertEqual(status, 200)
        item = result['list']
        self.assertEqual(item['addresses'], ['1.1.1.1', '2001:db8:abcd:1234::/64', '2606:4700:4700::1111'])
        other = Controller(self.root)
        try:
            self.assertIn(item, other.ip_lists())
        finally:
            other.db.close()
        item.update(addresses='1.1.1.1\n2606:4700:4700::1111\n2001:4860:4860::8844')
        self.assertEqual(self.request('/api/ip-lists/edit', item, headers)[0], 200)
        status, generated, _ = self.request('/api/routeros', {'list_id':item['id']}, headers)
        self.assertEqual(status, 200)
        key = item['id']
        self.assertIn(f'/ip firewall address-list add list=XRAY-DEST-{key} address=1.1.1.1/32', generated['script'])
        self.assertIn(f'/ipv6 firewall address-list add list=XRAY-DEST-{key} address=2606:4700:4700::1111/128', generated['script'])
        self.assertEqual(len(generated['warnings']), 1)
        self.assertIn('Маршрутизация IPv6 через VPN не настроена', generated['warnings'][0])

    def test_ipv6_only_and_switching_families_clear_only_own_entries(self):
        warnings = []
        script = routeros({'list_key':'list_111111111111'}, ['2606:4700:4700::1111'], warnings=warnings)
        self.assertIn('/ipv6 firewall address-list add', script)
        self.assertNotIn('/ip route add', script)
        self.assertNotIn('/tool netwatch add', script)
        self.assertTrue(warnings)
        v4 = routeros({'list_key':'list_111111111111'}, ['1.1.1.1'])
        self.assertIn('/ipv6 firewall address-list remove [find list=XRAY-DEST-list_111111111111]', v4)
        self.assertNotIn('/ipv6 firewall address-list add', v4)
        for line in script.splitlines():
            if ' remove ' in line:
                self.assertIn('list_111111111111', line)

    def test_initial_inventory_can_include_ipv6(self):
        lists = self.c.ip_lists(['1.1.1.1', '2606:4700:4700::1111/128', '10.0.0.1', 'fd00::1'])
        self.assertEqual(lists[0]['addresses'], ['1.1.1.1', '2606:4700:4700::1111'])

    def test_empty_ip_list_not_replaced_by_inventory(self):
        headers = self.auth()
        _, result, _ = self.request('/api/ip-lists/add', {'name': 'Empty', 'addresses': ''}, headers)
        self.assertEqual(self.request('/api/routeros', {'list_id': result['list']['id']}, headers)[0], 400)
        self.c.change_ip_list('delete', {'id': 'project', 'version': 1})
        self.c.change_ip_list('delete', {'id': result['list']['id'], 'version': 1})
        self.assertEqual(self.c.ip_lists(['1.1.1.1']), [])


if __name__ == '__main__':
    unittest.main()

import base64
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch

import test_panel
from accounts import Accounts
from secure_store import SecretStore
from two_factor import totp
from router_service import RouterService,PinnedKey,TerminalIntro,cleanup_script,fingerprint


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.panel=test_panel.PanelTest();self.panel.setUp();self.addCleanup(self.panel.tearDown)
        self.request=self.panel.request;self.c=self.panel.c;self.root=self.panel.root;self.headers=self.panel.auth()
        self.actor=self.request('/api/state',headers=self.headers)[1]['user']

    def wait_job(self,job):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            status,data,_=self.request('/api/routeros/jobs/'+job['id'],headers=self.headers)
            self.assertEqual(status,200)
            if data['status'] in ('done','error'):return data
            time.sleep(.01)
        self.fail('Operation did not complete')

    def test_factor_login_replay_recovery_and_disable(self):
        second=self.panel.auth()
        status,setup,_=self.request('/api/account/2fa/setup',{'password':'test-password'},self.headers)
        self.assertEqual(status,200);self.assertNotIn(setup['secret'],(self.root/'auth.json').read_text())
        self.assertEqual(self.request('/api/account/2fa/qr',headers=self.headers)[1][:8],b'\x89PNG\r\n\x1a\n')
        step=int(time.time()//30);code=totp(setup['secret'],step)
        status,result,_=self.request('/api/account/2fa/enable',{'code':code},self.headers)
        self.assertEqual(status,200);codes=result['recovery_codes'];self.assertEqual(len(codes),10)
        self.assertTrue(result['user']['two_factor_enabled'])
        self.assertEqual(self.request('/api/state',headers=second)[0],401)
        self.request('/api/logout',{},self.headers)
        status,login,cookie=self.request('/api/login',{'username':'admin','password':'test-password'})
        self.assertEqual(status,200);self.assertTrue(login['requires_2fa']);self.assertIsNone(cookie)
        self.assertEqual(self.request('/api/state')[0],401)
        self.assertEqual(self.request('/api/login/2fa',{'challenge':login['challenge'],'code':code})[0],401)
        status,_,cookie=self.request('/api/login/2fa',{'challenge':login['challenge'],'code':codes[0]})
        self.assertEqual(status,200)
        new={'Cookie':cookie.split(';')[0]};state=self.request('/api/state',headers=new)[1];new['X-CSRF-Token']=state['csrf']
        self.assertEqual(state['user']['recovery_remaining'],9)
        self.assertNotIn(codes[0],(self.root/'auth.json').read_text())
        self.assertEqual(self.request('/api/account/2fa/disable',{'password':'test-password','code':codes[0]},new)[0],400)
        status,result,_=self.request('/api/account/2fa/disable',{'password':'test-password','code':codes[1]},new)
        self.assertEqual(status,200);self.assertFalse(result['user']['two_factor_enabled'])
        self.assertEqual(self.request('/api/login',{'username':'admin','password':'test-password'})[0],200)

    def test_factor_challenge_attempt_limit(self):
        _,setup,_=self.request('/api/account/2fa/setup',{'password':'test-password'},self.headers)
        code=totp(setup['secret'],int(time.time()//30))
        _,result,_=self.request('/api/account/2fa/enable',{'code':code},self.headers)
        _,login,_=self.request('/api/login',{'username':'admin','password':'test-password'})
        for _ in range(5):self.assertEqual(self.request('/api/login/2fa',{'challenge':login['challenge'],'code':'wrong'})[0],401)
        self.assertEqual(self.request('/api/login/2fa',{'challenge':login['challenge'],'code':result['recovery_codes'][0]})[0],401)

    def test_account_preferences_avatar_and_authorization(self):
        data={'display_name':'Operator name','preferences':{'design':'console','language':'en','colorScheme':'dark'}}
        status,result,_=self.request('/api/account/profile',data,self.headers)
        self.assertEqual(status,200);self.assertEqual(result['user']['preferences'],data['preferences'])
        self.assertEqual(result['user']['revision'],self.actor['revision'])
        self.assertEqual(self.request('/api/account/profile',{'preferences':{'role':'admin'}},self.headers)[0],400)
        from PIL import Image
        image=Image.new('RGB',(30,80),'#456789');output=io.BytesIO();exif=Image.Exif();exif[270]='private metadata';image.save(output,format='JPEG',exif=exif)
        status,result,_=self.request('/api/account/avatar',{'image':base64.b64encode(output.getvalue()).decode()},self.headers)
        self.assertEqual(status,200)
        avatar=result['user']['avatar'];self.assertEqual(self.request(avatar)[0],401)
        status,content,_=self.request(avatar,headers=self.headers);self.assertEqual(status,200)
        with Image.open(io.BytesIO(content)) as saved:
            self.assertEqual(saved.size,(256,256));self.assertEqual(saved.format,'PNG');self.assertFalse(saved.getexif())
        self.assertNotIn(b'private metadata',content)
        self.assertEqual(self.request('/api/account/avatar',{'image':base64.b64encode(b'<svg/>').decode()},self.headers)[0],400)
        self.assertEqual(self.request('/api/account/avatar',{'image':''},self.headers)[1]['user']['avatar'],'')

    def test_router_job_cleanup_before_panel_delete_and_failure_retention(self):
        service=RouterService(self.c);self.c.router_service=service
        service.public_config=lambda:{'configured':True}
        before={item['id'] for item in self.c.ip_lists(self.panel.handler.defaults)}
        _,result,_=self.request('/api/ip-lists/add',{'name':'DNS','addresses':'1.1.1.1'},self.headers);item=result['list']
        service.import_script=Mock(side_effect=ValueError('Настройте подключение к RouterOS.'))
        status,job,_=self.request('/api/ip-lists/delete',item,self.headers);self.assertEqual(status,202)
        self.assertEqual(self.wait_job(job)['status'],'error');self.assertIn(item['id'],{v['id'] for v in self.c.ip_lists()})
        service.import_script=Mock()
        _,job,_=self.request('/api/ip-lists/delete',item,self.headers)
        self.assertEqual(self.wait_job(job)['status'],'done');self.assertEqual({v['id'] for v in self.c.ip_lists()},before)
        script=service.import_script.call_args.args[0]
        self.assertIn('/routing table remove [find name=xray-gateway-'+item['id']+']',script)
        self.assertNotIn('XRAY-DEST-other',script)

    def test_router_list_edits_are_locked_during_import(self):
        service=RouterService(self.c);self.c.router_service=service;service.public_config=lambda:{'configured':True}
        gate=threading.Event();self.addCleanup(gate.set)
        service.import_script=lambda script,log:gate.wait(2)
        _,result,_=self.request('/api/ip-lists/add',{'name':'DNS','addresses':'1.1.1.1'},self.headers);item=result['list']
        _,job,_=self.request('/api/routeros/apply',item,self.headers)
        self.assertEqual(self.request('/api/ip-lists/edit',item|{'addresses':'8.8.8.8'},self.headers)[0],400)
        other={'id':'other','role':'operator'}
        with self.assertRaises(ValueError):service.job(job['id'],other)
        gate.set();self.assertEqual(self.wait_job(job)['status'],'done')

    def test_router_terminal_and_configuration_are_admin_only(self):
        _,_,_=self.request('/api/users/add',{'username':'operator','password':'operator-pass','role':'operator'},self.headers)
        operator=self.panel.auth('operator','operator-pass')
        for path in ['/api/routeros/config','/api/routeros/terminal/open','/api/routeros/host-key']:
            self.assertEqual(self.request(path,{},operator)[0],403,path)
        self.assertEqual(self.request('/api/routeros/config',headers=operator)[0],403)

    def test_terminal_open_closes_connection_if_panel_session_was_revoked(self):
        service=RouterService(self.c);self.c.router_service=service
        def open_terminal(*args):self.panel.handler.sessions.clear();return {'id':'late-terminal'}
        service.open_terminal=Mock(side_effect=open_terminal);service.close_terminal=Mock()
        self.assertEqual(self.request('/api/routeros/terminal/open',{},self.headers)[0],401)
        service.close_terminal.assert_called_once_with('late-terminal')

    def test_legacy_project_list_supports_managed_deletion(self):
        service=RouterService(self.c);self.c.router_service=service;service.public_config=lambda:{'configured':True}
        service.import_script=Mock()
        item=next(v for v in self.c.ip_lists(self.panel.handler.defaults) if v['id']=='project')
        status,job,_=self.request('/api/ip-lists/delete',item,self.headers);self.assertEqual(status,202)
        self.assertEqual(self.wait_job(job)['status'],'done')
        self.assertEqual(self.c.ip_lists(),[])
        self.assertIn('XRAY-GW-WATCH-project',service.import_script.call_args.args[0])

    def test_factor_management_attempts_are_limited(self):
        for _ in range(5):self.assertEqual(self.request('/api/account/2fa/setup',{'password':'wrong'},self.headers)[0],400)
        self.assertEqual(self.request('/api/account/2fa/setup',{'password':'test-password'},self.headers)[0],429)

    def test_saved_router_credentials_are_marked_and_preserved_without_exposure(self):
        service=RouterService(self.c);self.c.router_service=service
        service.connect=Mock(return_value=Mock());service.execute=Mock(return_value='name: router')
        data={'host':'router.example','port':22,'username':'panel','auth':'key','fingerprint':'SHA256:'+'a'*43,
              'private_key':'private-key-fixture','passphrase':'passphrase-fixture'}
        status,public,_=self.request('/api/routeros/config',data,self.headers)
        self.assertEqual(status,200);self.assertTrue(public['configured']);self.assertTrue(public['passphrase_set'])
        self.assertEqual(self.request('/api/routeros/config',headers=self.headers)[1],public)
        for key in ('private_key','password','passphrase','secret'):self.assertNotIn(key,public)
        saved=json.loads(service.path.read_text());self.assertNotIn('private-key-fixture',service.path.read_text())
        self.assertEqual(self.request('/api/routeros/config',data|{'private_key':'','passphrase':''},self.headers)[0],200)
        self.assertEqual(json.loads(service.path.read_text())['secret'],saved['secret'])
        self.assertEqual(self.request('/api/routeros/config',data|{'private_key':''},self.headers)[0],400)
        status,public,_=self.request('/api/routeros/config',data|{'auth':'password','password':'ssh-password-fixture'},self.headers)
        self.assertEqual(status,200);self.assertTrue(public['configured']);self.assertFalse(public['passphrase_set'])
        self.assertNotIn('ssh-password-fixture',json.dumps(public))


class SecurityUnitTests(unittest.TestCase):
    def test_terminal_intro_strips_startup_screen_and_preserves_banner_and_queries(self):
        prefix=b'\r\x1b[9999B\r\x1b[9999B\x1bZ  \x1b[6n'+b'\r\n'*24+b'\n'
        banner=b'  MMM      MMM\r\n  MikroTik RouterOS\r\n\r\n[user@router] > '
        for size in (1,2,7,10000):
            intro=TerminalIntro();raw=prefix+banner
            actual=b''.join(intro.feed(raw[i:i+size]) for i in range(0,len(raw),size))
            self.assertEqual(actual,b'\x1b[9999B\x1b[9999B\x1bZ  \x1b[6n\x1b[H'+banner)
            later=b'\r\n\r\n\x1b[9999B\x1b[2Jcommand output\r\n'
            self.assertEqual(intro.feed(later),later)

    def test_terminal_intro_forwards_queries_before_banner_and_keeps_color_and_indent(self):
        intro=TerminalIntro()
        self.assertEqual(intro.feed(b'\x1bZ\x1b[6n'),b'\x1bZ\x1b[6n')
        self.assertEqual(intro.feed(b'\r\n\r\n\x1b[32'),b'')
        self.assertEqual(intro.feed(b'm  Banner\x1b[0m'),b'\x1b[32m  Banner\x1b[0m')

    def test_rfc6238_vectors(self):
        secret=base64.b32encode(b'12345678901234567890').decode()
        for timestamp,expected in [(59,'94287082'),(1111111109,'07081804'),(1111111111,'14050471'),(1234567890,'89005924'),(2000000000,'69279037')]:
            self.assertEqual(totp(secret,timestamp//30,digits=8),expected)

    def test_encryption_context_and_owned_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            store=SecretStore(Path(directory));token=store.seal('private-password','purpose-a')
            self.assertNotIn('private-password',token);self.assertEqual(store.open(token,'purpose-a'),'private-password')
            with self.assertRaises(RuntimeError):store.open(token,'purpose-b')
        key='list_123456abcdef';script=cleanup_script(key)
        self.assertIn('XRAY-GW-WATCH-'+key,script);self.assertIn('/ipv6 firewall address-list remove',script)
        self.assertNotIn('XRAY-DEST list',script)
        with self.assertRaises(ValueError):cleanup_script('evil; /user remove')

    def test_host_key_pinning(self):
        key=Mock();key.asbytes.return_value=b'host key'
        PinnedKey(fingerprint(key)).missing_host_key(None,'router',key)
        with self.assertRaises(ValueError):PinnedKey('SHA256:'+'x'*43).missing_host_key(None,'router',key)

    def test_terminal_is_bound_to_user_and_session(self):
        class Channel:
            closed=False
            def settimeout(self,value):pass
            def recv_ready(self):return False
            def sendall(self,value):self.sent=value
            def resize_pty(self,**values):self.size=values
            def close(self):self.closed=True
        with tempfile.TemporaryDirectory() as directory:
            controller=Mock();controller.directory=Path(directory);controller.settings.return_value={'source':'192.168.50.0/24'}
            service=RouterService(controller);client=Mock();channel=Channel();client.invoke_shell.return_value=channel;service.connect=lambda:client
            actor={'id':'a','role':'admin'};identifier=service.open_terminal(actor,'session-a')['id']
            for user,session in [({'id':'b'},'session-a'),(actor,'session-b')]:
                with self.assertRaises(ValueError):service.terminal(identifier,user,session)
            service.write_terminal(identifier,actor,'session-a','\x03/system identity print\r')
            self.assertEqual(channel.sent,b'\x03/system identity print\r')
            service.resize_terminal(identifier,actor,'session-a',120,40);self.assertEqual(channel.size,{'width':120,'height':40})
            service.logout('session-a');self.assertTrue(channel.closed)

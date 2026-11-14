import http.client,json,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
import test_panel
from updates import Updates
from update_protocol import validate_request,GATEWAY_IMAGE,UPDATER_IMAGE
import session_store


class PageTests(unittest.TestCase):
    def setUp(self):
        self.panel=test_panel.PanelTest();self.panel.setUp();self.addCleanup(self.panel.tearDown)
        self.c=self.panel.c;self.headers=self.panel.auth()

    def get(self,path,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.panel.server.server_port)
        connection.request('GET',path,headers=headers or {})
        response=connection.getresponse();status=response.status;body=response.read().decode();result=dict(response.getheaders());connection.close();return status,body,result

    def test_documents_do_not_contain_login_or_unrelated_pages(self):
        names=['overview','profiles','iplists','routeros','settings','account','wiki']
        for name in names:
            with self.subTest(page=name):
                status,body,_=self.get('/'+name,self.headers);self.assertEqual(status,200)
                self.assertIn('id="'+name+'Page"',body);self.assertNotIn('id="loginForm"',body)
                for other in names:
                    if other!=name:self.assertNotIn('id="'+other+'Page"',body)
                self.assertIn('id="pageState"',body)

    def test_login_redirect_and_safe_return_paths(self):
        status,body,headers=self.get('/profiles');self.assertEqual(status,303);self.assertEqual(headers['Location'],'/login?next=%2Fprofiles')
        status,body,_=self.get('/login');self.assertEqual(status,200);self.assertIn('id="loginForm"',body);self.assertNotIn('id="appView"',body)
        self.assertNotIn('/app.js',body);self.assertIn('/login.js',body)
        self.assertEqual(self.get('/login?next=%2Fprofiles',self.headers)[2]['Location'],'/profiles')
        self.assertEqual(self.get('/login?next=https%3A%2F%2Fevil.test',self.headers)[2]['Location'],'/overview')
        self.assertEqual(self.get('/login?next=%2Fsettings%23updates',self.headers)[2]['Location'],'/settings#updates')

    def test_all_wiki_sections_are_separate_documents(self):
        for topic in ['start','authentication','profiles','ip-lists','routeros','terminal','accounts','settings','updates']:
            status,body,_=self.get('/wiki/'+topic,self.headers);self.assertEqual(status,200);self.assertNotIn('{{WIKI_CONTENT}}',body)
            self.assertIn('class="wiki-article"',body);self.assertIn('aria-current="page" href="'+('/wiki' if topic=='start' else '/wiki/'+topic)+'"',body)
        self.assertEqual(self.get('/wiki/../../auth.json',self.headers)[0],404)

    def test_reader_cannot_open_administrator_documents(self):
        from accounts import Accounts
        accounts=Accounts(self.c.directory/'auth.json',self.c.lock);admin=accounts.authenticate('admin','test-password')
        accounts.change('add',{'username':'reader','password':'reader-password','role':'operator'},admin)
        headers=self.panel.auth('reader','reader-password')
        self.assertEqual(self.get('/routeros',headers)[2]['Location'],'/overview')
        self.assertEqual(self.get('/settings',headers)[2]['Location'],'/account')
        self.assertEqual(self.get('/wiki/profiles',headers)[0],200)
        self.assertEqual(self.panel.request('/api/updates/install',{'tag':'1.9.0-abcdef0'},headers)[0],403)
        self.assertEqual(self.panel.request('/api/updates/check',{},headers)[0],403)
        status,data,_=self.panel.request('/api/updates',headers=headers);self.assertEqual(status,200);self.assertIsNone(data['settings'])

    def test_sessions_survive_restart_encrypted_without_subscription_urls(self):
        raw=(self.c.directory/'sessions.enc.json').read_text();token=self.headers['Cookie'].split('=',1)[1]
        self.assertNotIn(token,raw);self.assertNotIn('csrf',raw)
        self.panel.handler.sessions=session_store.load(self.c)
        self.assertEqual(self.get('/profiles',self.headers)[0],200)
        self.panel.request('/api/logout',{},self.headers)
        self.panel.handler.sessions=session_store.load(self.c)
        self.assertEqual(self.get('/profiles',self.headers)[0],303)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.panel=test_panel.PanelTest();self.panel.setUp();self.addCleanup(self.panel.tearDown)
        self.c=self.panel.c;self.control=self.c.directory/'control';self.control.mkdir()
        self.updates=Updates(self.c,self.control,{'version':'1.8.2-aaaaaaa','base_version':'1.8.2'})
        self.c.updates=self.updates;self.headers=self.panel.auth()
        self.tag='1.9.0-bbbbbbb';self.revision='b'*40

    def candidate(self):
        return {'tag':self.tag,'version':'1.9.0','revision':self.revision,'url':'https://github.com/QueenDekim/XRay-gateway/tree/'+self.tag,
            'gateway_image':GATEWAY_IMAGE+'@sha256:'+'a'*64,'updater_image':UPDATER_IMAGE+'@sha256:'+'b'*64}

    def test_check_selects_published_semantic_version_and_releases_controller_lock(self):
        def metadata(url,headers=None):
            acquired=threading.Event()
            def reader():
                with self.c.lock:acquired.set()
            thread=threading.Thread(target=reader);thread.start();self.assertTrue(acquired.wait(1));thread.join()
            return [{'name':'1.10.0-ccccccc','commit':{'sha':'c'*40}},{'name':self.tag,'commit':{'sha':self.revision}},{'name':'invalid','commit':{'sha':'d'*40}}],{}
        def digest(repository,tag):
            if tag.startswith('1.10.0'):raise OSError('Not published yet')
            return repository+'@sha256:'+'a'*64
        with patch('updates.get_json',side_effect=metadata),patch('updates.registry_digest',side_effect=digest):result=self.updates.check()
        self.assertEqual(result['available']['tag'],self.tag);self.assertFalse(result['checking'])
        self.assertNotIn('gateway_image',result['available'])

    def test_network_failure_preserves_available_release_and_reports_error(self):
        self.updates.cache['available']=self.candidate()
        with patch('updates.get_json',side_effect=OSError('failure')):result=self.updates.check()
        self.assertEqual(result['available']['tag'],self.tag);self.assertTrue(result['error']);self.assertFalse(result['checking'])

    def test_install_requires_agent_exact_candidate_and_single_active_job(self):
        from update_protocol import write_json
        self.updates.cache['available']=self.candidate()
        with self.assertRaises(ValueError):self.updates.install(self.tag)
        write_json(self.control/'agent.json',{'heartbeat':time.time(),'protocol':1})
        with self.assertRaises(ValueError):self.updates.install('1.10.0-ccccccc')
        result=self.updates.install(self.tag);request=json.loads((self.control/'request.json').read_text());validate_request(request)
        self.assertEqual(result['id'],request['id']);self.assertEqual(request['gateway_image'],self.candidate()['gateway_image'])
        with self.assertRaises(ValueError):self.updates.install(self.tag)
        request['gateway_image']='alpine:latest'
        with self.assertRaises(ValueError):validate_request(request)

    def test_maintenance_blocks_mutations_but_allows_status_and_pages(self):
        from update_protocol import write_json
        write_json(self.control/'job.json',{'id':'1'*32,'status':'installing','tag':self.tag})
        for path,data in [('/api/profiles/add',{}),('/api/login',{'username':'admin','password':'test-password'}),('/api/logout',{})]:
            self.assertEqual(self.panel.request(path,data,self.headers)[0],503)
        self.assertEqual(self.panel.request('/api/state',headers=self.headers)[0],200)
        self.assertEqual(self.panel.request('/api/updates',headers=self.headers)[0],200)

    def test_invalid_settings_and_cached_current_release(self):
        for data in [{'auto_install':'yes'},{'auto_install':True,'check_interval_hours':0},{'auto_install':True,'check_interval_hours':True}]:
            with self.assertRaises(ValueError):self.updates.save_settings(data)
        self.updates.save_settings({'auto_install':True,'check_interval_hours':12})
        self.assertEqual(self.updates.settings(),{'auto_install':True,'check_interval_hours':12})
        self.updates.cache['available']=self.candidate();self.updates.current_number=(1,9,0)
        self.assertIsNone(self.updates.snapshot()['available'])

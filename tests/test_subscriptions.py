"""Subscription selection must import the reviewed nodes as one configuration."""
import base64
import json
import unittest
from unittest.mock import patch
import test_panel
from controller import profile_sources

URI=test_panel.URI
FIRST=URI+'#First%20node'
SECOND=URI.replace('example.org:443','second.example.org:8443').replace('type=tcp','type=xhttp').replace('security=reality','security=tls')+'#Second%20node'
URL='https://example.org/sub/private-token'


class SubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.panel=test_panel.PanelTest();self.panel.setUp();self.addCleanup(self.panel.tearDown)
        self.c=self.panel.c;self.headers=self.panel.auth()

    def request(self,path,data,headers=None):
        return self.panel.request(path,data,self.headers if headers is None else headers)

    def preview(self,payload=None):
        with patch('controller.fetch_subscription',return_value=payload or (FIRST+'\n'+SECOND).encode()):
            status,result,_=self.request('/api/profiles/preview',{'uri':URL})
        self.assertEqual(status,200);return result

    def selection(self,preview,selected=None):
        return {'name':'Selected','priority':7,'enabled':True,'revision':self.c.revision,'uri':URL,
                'subscription_token':preview['token'],
                'subscription_profiles':selected if selected is not None else [v['id'] for v in preview['profiles']]}

    def test_plain_base64_urlsafe_bom_duplicates_invalid_and_names(self):
        source=('\ufeff'+FIRST+'\r\n'+SECOND+'\n'+FIRST+'\n'+URI.replace('type=tcp','type=invalid')+'\n').encode()
        for body in [source,b'# subscription\n'+source,base64.b64encode(source),base64.urlsafe_b64encode(source).rstrip(b'=')]:
            with self.subTest(encoding=body[:4]):
                preview=self.preview(body)
                self.assertEqual([v['name'] for v in preview['profiles']],['First node','Second node'])
                self.assertEqual(preview['skipped'],1)
                self.assertEqual([v['transport'] for v in preview['profiles']],['tcp','xhttp'])
                text=json.dumps(preview)
                for secret in ['private-token','vless://','00000000-0000','pbk=','settings','users']:
                    self.assertNotIn(secret,text)
        with patch('controller.fetch_subscription',return_value=FIRST.upper().encode()):
            self.assertEqual(len(profile_sources(URL)[0]),1)

    def test_multi_add_is_atomic_and_does_not_refetch(self):
        preview=self.preview();data=self.selection(preview);data['name']=''
        with patch('controller.fetch_subscription',side_effect=AssertionError('must use preview')),patch.object(self.c,'restart') as restart,patch.object(self.c,'validate',wraps=self.c.validate) as validate:
            self.assertEqual(self.request('/api/profiles/add',data)[0],200)
        restart.assert_called_once();validate.assert_called_once()
        profiles=self.c.list_profiles()
        self.assertEqual([v['name'] for v in profiles],['First node','Second node'])
        self.assertEqual(len(set(v['id'] for v in profiles)),2)
        self.assertEqual([v['slot'] for v in profiles],[4,5])
        self.assertTrue(all(v['priority']==7 and v['enabled'] for v in profiles))
        self.assertEqual(self.c.revision,data['revision']+1)
        self.assertNotIn(URL,json.dumps(self.c.load('profiles',[])))
        self.assertEqual(self.request('/api/profiles/add',data|{'revision':self.c.revision})[0],400)

    def test_subset_and_edit_preserve_identity_slot_and_counters(self):
        preview=self.preview();data=self.selection(preview,[preview['profiles'][1]['id']])
        self.assertEqual(self.request('/api/profiles/add',data)[0],200)
        old=self.c.list_profiles()[0];self.c.stats={old['id']:{'downlink':42,'checks':5,'successful_checks':4}}
        preview=self.preview();data=self.selection(preview,[preview['profiles'][0]['id']]);data.update(id=old['id'],name='Keep name')
        self.assertEqual(self.request('/api/profiles/edit',data)[0],200)
        new=self.c.list_profiles()[0]
        self.assertEqual((new['id'],new['slot'],new['name']),(old['id'],old['slot'],'Keep name'))
        self.assertEqual(new['node']['streamSettings']['network'],'tcp')
        self.assertEqual(self.c.stats[old['id']],{'downlink':42,'checks':5,'successful_checks':4})
        preview=self.preview();data=self.selection(preview);data['id']=old['id']
        self.assertEqual(self.request('/api/profiles/edit',data)[0],400)
        self.assertEqual(self.c.list_profiles(),[new])

    def test_expired_wrong_session_or_changed_source_cannot_apply(self):
        preview=self.preview();data=self.selection(preview);other=self.panel.auth()
        self.assertEqual(self.request('/api/profiles/add',data,other)[0],400)
        self.assertEqual(self.request('/api/profiles/add',data|{'uri':URL+'/changed'})[0],400)
        for selected in [[],[{}],[preview['profiles'][0]['id']]*2,['missing']]:
            self.assertEqual(self.request('/api/profiles/add',data|{'subscription_profiles':selected})[0],400)
        with patch('panel.time.time',return_value=__import__('time').time()+301):
            self.assertEqual(self.request('/api/profiles/add',data)[0],400)
        self.assertEqual(self.c.list_profiles(),[])

    def test_replaced_preview_and_concurrent_revision_are_rejected(self):
        first=self.preview();second=self.preview()
        self.assertEqual(self.request('/api/profiles/add',self.selection(first))[0],400)
        data=self.selection(second);self.c.revision+=1
        self.assertEqual(self.request('/api/profiles/add',data)[0],400)
        self.assertEqual(self.c.list_profiles(),[])

    def test_failed_validation_or_capacity_imports_nothing(self):
        preview=self.preview();data=self.selection(preview);before=self.c.config.read_bytes()
        with patch.object(self.c,'validate',side_effect=ValueError('Invalid candidate')),patch.object(self.c,'restart') as restart:
            self.assertEqual(self.request('/api/profiles/add',data)[0],400)
        restart.assert_not_called();self.assertEqual(self.c.list_profiles(),[])
        self.assertEqual(self.c.config.read_bytes(),before)
        self.c.save('next_slot',100)
        self.assertEqual(self.request('/api/profiles/add',data)[0],400)
        self.assertEqual(self.c.list_profiles(),[])
        self.assertEqual(self.c.load('next_slot',None),100)

    def test_restart_failure_restores_config_without_partial_records(self):
        preview=self.preview();data=self.selection(preview);before=self.c.config.read_bytes();revision=self.c.revision
        with patch.object(self.c,'restart',side_effect=[RuntimeError('restart failed'),None]) as restart:
            self.assertEqual(self.request('/api/profiles/add',data)[0],503)
        self.assertEqual(restart.call_count,2);self.assertEqual(self.c.config.read_bytes(),before)
        self.assertEqual(self.c.list_profiles(),[]);self.assertEqual(self.c.load('profiles',[]),[])
        self.assertEqual(self.c.revision,revision);self.assertFalse(self.c.applying)

    def test_multinode_requires_selection_without_silent_first_choice(self):
        with patch('controller.fetch_subscription',return_value=(FIRST+'\n'+SECOND).encode()):
            status,result,_=self.request('/api/profiles/add',{'name':'New','priority':1,'enabled':True,'uri':URL,'revision':self.c.revision})
        self.assertEqual(status,400);self.assertIn('несколько профилей',result['error'])
        self.assertEqual(self.c.list_profiles(),[])

    def test_single_node_url_import_without_preview_still_has_group(self):
        with patch('controller.fetch_subscription',return_value=FIRST.encode()):
            status,_,_=self.request('/api/profiles/add',{'name':'Single','uri':URL,'priority':4,'enabled':True,'revision':self.c.revision})
        self.assertEqual(status,200)
        self.assertEqual(self.c.public_profiles()[0]['subscription']['name'],'example.org')
        self.assertNotIn(URL,json.dumps(self.c.load('profiles',[])))

    def test_custom_names_priorities_grouping_and_public_metadata(self):
        preview=self.preview();data=self.selection(preview);first,second=[p['id'] for p in preview['profiles']]
        data.update(name='',subscription_name='My group',subscription_options={first:{'name':'Renamed first','priority':45},second:{'name':'Renamed second','priority':2}})
        self.assertEqual(self.request('/api/profiles/add',data)[0],200)
        profiles=self.c.list_profiles()
        self.assertEqual([(p['name'],p['priority']) for p in profiles],[('Renamed second',2),('Renamed first',45)])
        groups=[p['subscription'] for p in profiles];self.assertEqual(groups[0]['id'],groups[1]['id'])
        self.assertTrue(all(p['name']=='My group' for p in groups))
        public=self.c.public_profiles();self.assertEqual(public[0]['subscription'],{'id':groups[0]['id'],'name':'My group'})
        self.assertNotIn('node_id',json.dumps(public));self.assertNotIn('private-token',json.dumps(public))
        reopened=type(self.c)(self.c.directory)
        try:self.assertEqual(reopened.public_profiles()[0]['subscription'],public[0]['subscription'])
        finally:reopened.db.close()

    def test_reimport_updates_group_members_preserving_ids_counters_and_slots(self):
        preview=self.preview();data=self.selection(preview)
        self.assertEqual(self.request('/api/profiles/add',data)[0],200)
        old={p['subscription']['node_id']:(p['id'],p['slot']) for p in self.c.list_profiles()}
        self.c.stats={identifier:{'downlink':42,'checks':5} for identifier,_ in old.values()}
        preview=self.preview();selected=preview['profiles'][0]['id'];data=self.selection(preview,[selected])
        data.update(subscription_name='Renamed group',subscription_options={selected:{'name':'New name','priority':99}})
        self.c.save('next_slot',101)
        with patch.object(self.c,'restart') as restart:self.assertEqual(self.request('/api/profiles/add',data)[0],200)
        restart.assert_called_once();profiles=self.c.list_profiles();self.assertEqual(len(profiles),2)
        self.assertEqual({p['subscription']['node_id']:(p['id'],p['slot']) for p in profiles},old)
        self.assertTrue(all(p['subscription']['name']=='Renamed group' for p in profiles))
        self.assertTrue(all(self.c.stats[p['id']]=={'downlink':42,'checks':5} for p in profiles))
        self.assertEqual(next(p for p in profiles if p['subscription']['node_id']==selected)['priority'],99)
        preview=self.preview();selected_public=next(p for p in preview['profiles'] if p['id']==selected)
        self.assertEqual((selected_public['name'],selected_public['priority']),('New name',99))
        self.assertEqual(preview['group']['name'],'Renamed group')

    def test_normal_edit_keeps_group_and_changes_only_own_priority(self):
        preview=self.preview();self.assertEqual(self.request('/api/profiles/add',self.selection(preview))[0],200)
        first,other=self.c.list_profiles();before=other.copy()
        data={'id':first['id'],'name':'Individual edit','priority':1,'enabled':True,'uri':'','revision':self.c.revision}
        self.assertEqual(self.request('/api/profiles/edit',data)[0],200)
        edited=self.c.list_profiles()[0];self.assertEqual(edited['subscription'],first['subscription'])
        self.assertEqual(edited['priority'],1);self.assertEqual(self.c.list_profiles()[1],before)

    def test_invalid_per_node_values_do_not_partially_import(self):
        preview=self.preview();selected=preview['profiles'][0]['id'];data=self.selection(preview,[selected])
        bad=[{'name':'','priority':1},{'name':'x'*81,'priority':1},{'name':'  ','priority':1}]
        bad += [{'name':'Valid','priority':value} for value in [True,0,1001,1.5,'10',None]]
        for option in bad:
            with self.subTest(option=option):
                self.assertEqual(self.request('/api/profiles/add',data|{'subscription_options':{selected:option}})[0],400)
        for options in [[],{'not-selected':{'name':'Unknown','priority':1}}]:
            self.assertEqual(self.request('/api/profiles/add',data|{'subscription_options':options})[0],400)
        self.assertEqual(self.request('/api/profiles/add',data|{'subscription_name':''})[0],400)
        self.assertEqual(self.c.list_profiles(),[])

    def test_reimport_attaches_unique_older_profile_without_duplicate(self):
        self.c.change('add',{'name':'Older profile','priority':81,'enabled':True,'uri':FIRST,'revision':self.c.revision})
        original=self.c.list_profiles()[0];preview=self.preview();entry=preview['profiles'][0]
        self.assertEqual((entry['name'],entry['priority']),('Older profile',81))
        data=self.selection(preview,[entry['id']]);data['subscription_options']={entry['id']:{'name':entry['name'],'priority':entry['priority']}}
        self.assertEqual(self.request('/api/profiles/add',data)[0],200)
        profiles=self.c.list_profiles();self.assertEqual(len(profiles),1)
        self.assertEqual((profiles[0]['id'],profiles[0]['slot']),(original['id'],original['slot']))
        self.assertEqual(profiles[0]['subscription']['id'],preview['group']['id'])

    def test_other_subscription_has_independent_group_even_for_same_nodes(self):
        preview=self.preview();self.assertEqual(self.request('/api/profiles/add',self.selection(preview))[0],200)
        with patch('controller.fetch_subscription',return_value=(FIRST+'\n'+SECOND).encode()):
            status,other,_=self.request('/api/profiles/preview',{'uri':URL+'-another'})
        self.assertEqual(status,200);self.assertNotEqual(preview['group']['id'],other['group']['id'])
        data=self.selection(other);data['uri']=URL+'-another'
        self.assertEqual(self.request('/api/profiles/add',data)[0],200)
        self.assertEqual(len(self.c.list_profiles()),4)
        self.assertEqual(len({p['subscription']['id'] for p in self.c.list_profiles()}),2)

    def test_preview_requires_admin_csrf_and_live_session_without_locking_readers(self):
        def fetch(*args,**kwargs):
            import threading
            event=threading.Event()
            def reader():
                with self.c.lock:event.set()
            thread=threading.Thread(target=reader);thread.start();self.assertTrue(event.wait(1));thread.join()
            self.panel.handler.sessions.clear()
            return FIRST.encode()
        with patch('controller.fetch_subscription',side_effect=fetch):
            self.assertEqual(self.request('/api/profiles/preview',{'uri':URL})[0],401)
        headers=self.panel.auth()
        with patch('controller.fetch_subscription') as fetch:
            self.assertEqual(self.request('/api/profiles/preview',{'uri':URL},headers|{'X-CSRF-Token':'wrong'})[0],403)
            fetch.assert_not_called()

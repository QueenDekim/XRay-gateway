import json
import sqlite3
import time
import unittest

import test_panel
from controller import Controller
from router_service import RouterService


class RouterHistoryTests(unittest.TestCase):
    def setUp(self):
        self.panel=test_panel.PanelTest();self.panel.setUp();self.addCleanup(self.panel.tearDown)
        self.c=self.panel.c;self.headers=self.panel.auth()
        self.actor=self.panel.request('/api/state',headers=self.headers)[1]['user']
        self.service=RouterService(self.c);self.c.router_service=self.service
        self.service.public_config=lambda:{'configured':True}
        self.service.import_script=lambda script,log:log('Imported test entries')

    def run_job(self):
        item=self.c.ip_lists(self.panel.handler.defaults)[0]
        job=self.service.start('apply',item['id'],item['version'],self.actor,self.panel.handler.defaults)
        until=time.monotonic()+15
        while time.monotonic()<until:
            result=self.service.job(job['id'],self.actor)
            if result['status'] in ('done','error'):return result
            time.sleep(.005)
        self.fail('RouterOS test job timed out')

    def reopen(self,directory=None):
        controller=Controller(directory or self.c.directory)
        self.addCleanup(controller.db.close)
        return RouterService(controller)

    def test_history_survives_logout_login_and_new_database_connection(self):
        completed=self.run_job();self.assertEqual(completed['status'],'done')
        self.panel.request('/auth/logout',{},self.headers)
        headers=self.panel.auth()
        status,history,_=self.panel.request('/api/routeros/jobs',headers=headers)
        self.assertEqual(status,200);self.assertEqual(history['jobs'][0],completed)
        restored=self.reopen()
        self.assertEqual(restored.job(completed['id'],self.actor),completed)
        self.assertEqual(restored.recent({'id':'other','role':'operator'}),[])
        with self.assertRaises(ValueError):restored.job(completed['id'],{'id':'other','role':'operator'})

    def test_trimmed_log_keeps_its_cursor_after_restart_and_backup(self):
        self.service.import_script=lambda script,log:[log('line '+str(index)) for index in range(605)]
        completed=self.run_job()
        self.assertEqual(len(completed['logs']),600)
        self.assertEqual(completed['logs'][0],'line 6')
        self.assertEqual(completed['cursor'],606)
        backup=self.c.directory/'copied-runtime';backup.mkdir()
        with sqlite3.connect(backup/'panel.sqlite') as target:self.c.db.backup(target)
        target.close()
        restored=self.reopen(backup)
        self.assertEqual(restored.job(completed['id'],self.actor),completed)
        self.assertEqual(restored.job(completed['id'],self.actor,600)['logs'],completed['logs'][-6:])

    def test_interrupted_jobs_become_persisted_errors_without_replaying_import(self):
        completed=self.run_job()
        with self.c.lock:
            record=json.loads(self.c.db.execute('SELECT value FROM router_jobs WHERE id=?',(completed['id'],)).fetchone()[0])
            record['status']='running'
            self.c.db.execute('UPDATE router_jobs SET value=? WHERE id=?',(json.dumps(record),completed['id']))
            self.c.db.commit()
        restored=self.reopen()
        restored.import_script=lambda *args:self.fail('Interrupted imports must not be replayed')
        restored.recover_jobs()
        recovered=restored.job(completed['id'],self.actor)
        self.assertEqual(recovered['status'],'error')
        self.assertIn('перезапуском',recovered['logs'][-1])
        again=self.reopen();again.recover_jobs()
        self.assertEqual(again.job(completed['id'],self.actor),recovered)
        self.assertEqual(again.busy,{})

    def test_retention_removes_old_log_rows_together_with_jobs(self):
        jobs=[self.run_job() for _ in range(32)]
        restored=self.reopen()
        self.assertEqual(len(restored.recent(self.actor)),30)
        with self.assertRaises(ValueError):restored.job(jobs[0]['id'],self.actor)
        with self.c.lock:
            orphaned=self.c.db.execute('SELECT COUNT(*) FROM router_job_logs WHERE job_id NOT IN (SELECT id FROM router_jobs)').fetchone()[0]
        self.assertEqual(orphaned,0)
        self.assertEqual(restored.recent(self.actor)[0]['id'],jobs[-1]['id'])

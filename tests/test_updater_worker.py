import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'updater'),str(ROOT/'gateway')]
import worker
from update_protocol import write_json


class WorkerTests(unittest.TestCase):
    def test_static_addresses_macs_and_aliases_are_kept_without_pinning_dynamic_ip(self):
        layout={'services':{'gateway':{'networks':{'lan':{'ipv4_address':'192.168.50.20'},'proxy':{}}}},'networks':{'lan':{'name':'lan'},'proxy':{'name':'proxy'}}}
        gateway={'NetworkSettings':{'Networks':{'lan':{'IPAddress':'192.168.50.20','MacAddress':'02:42:c0:a8:32:14','Aliases':['gateway']},'proxy':{'IPAddress':'172.20.0.4','MacAddress':'02:42:ac:14:00:04','Aliases':['gateway-panel']}}}}
        saved,override=worker.network_state(layout,gateway)
        self.assertEqual(saved['lan']['IPAddress'],'192.168.50.20');self.assertIsNone(saved['proxy']['IPAddress'])
        self.assertEqual(override['lan']['mac_address'],'02:42:c0:a8:32:14');self.assertEqual(override['proxy']['aliases'],['gateway-panel'])
        self.assertNotIn('ipv4_address',override['proxy'])

    def test_backup_and_restore_database_secrets_and_environment(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);data=root/'runtime';data.mkdir();control=root/'control';control.mkdir();project=root/'project';project.mkdir();backup=project/'.backups/update-test'
            with sqlite3.connect(data/'panel.sqlite') as db:db.execute('CREATE TABLE documents (key TEXT PRIMARY KEY,value TEXT)');db.execute('INSERT INTO documents VALUES (?,?)',('profiles','[]'))
            db.close()
            (data/'auth.json').write_text('{"users":[]}');(data/'.encryption-key').write_text('private-key');(data/'routeros.json').write_text('encrypted-router-data')
            env=project/'.env';env.write_text('GATEWAY_IMAGE=old\n')
            write_json(control/'job.json',{'id':'a'*32,'status':'installing','logs':[]})
            with patch.object(worker,'DATA',data),patch.object(worker,'CONTROL',control),patch.dict(os.environ,{'UPDATE_JOB_ID':'a'*32}):
                worker.backup(backup);before=worker.fingerprint()
                (data/'auth.json').write_text('changed');(data/'.encryption-key').write_text('changed');env.write_text('GATEWAY_IMAGE=new\n')
                calls=[]
                state={'directory':str(project),'project':'isolated-test','files':[], 'old_images':{'gateway':'old-gateway','xray':'old-core','updater':'old-updater'},'old_version':'1.8.2-aaaaaaa','environment':__import__('base64').b64encode(b'GATEWAY_IMAGE=old\n').decode(),'gateway_networks':{}}
                with patch.object(worker,'compose',side_effect=lambda *args:calls.append(args)),patch.object(worker,'verify'):
                    worker.rollback(state,backup)
                self.assertEqual(worker.fingerprint(),before);self.assertEqual((data/'.encryption-key').read_text(),'private-key')
                self.assertEqual(env.read_text(),'GATEWAY_IMAGE=old\n');self.assertEqual(json.loads((control/'job.json').read_text())['rolled_back'],True)
                self.assertEqual(calls[0][2],'stop');self.assertEqual(calls[-1][2],'up')

    def test_write_drain_requires_current_idle_panel(self):
        with tempfile.TemporaryDirectory() as directory:
            control=Path(directory)
            write_json(control/'panel.json',{'heartbeat':__import__('time').time(),'writes':0,'busy':False})
            with patch.object(worker,'CONTROL',control):worker.wait_for_writes(timeout=.1)
            write_json(control/'panel.json',{'heartbeat':__import__('time').time(),'writes':1,'busy':False})
            with patch.object(worker,'CONTROL',control),patch.object(worker.time,'sleep'):
                with self.assertRaises(RuntimeError):worker.wait_for_writes(timeout=.01)

    def test_compose_uses_explicit_files_and_project_not_shell_interpolation(self):
        state={'project':'test-project','directory':'/opt/test-project','files':['/opt/test-project/compose.yaml']}
        with patch.object(worker,'run',return_value='') as run:
            worker.compose(state,'/opt/test-project/.backups/update-x/images.override.json','up','-d','--no-build')
        args=run.call_args.args;self.assertEqual(args[:4],('docker','compose','--project-directory','/opt/test-project'))
        self.assertIn('/opt/test-project/.backups/update-x/images.override.json',args);self.assertNotIn('shell',run.call_args.kwargs)

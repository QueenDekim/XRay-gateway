"""Exercise real Compose replacement and rollback in an isolated test project."""
import argparse,json,os,shutil,sqlite3,subprocess,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def run(*args,check=True,**kwargs):
    result=subprocess.run(args,text=True,capture_output=True,**kwargs)
    if check and result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
    return result


def inspect(name):return json.loads(run('docker','inspect',name).stdout)[0]


def exercise(gateway_image,updater_image,fail):
    identifier=uuid.uuid4().hex;project='xray-update-test-'+identifier[:10]
    folder=(ROOT/'.secrets'/project).resolve();folder.mkdir(parents=True)
    assert folder.is_relative_to((ROOT/'.secrets').resolve())
    data=folder/'runtime';data.mkdir();control=folder/'control';control.mkdir();(control/'requests').mkdir()
    request={'protocol':1,'id':identifier,'created_at':time.time(),'gateway_image':'ghcr.io/queendekim/xray-gateway@sha256:'+'a'*64,'updater_image':'ghcr.io/queendekim/xray-gateway-updater@sha256:'+'b'*64}
    metadata=json.loads(run('docker','run','--rm','--network','none','--entrypoint','python3',gateway_image,'-c','from version import build_info; import json; print(json.dumps(build_info()))').stdout)
    request.update(tag=metadata['tag'],revision=metadata['revision'])
    assert metadata['base_version']!='1.8.2','Test needs a newer candidate image'
    with sqlite3.connect(data/'panel.sqlite') as db:
        db.execute('CREATE TABLE documents (key TEXT PRIMARY KEY,value TEXT)')
        for key,value in [('profiles','[{"id":"keep","priority":3}]'),('stats','{"keep":{"downlink":1234}}')]:db.execute('INSERT INTO documents VALUES (?,?)',(key,value))
    db.close();(data/'auth.json').write_text('{"users":[{"id":"keep-user"}]}');(data/'.encryption-key').write_text('keep-private-key');(data/'routeros.json').write_text('keep-encrypted-router')
    before={name:(data/name).read_bytes() for name in ['auth.json','.encryption-key','routeros.json']}
    (folder/'.env').write_text('GATEWAY_IMAGE=ghcr.io/queendekim/xray-gateway:1.8.2\n')
    stub=r"""import http.server,json,threading,time
from pathlib import Path
from version import build_info
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  info=build_info();broken=Path('/runtime-flags/fail').exists() and info['base_version']!='1.8.2'
  if broken:Path('/data/auth.json').write_text('damaged-test-data')
  body=json.dumps(info if self.path=='/api/version' else {'selected':'direct'}).encode()
  self.send_response(503 if broken and self.path=='/health' else 200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
def heartbeat():
 while True:
  path=Path('/run/xray-updates/panel.json');temp=path.with_suffix('.pulse');temp.write_text(json.dumps({'heartbeat':time.time(),'writes':0,'busy':False}));temp.replace(path);time.sleep(.5)
threading.Thread(target=heartbeat,daemon=True).start()
http.server.ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
"""
    (folder/'stub.py').write_text(stub)
    flags=folder/'flags';flags.mkdir()
    if fail:(flags/'fail').touch()
    wrapper=r"""import json,os
from pathlib import Path
import worker,engine
mapping=json.loads(os.environ['TEST_IMAGE_MAP']);original_run=worker.run;original_inspect=worker.inspect;original_config=worker.config;original_verify=worker.verify
# Only the registry adapter is replaced. Container replacement and rollback use real Docker/Compose.
def run(*args,**kwargs):
 if len(args)>2 and args[:2]==('docker','pull') and args[2] in mapping:return original_run('docker','image','inspect',mapping[args[2]],**kwargs)
 return original_run(*args,**kwargs)
worker.run=run
worker.inspect=lambda name:original_inspect(mapping.get(name,name))
worker.config=lambda path,images,state:original_config(path,{key:mapping.get(value,value) for key,value in images.items()},state)
worker.verify=lambda state,tag:original_verify(state,tag,timeout=20)
worker.main()
"""
    (folder/'wrapper.py').write_text(wrapper)
    compose={'services':{
      'gateway':{'image':'ghcr.io/queendekim/xray-gateway:1.8.2','entrypoint':['python3','/test/stub.py'],'environment':{'PYTHONPATH':'/app'},'volumes':[str(data)+':/data',str(control)+':/run/xray-updates',str(folder)+':/test:ro',str(flags)+':/runtime-flags:ro'],'networks':{'default':{'aliases':['preserved-alias']}},'healthcheck':{'test':['CMD','python3','-c','import urllib.request; urllib.request.urlopen("http://127.0.0.1:8080/health",timeout=2)'],'interval':'1s','timeout':'3s','retries':1}},
      'xray':{'image':updater_image,'entrypoint':['python3','-c'],'command':['import time; time.sleep(3600)'],'network_mode':'service:gateway','pid':'service:gateway','depends_on':['gateway']},
      'updater':{'image':updater_image,'entrypoint':['python3','-c'],'command':['import time; time.sleep(3600)']}}}
    config=folder/'compose.json';config.write_text(json.dumps(compose,indent=2))
    command=['docker','compose','--project-directory',str(folder),'-p',project,'-f',str(config)]
    worker_name='xray-gw-update-'+identifier;success=False
    try:
        run(*command,'up','-d',timeout=120)
        old_gateway=inspect(run(*command,'ps','-q','gateway').stdout.strip())
        (control/'job.json').write_text(json.dumps({'id':identifier,'tag':request['tag'],'status':'queued','logs':[]}))
        (control/'requests'/(identifier+'.json')).write_text(json.dumps(request))
        mapping={request['gateway_image']:gateway_image,request['updater_image']:updater_image,'ghcr.io/xtls/xray-core:26.10.21':updater_image}
        run('docker','run','-d','--name',worker_name,'--network','none','--cap-drop','ALL','--cap-add','DAC_OVERRIDE','--cap-add','CHOWN','--cap-add','FOWNER','--read-only','--security-opt','no-new-privileges:true','--tmpfs','/tmp',
            '--mount','type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock','--mount','type=bind,src='+str(folder)+',dst='+str(folder),
            '--mount','type=bind,src='+str(data)+',dst=/runtime','--mount','type=bind,src='+str(control)+',dst=/control',
            '-e','PYTHONPATH=/app','-e','UPDATE_PROJECT='+project,'-e','UPDATE_DIRECTORY='+str(folder),'-e','UPDATE_FILES='+json.dumps([str(config)]),'-e','UPDATE_JOB_ID='+identifier,
            '-e','TEST_IMAGE_MAP='+json.dumps(mapping),'--entrypoint','python3',updater_image,str(folder/'wrapper.py'))
        deadline=time.monotonic()+150
        while time.monotonic()<deadline:
            result=inspect(worker_name)
            if not result['State']['Running']:break
            time.sleep(1)
        else:raise RuntimeError('Test worker timed out')
        if result['State']['ExitCode']!=0:raise RuntimeError(run('docker','logs',worker_name).stdout+'\n'+run('docker','logs',worker_name).stderr)
        job=json.loads(run('docker','run','--rm','--network','none','--mount','type=bind,src='+str(control)+',dst=/control,readonly','--entrypoint','python3',updater_image,'-c',"print(open('/control/job.json').read())").stdout)
        assert job['status']==('error' if fail else 'done'),job
        if fail:assert job['rolled_back'] is True
        gateway=inspect(run(*command,'ps','-q','gateway').stdout.strip())
        info=json.loads(run('docker','exec',gateway['Id'],'python3','-c','from version import build_info; import json; print(json.dumps(build_info()))').stdout)
        assert info['base_version']==('1.8.2' if fail else metadata['base_version'])
        for key,value in before.items():assert (data/key).read_bytes()==value,key
        with sqlite3.connect(data/'panel.sqlite') as db:assert dict(db.execute('SELECT key,value FROM documents'))=={'profiles':'[{"id":"keep","priority":3}]','stats':'{"keep":{"downlink":1234}}'}
        db.close()
        old_net=next(iter(old_gateway['NetworkSettings']['Networks'].values()));new_net=next(iter(gateway['NetworkSettings']['Networks'].values()))
        assert old_net['MacAddress']==new_net['MacAddress'];assert 'preserved-alias' in new_net['Aliases']
        success=True;print(('ROLLBACK' if fail else 'INSTALL')+' / REAL COMPOSE / DATA / SESSION KEY / MAC / ALIASES PASS',flush=True)
    finally:
        run('docker','rm','-f',worker_name,check=False)
        run(*command,'down','-v','--remove-orphans','--timeout','2',check=False,timeout=60)
        for service in ['gateway','xray','updater']:run('docker','image','rm','xray-gateway-rollback:'+identifier+'-'+service,check=False)
        if success:shutil.rmtree(folder)
        else:print('Isolated diagnostic files retained: '+str(folder),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--gateway-image',required=True);parser.add_argument('--updater-image',required=True);args=parser.parse_args()
    exercise(args.gateway_image,args.updater_image,False);exercise(args.gateway_image,args.updater_image,True)

if __name__=='__main__':main()

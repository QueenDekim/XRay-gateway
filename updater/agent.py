"""Poll the shared queue and launch detached, project-scoped update workers."""
import json,os,time
from pathlib import Path
from engine import context,inspect,mount,run
from update_protocol import ACTIVE,validate_request,write_json
from version import build_info

CONTROL=Path('/control')


def read(name):
    try:
        path=CONTROL/name
        if path.stat().st_size>262144:return {}
        return json.loads(path.read_text())
    except (OSError,ValueError):return {}


def failed(job,text):
    write_json(CONTROL/'job.json',job|{'status':'error','updated_at':time.time(),'error':text,'logs':(job.get('logs',[])+[text])[-200:]})


def worker(ctx,identifier,recover=False):
    name='xray-gw-update-'+identifier
    args=['docker','run','-d','--name',name,'--network','none','--cap-drop','ALL','--cap-add','DAC_OVERRIDE','--cap-add','CHOWN','--cap-add','FOWNER','--read-only','--security-opt','no-new-privileges:true','--tmpfs','/tmp:rw,nosuid,nodev',
        '--label','io.xray-gateway.update-worker='+identifier,'--label','io.xray-gateway.update-project='+ctx['project'],
        '--mount','type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock',
        '--mount','type=bind,src='+ctx['directory']+',dst='+ctx['directory'],
        '--mount',mount(ctx['data'],'/runtime'),'--mount',mount(ctx['control'],'/control'),
        '-e','UPDATE_PROJECT='+ctx['project'],'-e','UPDATE_DIRECTORY='+ctx['directory'],
        '-e','UPDATE_FILES='+json.dumps(ctx['files']),'-e','UPDATE_JOB_ID='+identifier,
        '--entrypoint','python3',ctx['agent']['Image'],'/app/worker.py']
    if recover:args.append('--recover')
    run(*args)


def tick():
    ctx=context();write_json(CONTROL/'agent.json',{'heartbeat':time.time(),'version':build_info()['version'],'protocol':1})
    job=read('job.json');identifier=job.get('id','')
    if identifier:
        import re
        if not re.fullmatch(r'[0-9a-f]{32}',identifier):raise ValueError('Invalid queued job')
        name='xray-gw-update-'+identifier
        try:existing=inspect(name)
        except Exception:existing=None
        if existing:
            labels=existing['Config'].get('Labels') or {}
            if labels.get('io.xray-gateway.update-worker')!=identifier or labels.get('io.xray-gateway.update-project')!=ctx['project']:raise ValueError('Worker name is already in use')
            if existing['State']['Running']:return
            run('docker','rm',name)
        if job.get('status') in ACTIVE and (job.get('status')!='queued' or existing is not None or ((CONTROL/'requests'/(identifier+'.json')).exists() and not (CONTROL/'request.json').exists())):
            if read('recovery.json').get('id')==identifier:
                failed(job,'Не удалось восстановить предыдущую версию. Проверьте резервную копию.');return
            write_json(CONTROL/'recovery.json',{'id':identifier});worker(ctx,identifier,True);return
    request=read('request.json')
    if not request:return
    try:
        validate_request(request)
        if not -30<=time.time()-float(request.get('created_at',0))<=600:raise ValueError('Expired update request')
        directory=CONTROL/'requests';directory.mkdir(exist_ok=True)
        write_json(directory/(request['id']+'.json'),request)
        (CONTROL/'request.json').unlink(missing_ok=True)
        worker(ctx,request['id'])
    except Exception:
        failed(job,'Не удалось запустить обновление. Проверьте службу обновления.')
    finally:(CONTROL/'request.json').unlink(missing_ok=True)


if __name__=='__main__':
    CONTROL.mkdir(parents=True,exist_ok=True)
    while True:
        try:tick()
        except Exception:pass
        time.sleep(5)

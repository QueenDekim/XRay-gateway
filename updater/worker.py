"""Backup, replace the Compose services, verify health and restore on failure."""
import base64,hashlib,json,os,re,sqlite3,sys,tarfile,time
from pathlib import Path
from contextlib import closing
from engine import inspect,run
from update_protocol import GATEWAY_IMAGE,UPDATER_IMAGE,validate_request,write_json

CONTROL=Path('/control');DATA=Path('/runtime')


def read(path):return json.loads(Path(path).read_text())


def phase(status,text,**fields):
    job=read(CONTROL/'job.json')
    if job.get('id')!=os.environ['UPDATE_JOB_ID']:raise ValueError('Update job changed')
    write_json(CONTROL/'job.json',job|{'status':status,'updated_at':time.time(),'logs':(job.get('logs',[])+[text])[-200:]}|fields)


def compose(state,override,*args):
    command=['docker','compose','--project-directory',state['directory'],'-p',state['project']]
    for path in state['files']:command+=['-f',path]
    if override is not None:command+=['-f',str(override)]
    command+=list(args);return run(*command,timeout=600,cwd=state['directory'])


def config(path,images,state):
    services={service:{'image':image} for service,image in images.items()}
    if state.get('gateway_networks'):services['gateway']['networks']=state['gateway_networks']
    write_json(path,{'services':services})


def network_state(layout,gateway):
    preserved={};override={}
    for key,settings in (layout['services']['gateway'].get('networks') or {}).items():
        name=layout['networks'][key].get('name') or key
        previous=gateway['NetworkSettings']['Networks'][name]
        settings=settings or {};fields={}
        if previous.get('MacAddress'):fields['mac_address']=previous['MacAddress']
        if settings.get('ipv4_address'):fields['ipv4_address']=settings['ipv4_address']
        aliases=previous.get('Aliases') or []
        if aliases:fields['aliases']=aliases
        override[key]=fields
        preserved[name]={'MacAddress':previous.get('MacAddress'),'Aliases':aliases,
            'IPAddress':previous.get('IPAddress') if settings.get('ipv4_address') else None}
    return preserved,override


def file_owner(path,owner):
    if hasattr(os,'chown'):os.chown(path,owner.st_uid,owner.st_gid)


def backup_owner(directory,workdir):
    if not directory.exists():return
    owner=workdir.stat()
    for path in [directory.parent,directory,*directory.rglob('*')]:
        if not path.is_symlink():file_owner(path,owner)


def environment(path,images):
    owner=path.stat() if path.exists() else path.parent.stat()
    mode=path.stat().st_mode&0o777 if path.exists() else 0o600
    text=path.read_text() if path.exists() else ''
    for key,value in images.items():
        line=key+'='+value
        if re.search(r'^'+key+r'=',text,re.M):text=re.sub(r'^'+key+r'=.*$',lambda match:line,text,flags=re.M)
        else:text=text.rstrip()+'\n'+line+'\n'
    temporary=path.with_suffix('.update.tmp');temporary.write_text(text);file_owner(temporary,owner);temporary.chmod(mode);temporary.replace(path)


def backup(directory):
    directory.mkdir(mode=0o700,parents=True,exist_ok=False)
    database=DATA/'panel.sqlite';snapshot=directory/'panel.sqlite'
    if database.exists():
        with closing(sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(snapshot)) as target:source.backup(target);target.commit()
        file_owner(snapshot,database.stat());snapshot.chmod(0o600)
    with tarfile.open(directory/'runtime.tar.gz','w:gz') as archive:
        for path in DATA.iterdir():
            if path.name not in {'panel.sqlite','panel.sqlite-wal','panel.sqlite-shm'}:archive.add(path,arcname=path.name)
        if snapshot.exists():archive.add(snapshot,arcname='panel.sqlite')
    (directory/'runtime.tar.gz').chmod(0o600)


def wait_for_writes(timeout=300):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            panel=read(CONTROL/'panel.json')
            if 0<=time.time()-panel['heartbeat']<30 and panel['writes']==0 and not panel.get('busy'):return
        except (OSError,ValueError,KeyError):pass
        time.sleep(1)
    raise RuntimeError('Panel writes did not finish')


def fingerprint():
    with closing(sqlite3.connect('file:'+str(DATA/'panel.sqlite')+'?mode=ro',uri=True)) as database:
        documents={key:hashlib.sha256(value.encode()).hexdigest() for key,value in database.execute('SELECT key,value FROM documents') if key not in {'stats'}}
    return {'auth':hashlib.sha256((DATA/'auth.json').read_bytes()).hexdigest(),'documents':documents}


def containers(project):
    result={}
    for service in ['gateway','xray','updater']:
        ids=run('docker','ps','-aq','--filter','label=com.docker.compose.project='+project,'--filter','label=com.docker.compose.service='+service).splitlines()
        if len(ids)!=1:raise ValueError('Invalid Compose service count')
        result[service]=inspect(ids[0])
    return result


def verify(state,tag,timeout=120):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            current=containers(state['project']);gateway=current['gateway']
            if gateway['State'].get('Health',{}).get('Status')!='healthy':raise ValueError('Gateway is not healthy')
            code='import json,os,urllib.request; print(urllib.request.urlopen("http://127.0.0.1:"+os.environ.get("PANEL_PORT","8080")+"/api/version",timeout=3).read().decode())'
            info=json.loads(run('docker','exec',gateway['Id'],'python3','-c',code))
            if info['version']!=tag:raise ValueError('Wrong gateway version')
            assert fingerprint()==state['fingerprint'],'Stored application state changed'
            for name,previous in state['network'].items():
                active=gateway['NetworkSettings']['Networks'][name]
                for key in ['IPAddress','MacAddress']:
                    if previous.get(key):assert active.get(key)==previous[key],key
                assert set(previous.get('Aliases') or [])<=set(active.get('Aliases') or []),'Network aliases changed'
            return
        except Exception:time.sleep(2)
    raise RuntimeError('Updated gateway did not pass health checks')


def rollback(state,directory):
    phase('rollback','Восстановление предыдущей версии.')
    rollback_file=directory/'rollback.override.json';config(rollback_file,state['old_images'],state)
    try:compose(state,rollback_file,'stop','gateway','xray','updater')
    except Exception:pass
    # The runtime is the exact mount of the managed gateway, never an arbitrary host path.
    if DATA.resolve()==Path('/') or not (directory/'runtime.tar.gz').is_file():raise ValueError('Invalid rollback data')
    import shutil
    for path in DATA.iterdir():
        if path.is_dir():shutil.rmtree(path)
        else:path.unlink()
    with tarfile.open(directory/'runtime.tar.gz') as archive:
        archive.extractall(DATA,filter='data')
        if hasattr(os,'chown'):
            for member in archive.getmembers():
                target=DATA/member.name
                if target.parent.resolve().is_relative_to(DATA.resolve()):os.chown(target,member.uid,member.gid,follow_symlinks=False)
    env=Path(state['directory'])/'.env'
    if state['environment'] is None:env.unlink(missing_ok=True)
    else:env.write_bytes(base64.b64decode(state['environment']));env.chmod(0o600)
    compose(state,rollback_file,'up','-d','--no-build','--pull','never','--force-recreate','gateway','xray','updater')
    verify(state,state['old_version'])
    phase('error','Обновление отменено. Предыдущая версия восстановлена.',rolled_back=True,backup=str(directory))
    backup_owner(directory,Path(state['directory']))


def main():
    identifier=os.environ['UPDATE_JOB_ID']
    if not re.fullmatch(r'[0-9a-f]{32}',identifier):raise ValueError('Invalid update job')
    project=os.environ['UPDATE_PROJECT'];workdir=Path(os.environ['UPDATE_DIRECTORY'])
    if not workdir.is_absolute() or workdir==Path('/'):raise ValueError('Invalid update directory')
    directory=workdir/'.backups'/('update-'+identifier)
    state_path=directory/'state.json';state=None
    if '--recover' in sys.argv:
        if not state_path.exists():phase('error','Обновление прервано до изменения контейнеров.');return
        state=read(state_path)
        if state['directory']!=str(workdir) or state['project']!=project:raise ValueError('Invalid recovery context')
        if state.get('backup_complete'):rollback(state,directory)
        else:phase('error','Обновление прервано до изменения контейнеров.')
        return
    try:
        request=validate_request(read(CONTROL/'requests'/(identifier+'.json')))
        phase('pulling','Загрузка образов обновления.')
        for image in [request['gateway_image'],request['updater_image']]:run('docker','pull',image,timeout=600)
        target=inspect(request['gateway_image']);labels=target['Config'].get('Labels') or {}
        if labels.get('io.xray-gateway.update-protocol')!='1' or labels.get('org.opencontainers.image.revision')!=request['revision']:raise ValueError('Image revision mismatch')
        updater=inspect(request['updater_image'])
        if (updater['Config'].get('Labels') or {}).get('io.xray-gateway.update-protocol')!='1' or (updater['Config'].get('Labels') or {}).get('org.opencontainers.image.revision')!=request['revision']:raise ValueError('Updater revision mismatch')
        core=labels.get('io.xray-gateway.core-image','')
        if not re.fullmatch(r'ghcr.io/xtls/xray-core(?::[A-Za-z0-9._-]+|@sha256:[0-9a-f]{64})',core):raise ValueError('Missing supported core image')
        run('docker','pull',core,timeout=600)
        current=containers(project)
        setup={'project':project,'directory':str(workdir),'files':json.loads(os.environ['UPDATE_FILES'])}
        layout=json.loads(compose(setup,None,'config','--format','json'));networks,network_override=network_state(layout,current['gateway'])
        code='from version import build_info; import json; print(json.dumps(build_info()))'
        old=json.loads(run('docker','exec',current['gateway']['Id'],'python3','-c',code))['version']
        phase('backing_up','Создание резервной копии данных.')
        wait_for_writes()
        saved=fingerprint();backup(directory)
        images={}
        for service,container in current.items():
            name='xray-gateway-rollback:'+identifier+'-'+service;run('docker','tag',container['Image'],name);images[service]=name
        env=workdir/'.env'
        state={'project':project,'directory':str(workdir),'files':json.loads(os.environ['UPDATE_FILES']),
            'old_images':images,'old_version':old,'environment':base64.b64encode(env.read_bytes()).decode() if env.exists() else None,
            'fingerprint':saved,'network':networks,'gateway_networks':network_override,'backup_complete':True}
        write_json(state_path,state)
        image_file=directory/'images.override.json';images={'gateway':request['gateway_image'],'xray':core,'updater':request['updater_image']};config(image_file,images,state)
        environment(env,{'GATEWAY_IMAGE':images['gateway'],'UPDATER_IMAGE':images['updater'],'XRAY_IMAGE':core})
        phase('installing','Перезапуск контейнеров с новой версией.',backup=str(directory))
        compose(state,image_file,'stop','xray','gateway','updater')
        compose(state,image_file,'up','-d','--no-build','--pull','never','--force-recreate','gateway','xray','updater')
        phase('verifying','Проверка версии, состояния и сохранности данных.')
        verify(state,request['tag'])
        backup_owner(directory,workdir)
        phase('done','Обновление установлено.',installed=request['tag'],backup=str(directory))
    except Exception as error:
        if directory.exists():(directory/'debug.log').write_text(str(error)+'\n'+getattr(error,'details',''));(directory/'debug.log').chmod(0o600)
        if state and state.get('backup_complete'):rollback(state,directory)
        else:phase('error','Обновление не установлено. Текущая версия не изменена.')
        backup_owner(directory,workdir)


if __name__=='__main__':main()

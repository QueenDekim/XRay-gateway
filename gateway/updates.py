"""Release checks and a filesystem bridge to the isolated Docker updater."""
import copy,json,os,re,secrets,threading,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from controller import atomic_json
from version import build_info
from update_protocol import GATEWAY_IMAGE,UPDATER_IMAGE,TAG,ACTIVE,MAINTENANCE,version_tuple,validate_request,write_json


def get_json(url,headers=None):
    request=Request(url,headers={'User-Agent':'Xray-Gateway-update-check','Accept':'application/json',**(headers or {})})
    with urlopen(request,timeout=15) as response:
        data=response.read(2_000_001)
        if len(data)>2_000_000:raise ValueError('Update metadata is too large')
        return json.loads(data),dict(response.headers)


def registry_digest(repository,tag):
    name=repository.removeprefix('ghcr.io/')
    token,_=get_json('https://ghcr.io/token?'+urlencode({'service':'ghcr.io','scope':'repository:'+name+':pull'}))
    manifest,headers=get_json('https://ghcr.io/v2/'+name+'/manifests/'+tag,
        {'Authorization':'Bearer '+token['token'],'Accept':'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'})
    digest=next((v for k,v in headers.items() if k.lower()=='docker-content-digest'),'')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):raise ValueError('Missing image digest')
    return repository+'@'+digest


class Updates:
    def __init__(self,controller,control=None,current=None):
        self.controller=controller;self.control=Path(control or os.environ.get('UPDATE_CONTROL_DIR','/run/xray-updates'))
        self.current=current or build_info();self.current_number=tuple(map(int,self.current['version'].split('-')[0].split('.')));self.lock=threading.RLock();self.checking=False;self.last_auto_tag=None;self.active_writes=0;self.busy=False;self.last_attempt=0
        self.path=controller.directory/'updates-cache.json'
        try:self.cache=json.loads(self.path.read_text())
        except (OSError,ValueError):self.cache={'checked_at':None,'available':None,'error':None}
        self.next_check=time.time()+5

    def settings(self):
        with self.controller.lock:return {'check_interval_hours':6,'auto_install':False}|self.controller.load('updates_settings',{})

    def save_settings(self,data):
        interval=data.get('check_interval_hours',6);automatic=data.get('auto_install',False)
        if isinstance(interval,bool) or not isinstance(interval,int) or not 1<=interval<=168 or not isinstance(automatic,bool):
            raise ValueError('Проверьте интервал и режим автоматического обновления.')
        with self.controller.lock:self.controller.save('updates_settings',{'check_interval_hours':interval,'auto_install':automatic})
        self.next_check=time.time();return self.snapshot()

    def pulse(self):
        if self.control.is_dir():write_json(self.control/'panel.json',{'heartbeat':time.time(),'writes':self.active_writes,'busy':self.busy})

    def heartbeat(self):
        with self.controller.lock:
            busy=self.controller.applying
            router=getattr(self.controller,'router_service',None)
            if router:
                with router.lock:busy=busy or any(job['status'] in ('queued','running') for job in router.jobs.values())
        with self.lock:self.busy=busy;self.pulse()

    def enter_write(self):
        with self.lock:
            if self.maintenance():return False
            self.active_writes+=1;self.pulse();return True

    def leave_write(self):
        with self.lock:self.active_writes=max(0,self.active_writes-1)
        self.heartbeat()

    def read_control(self,name):
        try:
            path=self.control/name
            if path.stat().st_size>262144:return {}
            value=json.loads(path.read_text());return value if isinstance(value,dict) else {}
        except (OSError,ValueError):return {}

    def snapshot(self,admin=True):
        settings=self.settings()
        with self.lock:cache=copy.deepcopy(self.cache);checking=self.checking
        if cache.get('available') and version_tuple(cache['available']['tag'])<=self.current_number:cache['available']=None
        agent=self.read_control('agent.json');job=self.read_control('job.json')
        healthy=agent.get('protocol')==1 and 0<=time.time()-agent.get('heartbeat',0)<45
        public={k:cache.get(k) for k in ('checked_at','error')}
        candidate=cache.get('available')
        public.update(current=self.current['version'],available={k:candidate[k] for k in ('tag','version','revision','url')} if candidate else None,
            checking=checking,configured=healthy,settings=settings if admin else None,
            job=(job if admin else {k:v for k,v in job.items() if k in ('id','tag','status','installed','rolled_back','updated_at')}) if job else None)
        return public

    def maintenance(self):return self.read_control('job.json').get('status') in MAINTENANCE

    def check(self,started=False):
        if not started:
            with self.lock:
                busy=self.checking
                if not busy:self.checking=True;self.last_attempt=time.time()
            if busy:return self.snapshot()
        try:
            tags,_=get_json('https://api.github.com/repos/QueenDekim/XRay-gateway/tags?per_page=100')
            if not isinstance(tags,list):raise ValueError('Invalid release list')
            candidates=[]
            for entry in tags:
                tag=entry.get('name','');revision=entry.get('commit',{}).get('sha','')
                if TAG.fullmatch(tag) and re.fullmatch(r'[0-9a-f]{40}',revision) and revision.startswith(tag.rsplit('-',1)[1]):candidates.append((version_tuple(tag),tag,revision))
            available=None
            for number,tag,revision in sorted(candidates,reverse=True):
                if number<=self.current_number:break
                try:
                    gateway=registry_digest(GATEWAY_IMAGE,tag);updater=registry_digest(UPDATER_IMAGE,tag)
                except Exception:continue  # Tags can appear before image publication finishes.
                available={'tag':tag,'version':tag.split('-')[0],'revision':revision,'url':'https://github.com/QueenDekim/XRay-gateway/tree/'+tag,
                    'gateway_image':gateway,'updater_image':updater};break
            cache={'checked_at':time.time(),'available':available,'error':None}
        except Exception:
            with self.lock:cache=self.cache|{'error':'Не удалось проверить обновления. Повторите позже.'}
        finally:
            with self.lock:self.checking=False
        with self.lock:self.cache=cache;atomic_json(self.path,cache)
        self.next_check=time.time()+(300 if cache['error'] else self.settings()['check_interval_hours']*3600)
        return self.snapshot()

    def start_check(self):
        with self.lock:
            busy=self.checking or time.time()-self.last_attempt<60
            if not busy:self.checking=True;self.last_attempt=time.time()
        if not busy:threading.Thread(target=lambda:self.check(started=True),daemon=True).start()
        return self.snapshot()

    def install(self,tag):
        if not self.snapshot()['configured']:raise ValueError('Служба обновления не подключена.')
        with self.lock:
            candidate=self.cache.get('available')
            if not candidate or candidate['tag']!=tag or version_tuple(tag)<=self.current_number:raise ValueError('Обновление недоступно. Проверьте версии повторно.')
            if self.read_control('job.json').get('status') in ACTIVE:raise ValueError('Обновление уже выполняется.')
            request=validate_request({'protocol':1,'id':secrets.token_hex(16),'created_at':time.time(),**{k:candidate[k] for k in ('tag','revision','gateway_image','updater_image')}})
            atomic_json(self.control/'job.json',{'id':request['id'],'tag':tag,'status':'queued','updated_at':time.time(),'logs':['Обновление поставлено в очередь.']})
            atomic_json(self.control/'request.json',request)
            return {'id':request['id']}

    def run(self):
        while True:
            try:
                self.heartbeat()
                if time.time()>=self.next_check:self.start_check()
                snapshot=self.snapshot();candidate=snapshot['available']
                if snapshot['settings']['auto_install'] and snapshot['configured'] and candidate and version_tuple(candidate['tag'])[0]==self.current_number[0] and self.last_auto_tag!=candidate['tag']:
                    self.last_auto_tag=candidate['tag'];self.install(candidate['tag'])
            except Exception:pass
            time.sleep(5)

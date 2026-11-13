"""Pinned SSH connections, owned RouterOS resources and bounded interactive PTYs."""
import base64
import copy
import hashlib
import hmac
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import threading
import time
import paramiko
from controller import atomic_json,routeros
from secure_store import SecretStore


def fingerprint(key):
    return 'SHA256:'+base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')


def endpoint(data):
    host=str(data.get('host','')).strip()
    if not host or len(host)>253 or not re.fullmatch(r'[a-zA-Z0-9_.:-]+',host):raise ValueError('Некорректный адрес RouterOS.')
    try:port=int(data.get('port',22))
    except (ValueError,TypeError):raise ValueError('Некорректный SSH-порт.') from None
    if not 1<=port<=65535:raise ValueError('Некорректный SSH-порт.')
    return host,port


def cleanup_script(key):
    if not re.fullmatch(r'(?:project|list_[a-f0-9]{12})',key):raise ValueError('Некорректный идентификатор IP-списка.')
    lines=[]
    for comment in ('WATCH','ROUTE','LOCAL','MARK'):
        menu='/tool netwatch' if comment=='WATCH' else '/ip firewall mangle'
        lines.append(f'{menu} remove [find comment=XRAY-GW-{comment}-{key}]')
    lines.append(f'/ip route remove [find comment=XRAY-GW-TABLE-{key}]')
    for family in ('ip','ipv6'):
        for kind in ('DEST','LOCAL','EXEMPT'):
            lines.append(f'/{family} firewall address-list remove [find list=XRAY-{kind}-{key}]')
    lines.append(f'/routing table remove [find name=xray-gateway-{key}]')
    return '\n'.join(lines)


class PinnedKey(paramiko.MissingHostKeyPolicy):
    def __init__(self,expected):self.expected=expected
    def missing_host_key(self,client,hostname,key):
        if not hmac.compare_digest(fingerprint(key),self.expected):raise ValueError('Ключ SSH-сервера изменился. Проверьте отпечаток RouterOS.')


class RouterService:
    def __init__(self,controller):
        self.controller=controller
        self.path=controller.directory/'routeros.json'
        self.secrets=SecretStore(controller.directory)
        self.lock=threading.RLock()
        self.operation_lock=threading.Lock()
        self.jobs={};self.busy={};self.terminals={}
        network=ipaddress.ip_network(controller.settings()['source'])
        self.default_host=str(network.network_address+1)

    def config(self):
        if self.path.exists():return json.loads(self.path.read_text(encoding='utf-8'))
        return {'host':os.environ.get('ROUTEROS_HOST',self.default_host),
                'port':int(os.environ.get('ROUTEROS_PORT','22')),'username':'','auth':'key','fingerprint':''}

    def public_config(self):
        with self.lock:
            config=self.config()
            passphrase=config.get('passphrase_set',False)
            if config.get('secret') and 'passphrase_set' not in config and config['auth']=='key':
                try:value=self.secrets.open(config['secret'],'routeros:'+config['host']+':'+str(config['port'])+':'+config['username']+':'+config['auth'])
                except RuntimeError as exc:raise ValueError(str(exc)) from None
                passphrase=bool(value.get('passphrase'))
            return {k:config.get(k,'') for k in ('host','port','username','auth','fingerprint')}|{'configured':bool(config.get('secret')),'passphrase_set':passphrase}

    def scan(self,data):
        host,port=endpoint(data)
        try:
            with socket.create_connection((host,port),timeout=8) as connection:
                transport=paramiko.Transport(connection)
                try:
                    transport.start_client(timeout=8)
                    key=transport.get_remote_server_key()
                    return {'fingerprint':fingerprint(key),'algorithm':key.get_name()}
                finally:transport.close()
        except Exception:raise ValueError('Не удалось получить SSH-ключ RouterOS.') from None

    def save(self,data):
        host,port=endpoint(data);username=str(data.get('username','')).strip();auth=data.get('auth','key')
        if not username or len(username)>64 or any(c.isspace() for c in username):raise ValueError('Укажите SSH-логин RouterOS.')
        if auth not in ('key','password'):raise ValueError('Некорректный способ SSH-авторизации.')
        pin=str(data.get('fingerprint','')).strip()
        if not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}',pin):raise ValueError('Подтвердите отпечаток SSH-ключа RouterOS.')
        with self.lock:
            previous=self.config()
            credential=data.get('private_key' if auth=='key' else 'password')
            if auth=='key' and not credential and data.get('passphrase'):raise ValueError('Для смены пароля ключа укажите приватный SSH-ключ.')
            if credential:
                if not isinstance(credential,str) or len(credential)>32768:raise ValueError('Некорректные SSH-реквизиты.')
                value={'value':credential,'passphrase':str(data.get('passphrase','')) if auth=='key' else ''}
                encrypted=self.secrets.seal(value,'routeros:'+host+':'+str(port)+':'+username+':'+auth)
            elif all(previous.get(k)==v for k,v in [('host',host),('port',port),('username',username),('auth',auth)]) and previous.get('secret'):
                encrypted=previous['secret']
            else:raise ValueError('Укажите пароль или приватный SSH-ключ.')
            passphrase_set=bool(value.get('passphrase')) if credential and auth=='key' else (self.public_config()['passphrase_set'] if auth=='key' else False)
            config={'host':host,'port':port,'username':username,'auth':auth,'fingerprint':pin,'secret':encrypted,'passphrase_set':passphrase_set}
        client=self.connect(config)
        try:
            self.execute(client,'/system identity print',lambda line:None,15)
        finally:client.close()
        with self.lock:
            atomic_json(self.path,config)
            for identifier in list(self.terminals):self.close_terminal(identifier)
        return self.public_config()

    def connect(self,config=None):
        config=config or self.config()
        if not config.get('secret'):raise ValueError('Настройте подключение к RouterOS.')
        credential=self.secrets.open(config['secret'],'routeros:'+config['host']+':'+str(config['port'])+':'+config['username']+':'+config['auth'])
        arguments={'hostname':config['host'],'port':config['port'],'username':config['username'],
                   'timeout':10,'auth_timeout':10,'banner_timeout':10,'allow_agent':False,'look_for_keys':False}
        if config['auth']=='key':
            key=None
            for kind in (paramiko.RSAKey,paramiko.Ed25519Key,paramiko.ECDSAKey):
                try:key=kind.from_private_key(io.StringIO(credential['value']),password=credential.get('passphrase') or None);break
                except (paramiko.SSHException,ValueError):pass
            if key is None:raise ValueError('Не удалось прочитать приватный SSH-ключ.')
            arguments['pkey']=key
        else:arguments['password']=credential['value']
        client=paramiko.SSHClient();client.set_missing_host_key_policy(PinnedKey(config['fingerprint']))
        try:client.connect(**arguments);client.get_transport().set_keepalive(15);return client
        except ValueError:client.close();raise
        except paramiko.AuthenticationException:client.close();raise ValueError('RouterOS отклонил SSH-авторизацию.') from None
        except Exception:client.close();raise ValueError('Не удалось подключиться к RouterOS по SSH.') from None

    def execute(self,client,command,log,timeout=120):
        channel=client.get_transport().open_session(timeout=10);channel.exec_command(command)
        output=bytearray();until=time.monotonic()+timeout;pending=b''
        try:
            while True:
                chunk=b''
                if channel.recv_ready():chunk+=channel.recv(32768)
                if channel.recv_stderr_ready():chunk+=channel.recv_stderr(32768)
                if chunk:
                    output.extend(chunk);pending+=chunk
                    while b'\n' in pending:
                        line,pending=pending.split(b'\n',1);log(line.decode('utf-8','replace').rstrip('\r'))
                    if len(output)>2_000_000:raise ValueError('Вывод RouterOS превысил допустимый размер.')
                elif channel.exit_status_ready():break
                else:
                    if time.monotonic()>until:raise ValueError('Истекло время выполнения команды RouterOS.')
                    time.sleep(.03)
            if pending:log(pending.decode('utf-8','replace'))
            text=output.decode('utf-8','replace')
            if channel.recv_exit_status()!=0 or re.search(r'(?im)^\s*(failure:|syntax error|expected end of command|bad command name|not enough permissions|script error)',text):
                raise ValueError('RouterOS сообщил об ошибке. Откройте журнал операции.')
            return text
        finally:channel.close()

    def import_script(self,script,log):
        client=self.connect();sftp=None;filename='xray-gw-'+secrets.token_hex(8)+'.rsc';marker='XG-OK-'+secrets.token_hex(12)
        try:
            log('SSH: подключение установлено')
            sftp=client.open_sftp()
            with sftp.open(filename,'w') as stream:stream.write((script+'\n:put "'+marker+'"\n').encode('utf-8'))
            log('RouterOS: импорт конфигурации')
            result=self.execute(client,'/import file-name="'+filename+'" verbose=yes',log)
            if not any(line.strip()==marker for line in result.splitlines()):raise ValueError('RouterOS не подтвердил завершение импорта.')
            log('RouterOS: импорт завершён')
        finally:
            if sftp:
                try:sftp.remove(filename)
                except OSError:log('Не удалось удалить временный файл импорта')
                sftp.close()
            client.close()

    def start(self,action,identifier,version,actor,defaults=()):
        if action not in ('apply','delete'):raise ValueError('Некорректное действие.')
        if not re.fullmatch(r'(?:project|list_[a-f0-9]{12})',identifier):raise ValueError('Некорректный идентификатор IP-списка.')
        with self.controller.lock,self.lock:
            if not self.public_config()['configured']:raise ValueError('Настройте подключение к RouterOS.')
            item=next((item for item in self.controller.ip_lists(defaults) if item['id']==identifier),None)
            if not item or item['version']!=int(version):raise ValueError('Список изменился. Обновите страницу.')
            if identifier in self.busy:raise ValueError('Для списка уже выполняется операция RouterOS.')
            if sum(job['status'] in ('queued','running') for job in self.jobs.values())>=10:raise ValueError('Слишком много операций RouterOS. Подождите завершения.')
            job_id=secrets.token_hex(16)
            job={'id':job_id,'action':action,'list_id':identifier,'name':item['name'],'owner':actor['id'],'status':'queued','logs':[],'offset':0,'created':time.time()}
            self.jobs[job_id]=job;self.busy[identifier]=job_id
            settings=copy.deepcopy(self.controller.settings())
        def log(line):
            with self.lock:
                job['logs'].append(str(line)[:2000])
                if len(job['logs'])>600:job['logs'].pop(0);job['offset']+=1
        def work():
            try:
                with self.operation_lock:
                    with self.lock:job['status']='running'
                    script=cleanup_script(identifier)
                    if action=='apply' and item['addresses']:
                        warnings=[]
                        script=routeros(settings|{'destinations':'\n'.join(item['addresses']),'list_key':identifier,'list_name':item['name']},[],warnings)
                        for warning in warnings:log(warning)
                    self.import_script(script,log)
                    if action=='delete':
                        with self.controller.lock,self.lock:
                            self.busy.pop(identifier,None)
                            self.controller.change_ip_list('delete',{'id':identifier,'version':item['version']},defaults)
                        log('Список удалён из панели и RouterOS')
                    else:log('Список установлен в RouterOS')
                    with self.lock:job['status']='done'
            except Exception as exc:
                log(str(exc) if isinstance(exc,ValueError) else 'Не удалось выполнить операцию RouterOS.')
                with self.lock:job['status']='error'
            finally:
                with self.lock:
                    self.busy.pop(identifier,None)
                    for old in sorted(self.jobs.values(),key=lambda j:j['created'])[:-30]:
                        if old['status'] in ('done','error'):self.jobs.pop(old['id'],None)
        threading.Thread(target=work,daemon=True).start()
        return self.job(job_id,actor)

    def job(self,identifier,actor,cursor=0):
        with self.lock:
            job=self.jobs.get(identifier)
            if not job or (job['owner']!=actor['id'] and actor['role']!='admin'):raise ValueError('Операция не найдена.')
            index=max(0,int(cursor)-job['offset'])
            return {k:job[k] for k in ('id','action','list_id','name','status')}|{'logs':job['logs'][index:],'cursor':job['offset']+len(job['logs'])}

    def recent(self,actor):
        with self.lock:
            return [self.job(job['id'],actor) for job in reversed(list(self.jobs.values())) if job['owner']==actor['id'] or actor['role']=='admin'][:20]

    def open_terminal(self,actor,session,cols=100,rows=30):
        client=self.connect()
        try:channel=client.invoke_shell(term='xterm',width=max(20,min(300,int(cols))),height=max(5,min(100,int(rows))))
        except Exception:client.close();raise
        channel.settimeout(5)
        identifier=secrets.token_hex(24)
        with self.lock:
            for old,item in list(self.terminals.items()):
                if item['owner']==actor['id'] or time.monotonic()-item['active']>300:self.close_terminal(old)
            if len(self.terminals)>=8:channel.close();client.close();raise ValueError('Достигнут предел SSH-терминалов.')
            terminal={'owner':actor['id'],'session':session,'client':client,'channel':channel,'buffer':bytearray(),'offset':0,'active':time.monotonic(),'started':time.monotonic()}
            self.terminals[identifier]=terminal
        def read():
            try:
                while not channel.closed:
                    if time.monotonic()-terminal['active']>300 or time.monotonic()-terminal['started']>3600:break
                    if channel.recv_ready():
                        data=channel.recv(32768)
                        if not data:break
                        with self.lock:
                            terminal['buffer'].extend(data)
                            if len(terminal['buffer'])>262144:
                                count=len(terminal['buffer'])-262144;del terminal['buffer'][:count];terminal['offset']+=count
                    else:time.sleep(.03)
            except (OSError,paramiko.SSHException):pass
            finally:channel.close();client.close()
        threading.Thread(target=read,daemon=True).start()
        return {'id':identifier}

    def terminal(self,identifier,actor,session):
        with self.lock:
            item=self.terminals.get(identifier)
            if not item or item['owner']!=actor['id'] or item['session']!=session:raise ValueError('Терминал не найден или отключён.')
            return item

    def read_terminal(self,identifier,actor,session,cursor):
        with self.lock:
            item=self.terminal(identifier,actor,session);start=max(0,int(cursor)-item['offset']);data=bytes(item['buffer'][start:])
            return {'data':base64.b64encode(data).decode(),'cursor':item['offset']+len(item['buffer']),'closed':item['channel'].closed}

    def write_terminal(self,identifier,actor,session,data):
        if not isinstance(data,str) or len(data)>32768:raise ValueError('Слишком большой ввод терминала.')
        item=self.terminal(identifier,actor,session);item['active']=time.monotonic();item['channel'].sendall(data.encode('utf-8'))

    def resize_terminal(self,identifier,actor,session,cols,rows):
        item=self.terminal(identifier,actor,session);item['active']=time.monotonic()
        item['channel'].resize_pty(width=max(20,min(300,int(cols))),height=max(5,min(100,int(rows))))

    def close_terminal(self,identifier):
        with self.lock:
            item=self.terminals.pop(identifier,None)
            if item:item['channel'].close();item['client'].close()

    def logout(self,session):
        with self.lock:
            for key,item in list(self.terminals.items()):
                if item['session']==session:self.close_terminal(key)

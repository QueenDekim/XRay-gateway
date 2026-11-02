"""Test empty-volume startup and authentication in isolated Docker containers."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid


def docker(*args, check=True):
    return subprocess.run(['docker',*args],capture_output=True,text=True,check=check)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default='xray-gateway:publication-check')
    parser.add_argument('--xray-image',default='ghcr.io/xtls/xray-core:26.10.21')
    args=parser.parse_args()
    suffix=uuid.uuid4().hex[:10]
    gateway,core='xray-smoke-gateway-'+suffix,'xray-smoke-core-'+suffix
    password='smoke-test-password'
    with tempfile.TemporaryDirectory(prefix='xray-smoke-') as temporary:
        root=Path(temporary).resolve()
        assert root.parent==Path(tempfile.gettempdir()).resolve()
        runtime=root/'runtime';runtime.mkdir()
        secret=root/'password';secret.write_text(password)
        try:
            for attempt in range(2):
                docker('run','-d','--name',gateway,'--cap-add','NET_ADMIN','--cap-add','NET_RAW',
                       '--sysctl','net.ipv4.conf.all.src_valid_mark=0',
                       '--mount',f'type=bind,source={runtime},target=/data',
                       '--mount',f'type=bind,source={secret},target=/run/secrets/admin_password,readonly',
                       '-e','ADMIN_USERNAME=smoke-owner',args.image)
                until=time.monotonic()+30
                while not (runtime/'config.json').is_file():
                    if time.monotonic()>until:
                        raise RuntimeError('Gateway did not initialize config.json: '+docker('logs',gateway).stdout)
                    time.sleep(.5)
                docker('run','-d','--name',core,'--user','0:0','--cap-add','NET_ADMIN','--network','container:'+gateway,'--pid','container:'+gateway,
                       '--mount',f'type=bind,source={runtime},target=/usr/local/etc/xray,readonly',
                       args.xray_image,'run','-c','/usr/local/etc/xray/config.json')
                code="import urllib.request; urllib.request.urlopen('http://127.0.0.1:18080/health',timeout=2).read()"
                until=time.monotonic()+45
                while docker('exec',gateway,'python3','-c',code,check=False).returncode:
                    if time.monotonic()>until:
                        raise RuntimeError('Gateway health did not become ready: '+docker('logs',gateway).stdout+docker('logs',gateway).stderr+docker('logs',core).stdout+docker('logs',core).stderr)
                    time.sleep(.5)
                login="""import http.cookiejar,json,urllib.request
jar=http.cookiejar.CookieJar()
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
request=urllib.request.Request('http://127.0.0.1:8080/api/login',data=json.dumps({'username':'smoke-owner','password':'smoke-test-password'}).encode(),headers={'Content-Type':'application/json'})
client.open(request).read()
state=json.load(client.open('http://127.0.0.1:8080/api/state'))
assert state['username']=='smoke-owner' and state['profiles']==[] and state['ip_lists']==[] and state['ready']
assert state['settings']['source']=='192.168.50.0/24'
print('Fresh-volume state and authentication PASS')
"""
                result=docker('exec',gateway,'python3','-c',login)
                print(result.stdout.strip())
                docker('rm','-f',core,gateway)
                secret.write_text('replacement-must-not-reset-account')
            print('PERSISTENT ACCOUNT / EMPTY PROFILES / XRAY API / HEALTH PASS')
        finally:
            docker('rm','-f',core,gateway,check=False)


if __name__=='__main__':
    main()

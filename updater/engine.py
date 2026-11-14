"""Docker CLI calls and scoped Compose context for the updater only."""
import json,os,subprocess
from pathlib import PurePosixPath


def run(*args,timeout=180,cwd=None):
    result=subprocess.run(list(args),text=True,capture_output=True,timeout=timeout,cwd=cwd)
    if result.returncode:
        error=RuntimeError('Command failed: '+args[0]);error.details=result.stdout+'\n'+result.stderr;raise error
    return result.stdout


def docker_json(*args):return json.loads(run('docker',*args))


def inspect(name):return docker_json('inspect',name)[0]


def context():
    agent=inspect(os.environ['HOSTNAME']);labels=agent['Config'].get('Labels') or {};project=labels.get('com.docker.compose.project')
    if not project or labels.get('com.docker.compose.service')!='updater':raise ValueError('Updater must run as the Compose updater service')
    # docker ps --format json emits one JSON object per line.
    def one(name):
        rows=run('docker','ps','-aq','--filter','label=com.docker.compose.project='+project,'--filter','label=com.docker.compose.service='+name).splitlines()
        if len(rows)!=1:raise ValueError('Expected exactly one '+name+' service')
        return inspect(rows[0])
    gateway=one('gateway');core=one('xray')
    labels=gateway['Config'].get('Labels') or {};workdir=PurePosixPath(labels.get('com.docker.compose.project.working_dir',''))
    if not workdir.is_absolute() or str(workdir)=='/' or '..' in workdir.parts:raise ValueError('Invalid Compose directory')
    files=[]
    for value in labels.get('com.docker.compose.project.config_files','').split(','):
        path=PurePosixPath(value)
        if not path.is_absolute() or '..' in path.parts or not path.is_relative_to(workdir):raise ValueError('Compose files must be inside the project directory')
        if path.name in ('images.override.json','rollback.override.json') and '.backups' in path.parts:continue
        files.append(str(path))
    if not files:raise ValueError('Missing Compose files')
    data=next((m for m in gateway['Mounts'] if m['Destination']=='/data'),None)
    control=next((m for m in agent['Mounts'] if m['Destination']=='/control'),None)
    if not data or not control or data.get('Source')=='/':raise ValueError('Missing scoped runtime/control mounts')
    return {'project':project,'directory':str(workdir),'files':files,'data':data,'control':control,'agent':agent,'gateway':gateway,'core':core}


def mount(mount,destination):
    if mount['Type']=='volume':return 'type=volume,src='+mount['Name']+',dst='+destination
    if mount['Type']=='bind':return 'type=bind,src='+mount['Source']+',dst='+destination
    raise ValueError('Unsupported updater mount')

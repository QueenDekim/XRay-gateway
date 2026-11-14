"""Encrypted, bounded sessions that retain expiry and account revision checks."""
import json,time
from controller import atomic_json
from secure_store import SecretStore

FIELDS=('expires','csrf','user_id','user_revision')


def save(controller,sessions):
    values={token:{key:value[key] for key in FIELDS} for token,value in sessions.items() if value.get('expires',0)>time.time() and all(key in value for key in FIELDS)}
    atomic_json(controller.directory/'sessions.enc.json',{'sealed':SecretStore(controller.directory).seal(json.dumps(values),'panel-sessions')})


def load(controller):
    try:
        stored=json.loads((controller.directory/'sessions.enc.json').read_text())
        values=json.loads(SecretStore(controller.directory).open(stored['sealed'],'panel-sessions'))
        if not isinstance(values,dict) or len(values)>128:return {}
        return {token:value for token,value in values.items() if isinstance(token,str) and isinstance(value,dict) and all(key in value for key in FIELDS) and value['expires']>time.time()}
    except (OSError,ValueError,TypeError,KeyError,RuntimeError):return {}

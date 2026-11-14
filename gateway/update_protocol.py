"""Shared, bounded update request format; no arbitrary container commands."""
import re
GATEWAY_IMAGE='ghcr.io/queendekim/xray-gateway'
UPDATER_IMAGE='ghcr.io/queendekim/xray-gateway-updater'
TAG=re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-([0-9a-f]{7})')
ACTIVE={'queued','pulling','backing_up','installing','verifying','rollback'}
MAINTENANCE={'backing_up','installing','verifying','rollback'}


def version_tuple(tag):
    match=TAG.fullmatch(tag)
    if not match:raise ValueError('Invalid update version')
    return tuple(int(match[i]) for i in (1,2,3))


def validate_request(value):
    if not isinstance(value,dict) or value.get('protocol')!=1:raise ValueError('Invalid update protocol')
    if not re.fullmatch(r'[0-9a-f]{32}',value.get('id','')):raise ValueError('Invalid update ID')
    version_tuple(value.get('tag',''))
    if not re.fullmatch(r'[0-9a-f]{40}',value.get('revision','')) or not value['revision'].startswith(value['tag'].rsplit('-',1)[1]):raise ValueError('Invalid update revision')
    for key,repository in [('gateway_image',GATEWAY_IMAGE),('updater_image',UPDATER_IMAGE)]:
        if not re.fullmatch(re.escape(repository)+r'@sha256:[0-9a-f]{64}',value.get(key,'')):raise ValueError('Invalid update image')
    return value


def write_json(path,value):
    import json,os
    from pathlib import Path
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    with temporary.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    temporary.chmod(0o600);temporary.replace(path)

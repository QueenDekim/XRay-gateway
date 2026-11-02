"""Create the first administrator while preserving an existing installation."""
import os
from pathlib import Path
import time
import uuid
from accounts import password_hash
from controller import atomic_json


def initialize_accounts(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'auth.json'
    if path.exists():
        return False
    username = os.environ.get('ADMIN_USERNAME', 'admin').strip()
    if not 1 <= len(username) <= 64 or any(c.isspace() or not c.isprintable() for c in username):
        raise ValueError('Invalid ADMIN_USERNAME')
    password_file = Path(os.environ.get('ADMIN_PASSWORD_FILE', '/run/secrets/admin_password'))
    try:
        password = password_file.read_text(encoding='utf-8').rstrip('\r\n')
    except OSError:
        raise RuntimeError('Create the administrator password file before starting the gateway') from None
    user = dict(password_hash(password), id='user_' + uuid.uuid4().hex[:16], username=username,
                role='admin', revision=1, created_at=time.time())
    atomic_json(path, {'version': 2, 'users': [user]})
    return True

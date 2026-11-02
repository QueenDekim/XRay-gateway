"""Local recovery: set/create one administrator without deleting other users."""
import getpass
import os
import threading
import time
import uuid
from pathlib import Path
from accounts import Accounts, password_hash
from controller import atomic_json


def main():
    username = input('Login [admin]: ').strip() or 'admin'
    if not 1 <= len(username) <= 64 or any(c.isspace() or not c.isprintable() for c in username):
        raise SystemExit('Invalid login.')
    password = getpass.getpass('New password: ')
    if password != getpass.getpass('Repeat password: '):
        raise SystemExit('Passwords do not match.')
    try:
        hashed = password_hash(password)
    except ValueError as exc:
        raise SystemExit(str(exc))
    path = Path(os.environ.get('DATA_DIR', '/data')) / 'auth.json'
    store = Accounts(path, threading.RLock())
    with store.lock:
        data = store.load() if path.exists() else {'version':2, 'users':[]}
        user = next((u for u in data['users'] if u['username'].casefold() == username.casefold()), None)
        if user is None:
            user = {'id':'user_' + uuid.uuid4().hex[:16], 'revision':0, 'created_at':time.time()}
            data['users'].append(user)
        user.update(hashed, username=username, role='admin', revision=user['revision'] + 1)
        atomic_json(path, data)
    print('Administrator updated. Its earlier sessions are revoked; other accounts are preserved.')


if __name__ == '__main__':
    main()

"""Encrypt persistent service credentials with a volume-local key."""
import json
import os
from pathlib import Path
import threading
from cryptography.fernet import Fernet, InvalidToken

_lock=threading.RLock()


class SecretStore:
    def __init__(self,directory):
        self.path=Path(directory)/'.encryption-key'

    def cipher(self,create=False):
        with _lock:
            if create and not self.path.exists():
                self.path.parent.mkdir(parents=True,exist_ok=True)
                descriptor=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(descriptor,'wb') as stream:stream.write(Fernet.generate_key())
            try:return Fernet(self.path.read_bytes())
            except (OSError,ValueError):raise RuntimeError('Ключ шифрования недоступен. Восстановите резервную копию.') from None

    def seal(self,value,context):
        return self.cipher(True).encrypt(json.dumps({'context':context,'value':value}).encode()).decode()

    def open(self,value,context):
        try:
            result=json.loads(self.cipher().decrypt(value.encode()))
            if result['context']!=context:raise ValueError()
            return result['value']
        except (InvalidToken,ValueError,KeyError,TypeError):
            raise RuntimeError('Не удалось расшифровать сохранённые данные.') from None

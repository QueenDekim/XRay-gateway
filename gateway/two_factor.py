"""TOTP (RFC 6238), replay protection and single-use recovery codes."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import urlencode,quote


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def totp(secret,step,digits=6):
    key=base64.b32decode(secret+'='*((-len(secret))%8),casefold=True)
    digest=hmac.new(key,struct.pack('>Q',step),hashlib.sha1).digest()
    offset=digest[-1]&15
    return str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%10**digits).zfill(digits)


def match_step(secret,code,last_step=-1,now=None):
    code=str(code).strip()
    if len(code)!=6 or not code.isascii() or not code.isdigit():return None
    current=int((time.time() if now is None else now)//30)
    for step in (current,current-1,current+1):
        if step>=0 and step>last_step and hmac.compare_digest(totp(secret,step),code):return step
    return None


def recovery_hash(identifier,code):
    normalized=str(code).replace('-','').replace(' ','').lower()
    return hashlib.sha256((identifier+':'+normalized).encode()).hexdigest()


def recovery_codes(identifier):
    values=[secrets.token_hex(16) for _ in range(10)]
    codes=['-'.join(value[i:i+4] for i in range(0,32,4)) for value in values]
    return codes,[recovery_hash(identifier,code) for code in codes]


def provisioning_uri(secret,username):
    return 'otpauth://totp/'+quote('Xray Gateway:'+username,safe='')+'?'+urlencode({'secret':secret,'issuer':'Xray Gateway','algorithm':'SHA1','digits':6,'period':30})

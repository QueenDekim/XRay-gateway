"""Build Xray configuration from VLESS subscription URLs without unsafe TLS bypass."""
import argparse, base64, json, os, pathlib, re, sys
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
ROOT=pathlib.Path(__file__).resolve().parents[1]

TRANSPORT_ALIASES={'tcp':'tcp','raw':'tcp','xhttp':'xhttp','splithttp':'xhttp',
                   'ws':'ws','websocket':'ws','grpc':'grpc','httpupgrade':'httpupgrade',
                   'kcp':'kcp','mkcp':'kcp','hysteria':'hysteria','xdrive':'xdrive'}


def json_object(value):
    result=json.loads(value)
    if not isinstance(result,dict):
        raise ValueError('Expected a JSON object')
    check_tls_verification(result)
    return result


def boolean(value):
    if str(value).lower() in ('1','true','yes','on'):
        return True
    if str(value).lower() in ('0','false','no','off',''):
        return False
    raise ValueError('Invalid boolean parameter')


def check_tls_verification(value):
    if isinstance(value,dict):
        for key,item in value.items():
            if key.lower() in ('allowinsecure','tlsallowinsecure','insecure','skipcertverify','skip-cert-verify') and boolean(item):
                raise ValueError('Disabling TLS verification is not supported')
            if key.lower() in ('fp','fingerprint') and str(item).lower()=='unsafe':
                raise ValueError('Unsafe TLS fingerprint is not supported')
            check_tls_verification(item)
    elif isinstance(value,list):
        for item in value:
            check_tls_verification(item)


def transport_settings(network,q):
    names={'tcp':'tcpSettings','xhttp':'xhttpSettings','ws':'wsSettings','grpc':'grpcSettings',
           'httpupgrade':'httpupgradeSettings','kcp':'kcpSettings','hysteria':'hysteriaSettings','xdrive':'xdriveSettings'}
    name=names[network]
    raw=q.get(name.lower()) or (q.get('rawsettings') if network=='tcp' else None)
    settings=json_object(raw) if raw else {}
    if network=='tcp':
        if 'header' not in settings or 'headertype' in q:
            kind=q.get('headertype') or 'none'
            header={'type':kind}
            if kind=='http':
                request={'path':(q.get('path') or '/').split(',')}
                if q.get('host'):
                    request['headers']={'Host':[host.strip() for host in q['host'].split(',') if host.strip()]}
                header['request']=request
            settings['header']=header
    elif network in ('xhttp','ws','httpupgrade'):
        settings.setdefault('path','/')
        for key in ('path','host'):
            if q.get(key):settings[key]=q[key]
        if q.get('headers'):settings['headers']=json_object(q['headers'])
        if network=='xhttp':
            settings.setdefault('mode','auto')
            if q.get('mode'):settings['mode']=q['mode']
            if q.get('extra'):settings['extra']=json_object(q['extra'])
        elif q.get('ed'):
            early_data=int(q['ed'])
            if early_data<0:raise ValueError('Invalid early data size')
            settings['path']+=('&' if '?' in settings['path'] else '?')+'ed='+str(early_data)
    elif network=='grpc':
        for source,target in [('servicename','serviceName'),('authority','authority')]:
            value=q.get(source) or (q.get('path') if source=='servicename' else q.get('host'))
            if value:settings[target]=value
        if q.get('mode'):
            if q['mode'] not in ('gun','multi'):raise ValueError('Unsupported gRPC mode')
            settings['multiMode']=q['mode']=='multi'
        elif 'multimode' in q:settings['multiMode']=boolean(q['multimode'])
        for target in ('idle_timeout','health_check_timeout','initial_windows_size'):
            value=q.get(target) or q.get(target.replace('_',''))
            if value:settings[target]=int(value)
        if 'permit_without_stream' in q:settings['permit_without_stream']=boolean(q['permit_without_stream'])
        if q.get('user_agent'):settings['user_agent']=q['user_agent']
    elif network=='kcp':
        for target in ('mtu','tti','uplinkCapacity','downlinkCapacity','cwndMultiplier','maxSendingWindow'):
            if q.get(target.lower()):settings[target]=int(q[target.lower()])
        # These legacy fields are ignored by this core; masks use finalmask instead.
        header=settings.get('header') or {}
        if not isinstance(header,dict):raise ValueError('Invalid mKCP header')
        if q.get('headertype') not in (None,'','none') or q.get('seed') or settings.get('seed') or header.get('type','none')!='none':
            raise ValueError('Legacy mKCP header and seed are no longer supported; use finalmask')
    elif network=='hysteria':
        settings.setdefault('version',2)
        if q.get('version'):settings['version']=int(q['version'])
        if q.get('auth'):settings['auth']=q['auth']
        if q.get('udpidletimeout'):settings['udpIdleTimeout']=int(q['udpidletimeout'])
    elif network=='xdrive':
        for target in ('service','remoteFolder'):
            if q.get(target.lower()):settings[target]=q[target.lower()]
        if q.get('secrets'):
            settings['secrets']=json.loads(q['secrets'])
            if not isinstance(settings['secrets'],list) or not all(isinstance(item,str) for item in settings['secrets']):
                raise ValueError('Invalid XDrive secrets')
    return name,settings

def extract_uris(payload):
    text=payload.decode("utf-8-sig").strip()
    if "vless://" in text.lower():
        return re.findall(r"vless://[^\s<\"']+", text,re.IGNORECASE)
    try:
        obj=json.loads(text)
        if isinstance(obj,dict):
            for key in ("proxies","servers","outbounds"):
                if key in obj: raise ValueError("JSON proxy configurations need conversion; not silently supported")
    except json.JSONDecodeError: pass
    compact="".join(text.split())
    compact+= "="*((-len(compact))%4)
    try: decoded=base64.urlsafe_b64decode(compact).decode("utf-8-sig")
    except Exception as e: raise ValueError("Unknown subscription encoding") from e
    uri=re.findall(r"vless://[^\s<\"']+", decoded,re.IGNORECASE)
    if not uri: raise ValueError("Subscription contained no vless:// URLs")
    return uri

def parse_vless(uri):
    parsed=urlsplit(uri)
    if parsed.scheme.lower()!="vless" or not parsed.hostname or not parsed.port or not parsed.username or parsed.password is not None:
        raise ValueError("Invalid VLESS URL")
    q={k.lower():v[-1] for k,v in parse_qs(parsed.query,keep_blank_values=True).items()}
    check_tls_verification(q)
    net=TRANSPORT_ALIASES.get((q.get("type") or q.get("net") or "tcp").lower())
    if net is None:raise ValueError("Unsupported VLESS transport")
    security=(q.get("security") or "none").lower()
    if security not in ('none','tls','reality'):raise ValueError('Unsupported transport security')
    if security=='reality' and net not in ('tcp','xhttp','grpc'):
        raise ValueError('REALITY only supports RAW, XHTTP and gRPC')
    if net=='hysteria' and security!='tls':
        raise ValueError('The Hysteria transport requires TLS')
    users={"id":unquote(parsed.username),"encryption":q.get("encryption") or "none"}
    if q.get("flow"):users["flow"]=q["flow"]
    stream={"network":net,"security":security}
    if security=='reality':
        if not q.get('pbk'):raise ValueError('Missing REALITY public key')
        reality={"show":False,"fingerprint":q.get("fp") or "chrome",
                 "serverName":q.get("sni") or q.get("servername") or parsed.hostname,
                 "publicKey":q["pbk"],"shortId":q.get("sid", ""),"spiderX":q.get("spx") or "/"}
        if q.get('pqv'):reality['mldsa65Verify']=q['pqv']
        stream['realitySettings']=reality
    elif security=='tls':
        tls={'serverName':q.get('sni') or q.get('servername') or parsed.hostname,
             'fingerprint':q.get('fp') or 'chrome'}
        if q.get('alpn'):
            tls['alpn']=[value.strip() for value in q['alpn'].split(',') if value.strip()]
        for source,target in [('ech','echConfigList'),('pcs','pinnedPeerCertSha256'),('vcn','verifyPeerCertByName'),
                              ('minversion','minVersion'),('maxversion','maxVersion')]:
            if q.get(source):tls[target]=q[source]
        if q.get('curvepreferences'):tls['curvePreferences']=[value.strip() for value in q['curvepreferences'].split(',') if value.strip()]
        stream['tlsSettings']=tls
    name,settings=transport_settings(net,q)
    stream[name]=settings
    if q.get('fm'):stream['finalmask']=json_object(q['fm'])
    node={"protocol":"vless","settings":{"vnext":[{"address":parsed.hostname,"port":parsed.port,
                                                      "users":[users]}]},"streamSettings":stream}
    if q.get('mux'):node['mux']=json_object(q['mux'])
    if net=='xdrive':
        if users['encryption']=='none':raise ValueError('XDrive requires VLESS encryption')
        node.setdefault('mux',{'enabled':True,'concurrency':8,'xudpConcurrency':8,'xudpProxyUDP443':'allow'})
    return node

class SubscriptionRedirects(HTTPRedirectHandler):
    max_redirections=3

    def __init__(self, allow_http):
        super().__init__()
        self.allow_http=allow_http

    def redirect_request(self, request, fp, code, message, headers, new_url):
        validate_subscription_url(new_url,self.allow_http)
        if urlsplit(request.full_url).scheme=='https' and urlsplit(new_url).scheme!='https':
            raise ValueError('Subscription redirect must preserve HTTPS')
        return super().redirect_request(request,fp,code,message,headers,new_url)


def validate_subscription_url(url,allow_http=False):
    parsed=urlsplit(url)
    if parsed.scheme not in (('https','http') if allow_http else ('https',)) or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Invalid subscription URL or transport')
    if parsed.port is not None and not 1<=parsed.port<=65535:
        raise ValueError('Invalid subscription port')


def fetch_subscription(url,allow_http=False):
    validate_subscription_url(url,allow_http)
    opener=build_opener(SubscriptionRedirects(allow_http))
    with opener.open(Request(url,headers={"User-Agent":"v2rayN/7.0"}),timeout=10) as response:
        body=response.read(2_000_001)
    if len(body)>2_000_000:
        raise ValueError('Subscription response is too large')
    return body


def load_subscription(url, expected=None, allow_http=False):
    body=fetch_subscription(url,allow_http)
    nodes=[]
    for uri in extract_uris(body):
        try: node=parse_vless(uri)
        except ValueError: continue
        nodes.append(node)
    if not nodes:raise ValueError('Subscription has no supported VLESS node')
    expected=TRANSPORT_ALIASES.get(expected,expected)
    return next((node for node in nodes if node['streamSettings']['network']==expected),nodes[0])

def inbound(name,port):
    return {"tag":name,"listen":"0.0.0.0","port":port,"protocol":"tunnel",
            "settings":{"allowedNetwork":"tcp,udp","followRedirect":True},
            "streamSettings":{"sockopt":{"tproxy":"tproxy"}}}
def httpproxy(name,port):
    return {"tag":name,"listen":"127.0.0.1","port":port,"protocol":"http",
            "settings":{"allowTransparent":False}}

def build(primary,backup):
    outbounds=[]
    for name,node in (("primary",primary),("backup",backup)):
        node=(node or {"protocol":"blackhole","settings":{"response":{"type":"none"}}}).copy()
        node["tag"]=name
        outbounds.append(node)
    outbounds.append({"tag":"direct","protocol":"freedom","settings":{}})
    return {"log":{"loglevel":"warning"},
      "inbounds":[inbound("tp",12345),inbound("tb",12346),inbound("td",12347),
                  httpproxy("hp",18081),httpproxy("hb",18082)],
      "outbounds":outbounds,
      "routing":{"domainStrategy":"AsIs","rules":[
         {"type":"field","inboundTag":["tp","hp"],"outboundTag":"primary"},
         {"type":"field","inboundTag":["tb","hb"],"outboundTag":"backup"},
         {"type":"field","inboundTag":["td"],"outboundTag":"direct"}]}}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subscriptions',type=pathlib.Path,required=True)
    parser.add_argument('--output',type=pathlib.Path,default=ROOT/'config/runtime/config.json')
    parser.add_argument('--allow-http',action='store_true')
    args=parser.parse_args()
    secrets=json.loads(args.subscriptions.read_text(encoding="utf-8"))
    runtime=args.output
    old={}
    if runtime.exists(): old=json.loads(runtime.read_text())
    nodes=[]
    for tag,expected in (("primary","tcp"),("backup","xhttp")):
        try:
            node=load_subscription(secrets[tag],expected,args.allow_http)
            stream=node['streamSettings']
            print(tag+": subscription retrieved, valid "+stream['network']+"/"+stream['security']+" VLESS")
        except Exception as e:
            print(tag+": subscription unavailable",file=sys.stderr)
            node=next((x for x in old.get("outbounds",[]) if x.get("tag")==tag and x.get("protocol")=="vless"),None)
            if node: print(tag+": preserving last valid cached profile",file=sys.stderr)
            else: print(tag+": no cached profile; using blackhole until valid subscription arrives",file=sys.stderr)
        nodes.append(node)
    config=build(*nodes)
    runtime.parent.mkdir(parents=True,exist_ok=True)
    tmp=runtime.with_suffix(".tmp")
    tmp.write_text(json.dumps(config,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.chmod(tmp,0o600)
    tmp.replace(runtime)
    print("ready:",sum(bool(x) for x in nodes),"valid VLESS outbound(s)")
if __name__=="__main__": main()

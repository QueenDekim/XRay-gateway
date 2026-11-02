"""Build Xray configuration from VLESS subscription URLs without unsafe TLS bypass."""
import argparse, base64, json, os, pathlib, re, sys
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen
ROOT=pathlib.Path(__file__).resolve().parents[1]

def extract_uris(payload):
    text=payload.decode("utf-8-sig").strip()
    if text.lower().startswith("vless://") or "vless://" in text:
        return re.findall(r"vless://[^\s<\"']+", text)
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
    uri=re.findall(r"vless://[^\s<\"']+", decoded)
    if not uri: raise ValueError("Subscription contained no vless:// URLs")
    return uri

def parse_vless(uri):
    parsed=urlsplit(uri)
    if parsed.scheme.lower()!="vless" or not parsed.hostname or not parsed.port or not parsed.username:
        raise ValueError("Invalid VLESS URL")
    q={k.lower():v[-1] for k,v in parse_qs(parsed.query,keep_blank_values=True).items()}
    net=q.get("type",q.get("net","tcp")).lower()
    if net not in ("tcp","xhttp"): raise ValueError("Only TCP and XHTTP supported, got "+net)
    if q.get("security","").lower()!="reality": raise ValueError("Security must be REALITY")
    if not q.get("pbk"): raise ValueError("Missing REALITY public key")
    users={"id":unquote(parsed.username),"encryption":q.get("encryption","none")}
    if q.get("flow"): users["flow"]=q["flow"]
    reality={"show":False,"fingerprint":q.get("fp","chrome"),
             "serverName":q.get("sni",q.get("servername","")),
             "publicKey":q["pbk"],"shortId":q.get("sid",""),
             "spiderX":q.get("spx","/")}
    stream={"network":net,"security":"reality","realitySettings":reality}
    if net=="xhttp":
        x={"path":q.get("path","/"),"mode":q.get("mode","auto")}
        if q.get("host"): x["host"]=q["host"]
        if q.get("extra"):
            try: x["extra"]=json.loads(q["extra"])
            except Exception as e: raise ValueError("Invalid xhttp extra JSON") from e
        stream["xhttpSettings"]=x
    else:
        stream["tcpSettings"]={"header":{"type":q.get("headertype","none")}}
    return {"protocol":"vless","settings":{"vnext":[{"address":parsed.hostname,"port":parsed.port,
                                                     "users":[users]}]},
            "streamSettings":stream}

def load_subscription(url, expected, allow_http=False):
    if not url.startswith("https://"):
        if not allow_http or not url.startswith('http://'):
            raise ValueError('Subscription transport must use HTTPS')
    with urlopen(Request(url,headers={"User-Agent":"v2rayN/7.0"}), timeout=15) as resp:
        body=resp.read(2_000_000)
    for uri in extract_uris(body):
        try: node=parse_vless(uri)
        except ValueError: continue
        if node["streamSettings"]["network"]==expected:
            return node
    raise ValueError("Subscription has no valid "+expected+"+REALITY node")

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
            print(tag+": subscription retrieved, valid "+expected+"+REALITY")
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

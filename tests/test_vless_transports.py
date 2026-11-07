import base64
import json
from pathlib import Path
import sys
import unittest
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway'),str(ROOT/'scripts')]
from render import parse_vless,load_subscription

KEY=base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip('=')


def uri(network='tcp',security='tls',address='127.0.0.1',**parameters):
    query={'type':network,'security':security,'sni':'example.org',**parameters}
    return 'vless://00000000-0000-0000-0000-000000000001@'+address+':443?'+urlencode(query)


def transport_cases():
    cases=[]
    for network in ('tcp','xhttp','ws','grpc','httpupgrade','kcp','hysteria','xdrive'):
        settings={}
        if network=='grpc':settings={'serviceName':'relay','mode':'multi','authority':'example.org'}
        if network in ('xhttp','ws','httpupgrade'):settings={'path':'/relay/','host':'example.org'}
        if network=='xdrive':settings={'service':'local','remoteFolder':'/tmp/xray-vless-transport-test','encryption':'mlkem768x25519plus.native.0rtt.'+KEY}
        for security in ('tls','none','reality'):
            if security=='reality' and network not in ('tcp','xhttp','grpc'):continue
            if network=='hysteria' and security!='tls':continue
            query=settings|({'pbk':KEY,'sid':'aabb'} if security=='reality' else {})
            cases.append((network+'/'+security,uri(network,security,**query)))
    return cases


class VlessTransportTests(unittest.TestCase):
    def test_every_supported_vless_transport_and_security(self):
        for label,source in transport_cases():
            with self.subTest(label=label):
                node=parse_vless(source);network,security=label.split('/')
                self.assertEqual(node['streamSettings']['network'],network)
                self.assertEqual(node['streamSettings']['security'],security)
                self.assertEqual(node['settings']['vnext'][0]['users'][0]['id'],'00000000-0000-0000-0000-000000000001')

    def test_xhttp_tls_keeps_fronting_parameters(self):
        source=uri('xhttp',address='cdn.example.org',host='cdn.example.org',path='/api/v1/relay/',mode='auto',fp='firefox',
                   alpn='h2,http/1.1',sni='sni.example.org')
        stream=parse_vless(source)['streamSettings']
        self.assertEqual(stream['tlsSettings'],{'serverName':'sni.example.org','fingerprint':'firefox','alpn':['h2','http/1.1']})
        self.assertEqual(stream['xhttpSettings'],{'path':'/api/v1/relay/','host':'cdn.example.org','mode':'auto'})
        self.assertNotIn('realitySettings',stream)

    def test_aliases_none_and_empty_export_values(self):
        for alias,canonical in [('raw','tcp'),('splithttp','xhttp'),('websocket','ws'),('mkcp','kcp')]:
            with self.subTest(alias=alias):self.assertEqual(parse_vless(uri(alias))['streamSettings']['network'],canonical)
        stream=parse_vless(uri('xhttp','none',path='',mode=''))['streamSettings']
        self.assertEqual(stream,{'network':'xhttp','security':'none','xhttpSettings':{'path':'/','mode':'auto'}})
        self.assertEqual(parse_vless(uri(address='[::1]',encryption=''))['settings']['vnext'][0]['users'][0]['encryption'],'none')

    def test_security_constraints_and_certificate_verification(self):
        for source in [uri('ws','reality',pbk=KEY),uri('httpupgrade','reality',pbk=KEY),uri(security='xtls'),
                       uri('hysteria','none'),
                       uri(allowInsecure='1'),uri(tlsAllowInsecure='true'),uri(fp='unsafe'),
                       uri('xhttp',extra=json.dumps({'downloadSettings':{'tlsSettings':{'allowInsecure':True}}})),
                       uri('xhttp',extra='[]')]:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):parse_vless(source)
        tls=parse_vless(uri(allowInsecure='false',pcs='aa'*32,vcn='example.org',ech='config'))['streamSettings']['tlsSettings']
        self.assertNotIn('allowInsecure',tls)
        self.assertEqual(tls['pinnedPeerCertSha256'],'aa'*32)
        self.assertEqual(tls['verifyPeerCertByName'],'example.org')
        self.assertEqual(tls['echConfigList'],'config')

    def test_transport_parameters_and_finalmask(self):
        raw=parse_vless(uri(headerType='http',path='/a,/b',host='127.0.0.1'))['streamSettings']['tcpSettings']
        self.assertEqual(raw['header']['request']['path'],['/a','/b'])
        ws=parse_vless(uri('ws',path='/socket?token=x',ed='2048',headers='{"X-Test":"value"}'))['streamSettings']['wsSettings']
        self.assertEqual(ws['path'],'/socket?token=x&ed=2048')
        self.assertEqual(ws['headers'],{'X-Test':'value'})
        grpc=parse_vless(uri('grpc',serviceName='a/b',mode='multi',authority='edge.example',idle_timeout='30'))['streamSettings']['grpcSettings']
        self.assertEqual(grpc,{'serviceName':'a/b','multiMode':True,'authority':'edge.example','idle_timeout':30})
        kcp=parse_vless(uri('kcp',mtu='1350',tti='20',uplinkCapacity='12',fm='{"udp":[]}'))['streamSettings']
        self.assertEqual(kcp['kcpSettings'],{'mtu':1350,'tti':20,'uplinkCapacity':12})
        self.assertEqual(kcp['finalmask'],{'udp':[]})
        with self.assertRaises(ValueError):parse_vless(uri('kcp',seed='obsolete'))

    def test_native_settings_preserve_complex_transports(self):
        extra={'xmux':{'maxConnections':1},'downloadSettings':{'network':'xhttp','security':'tls','tlsSettings':{'serverName':'download.example'}}}
        self.assertEqual(parse_vless(uri('xhttp',extra=json.dumps(extra)))['streamSettings']['xhttpSettings']['extra'],extra)
        self.assertEqual(parse_vless(uri('hysteria',auth='transport-password'))['streamSettings']['hysteriaSettings'],{'version':2,'auth':'transport-password'})
        source=uri('xdrive',encryption='mlkem768x25519plus.native.0rtt.'+KEY,xdriveSettings='{"service":"local","remoteFolder":"/tmp/relay","concurrency":4}')
        node=parse_vless(source)
        self.assertEqual(node['streamSettings']['xdriveSettings']['concurrency'],4)
        self.assertTrue(node['mux']['enabled'])

    def test_removed_or_non_vless_transports_are_rejected(self):
        for network in ('http','h2','h3','quic','masque','invalid'):
            with self.subTest(network=network):
                with self.assertRaises(ValueError):parse_vless(uri(network))

    def test_cli_import_can_use_other_transports(self):
        from unittest.mock import patch
        with patch('render.fetch_subscription',return_value=base64.b64encode(uri('ws').encode())):
            self.assertEqual(load_subscription('https://example.org/sub/token','tcp')['streamSettings']['network'],'ws')

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock,Mock,patch

import test_panel
from controller import Controller,list_address,routeros
from router_service import RouterService

ROOT=Path(__file__).resolve().parents[1]


class DomainLists(unittest.TestCase):
    def test_api_mixed_domains_preserve_names_and_never_resolve_before_export(self):
        panel=test_panel.PanelTest();panel.setUp();self.addCleanup(panel.tearDown)
        headers=panel.auth()
        status,result,_=panel.request('/api/ip-lists/add',{'name':'Names and addresses','addresses':
            'WWW.Example.COM\nwww.example.com.\nexample.com\n1.1.1.7/24\n2606:4700:4700::1111\nпример.рф'},headers)
        self.assertEqual(status,200);item=result['list']
        self.assertEqual(item['addresses'],['1.1.1.0/24','2606:4700:4700::1111','example.com','WWW.Example.COM','xn--e1afmkfd.xn--p1ai'])
        other=Controller(panel.root)
        try:self.assertIn(item,other.ip_lists())
        finally:other.db.close()
        with patch('socket.getaddrinfo',side_effect=AssertionError('Application must not resolve list domains')):
            script=routeros({'list_key':item['id'],'destinations':'\n'.join(item['addresses'])},[])
        for family in ('ip','ipv6'):
            for domain in item['addresses'][2:]:self.assertIn(f'/{family} firewall address-list add list=XRAY-DEST-{item["id"]} address={domain} ',script)
        self.assertEqual(panel.request('/api/routeros',{'list_id':item['id']},headers)[0],200)

    def test_domain_validation_rejects_urls_wildcards_invalid_ips_and_commands(self):
        for value in ('bad-ip','http://example.com','*.example.com','example.com:443','example..com','example.com..',
                      '999.999.999.999','-bad.com','bad-.com','x.com/24','a'*64+'.com','x.com"; /quit','x.$bad.com','_sip.example.com'):
            with self.subTest(value=value),self.assertRaises(ValueError):list_address(value)

    def test_domain_only_routes_and_dns_cleanup_are_scoped_and_idempotent(self):
        key='list_123456abcdef';script=routeros({'list_key':key},['example.com','EXAMPLE.COM.'])
        self.assertIn('/ip route add',script);self.assertIn('/tool netwatch add',script)
        for family in ('ip','ipv6'):
            self.assertEqual(script.count(f'/{family} firewall address-list add list=XRAY-DEST-{key} address=example.com '),1)
            self.assertLess(script.index(f'/{family} firewall address-list remove [find list=XRAY-DEST-{key} dynamic=no]'),
                            script.index(f'/{family} firewall address-list remove [find list=XRAY-DEST-{key}]'))

    def test_cli_accepts_domain_names_in_text_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'mixed.txt';output=Path(directory)/'list.rsc'
            source.write_text('1.1.1.1\nwww.example.com # keep this name\n',encoding='utf-8')
            result=subprocess.run([sys.executable,str(ROOT/'scripts/build_routeros.py'),'--destinations',str(source),
                '--gateway','192.168.50.20','--host','192.168.50.10','--source','192.168.50.100/32','--output',str(output)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('address=www.example.com ',output.read_text(encoding='utf-8'))

    def test_import_logs_omit_only_number_comments_and_keep_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            controller=Mock();controller.directory=Path(directory);controller.settings.return_value={'source':'192.168.50.0/24'}
            for fail in (False,True):
                service=RouterService(controller);client=Mock();sftp=MagicMock();client.open_sftp.return_value=sftp;service.connect=lambda:client
                stream=sftp.open.return_value.__enter__.return_value;logs=[]
                def execute(client,command,log):
                    for line in ['#line 1','#line 42','/ip firewall address-list add address=example.com','# Keep ordinary comments']:
                        log(line)
                    if fail:
                        log('failure: invalid value (line 12 column 7)');raise ValueError('Import failed')
                    body=stream.write.call_args.args[0].decode();marker=re.search(r':put "(XG-OK-[a-f0-9]+)"',body)[1]
                    return marker+'\n'
                service.execute=execute
                if fail:
                    with self.assertRaises(ValueError):service.import_script('# test',logs.append)
                    self.assertIn('failure: invalid value (line 12 column 7)',logs)
                else:service.import_script('# test',logs.append)
                self.assertNotIn('#line 1',logs);self.assertNotIn('#line 42',logs)
                self.assertIn('/ip firewall address-list add address=example.com',logs)
                self.assertIn('# Keep ordinary comments',logs);sftp.remove.assert_called_once()

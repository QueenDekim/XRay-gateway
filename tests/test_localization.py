import http.client
import json
from pathlib import Path
import re
import sys
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway'),str(ROOT/'scripts')]
from panel import Panel
from localization import translate_message
from version import build_info


class LocalizationTests(unittest.TestCase):
    def test_version_and_catalog_are_available_before_login(self):
        server=__import__('http.server',fromlist=['ThreadingHTTPServer']).ThreadingHTTPServer(('127.0.0.1',0),Panel)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            for path in ['/api/version','/locales.json','/locales.js','/i18n.js']:
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
                connection.request('GET',path);response=connection.getresponse();raw=response.read()
                self.assertEqual(response.status,200,path)
                if path=='/api/version':
                    info=json.loads(raw);self.assertRegex(info['version'],r'^1\.0-[0-9a-f]{7}$')
                    self.assertEqual(info['url'],'https://github.com/QueenDekim/XRay-gateway/tree/'+info['version'])
                if path=='/locales.js':self.assertTrue(raw.startswith(b'window.XrayMessages = '))
                connection.close()
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
            connection.request('GET','/api/state',headers={'Accept-Language':'en'})
            response=connection.getresponse();self.assertEqual(response.status,401)
            self.assertEqual(json.loads(response.read())['error'],'Sign in required.')
            connection.close()
        finally:server.shutdown();server.server_close()

    def test_api_localization_preserves_invalid_input_and_limits(self):
        self.assertEqual(translate_message('Неверный логин или пароль.','en-US'),'Invalid username or password.')
        self.assertEqual(translate_message('Некорректный IPv4, IPv6 или CIDR: имя','en'),'Invalid IPv4, IPv6 or CIDR: имя')
        self.assertEqual(translate_message('check_interval: допустимо целое число от 5 до 3600.','en'),'check_interval: enter an integer from 5 to 3600.')
        self.assertEqual(translate_message('custom user name','en'),'custom user name')

    def test_static_translation_catalog_is_complete(self):
        from html.parser import HTMLParser
        catalog=json.loads((ROOT/'gateway/web/locales.json').read_text(encoding='utf-8'))
        class Keys(HTMLParser):
            def handle_starttag(inner,tag,attributes):
                for key,value in attributes:
                    if key in ('data-i18n','data-i18n-aria'):self.assertIn(value,catalog)
        Keys().feed((ROOT/'gateway/web/index.html').read_text(encoding='utf-8'))
        for source,target in catalog.items():
            self.assertTrue(target,source)
            self.assertEqual(sorted(re.findall(r'\{\d+\}',source)),sorted(re.findall(r'\{\d+\}',target)),source)

    def test_build_revision_override_is_checked(self):
        self.assertEqual(build_info('f'*40)['version'],'1.0-fffffff')
        with self.assertRaises(ValueError):build_info('unsafe/ref')

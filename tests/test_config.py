import importlib.util
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("render",ROOT/"scripts"/"render.py")
render=importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)

class ConfigTest(unittest.TestCase):
    def test_url_parsing_tcp(self):
        u="vless://00000000-0000-0000-0000-000000000000@example.org:443?type=tcp&security=reality&pbk=pub&sid=aa&sni=www.example.com&fp=chrome"
        obj=render.parse_vless(u)
        self.assertEqual(obj["streamSettings"]["network"],"tcp")
        self.assertEqual(obj["streamSettings"]["realitySettings"]["publicKey"],"pub")

    def test_url_parsing_xhttp(self):
        u="vless://00000000-0000-0000-0000-000000000000@example.org:443?type=xhttp&security=reality&pbk=pub&path=%2Fab&mode=auto"
        obj=render.parse_vless(u)
        self.assertEqual(obj["streamSettings"]["xhttpSettings"]["path"],"/ab")

    def test_base64_subscription(self):
        import base64
        data="vless://test@example.org:443?type=tcp\n".encode()
        self.assertEqual(len(render.extract_uris(base64.b64encode(data))),1)

    def test_safe_fallback(self):
        cfg=render.build(None,None)
        self.assertEqual(cfg["outbounds"][0]["protocol"],"blackhole")
        self.assertEqual(cfg["outbounds"][1]["protocol"],"blackhole")
        self.assertEqual(cfg["outbounds"][2]["protocol"],"freedom")
        self.assertEqual(len(cfg["inbounds"]),5)

    def test_scoped_routeros_generator(self):
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as directory:
            target=pathlib.Path(directory)
            (target/'destinations.txt').write_text('1.1.1.1\n')
            subprocess.run([__import__('sys').executable,str(ROOT/'scripts/build_routeros.py'),
                '--destinations',str(target/'destinations.txt'),'--gateway','192.168.50.20',
                '--host','192.168.50.10','--source','192.168.50.0/24','--output',str(target/'import.rsc')],check=True,capture_output=True)
            script=(target/'import.rsc').read_text()
            self.assertIn('src-address=192.168.50.0/24',script)
            self.assertIn('/tool netwatch enable',script)
            self.assertIn('disabled=yes comment=XRAY-GW-ROUTE',script)

if __name__=="__main__": unittest.main()

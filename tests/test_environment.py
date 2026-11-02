import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway'),str(ROOT/'scripts')]
from bootstrap import initialize_accounts
from controller import Controller, configuration, atomic_json, routeros
from environment import network_defaults, ingress_interface, service_port
from accounts import password_matches


class DeploymentTests(unittest.TestCase):
    def test_fresh_controller_needs_no_cached_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            controller=Controller(directory)
            self.assertEqual(controller.list_profiles(),[])
            def candidate(profiles):
                path=Path(directory)/'candidate.json';atomic_json(path,configuration(profiles));return path
            controller.validate=candidate
            controller.initialize()
            self.assertTrue(controller.config.is_file())
            self.assertEqual(configuration([])['outbounds'][0]['tag'],'direct')
            controller.db.close()

    def test_first_admin_uses_secret_file_and_restart_preserves_password(self):
        with tempfile.TemporaryDirectory() as directory:
            secret=Path(directory)/'password';secret.write_text('a-test-password\n')
            with patch.dict(os.environ,{'ADMIN_USERNAME':'owner','ADMIN_PASSWORD_FILE':str(secret)}):
                self.assertTrue(initialize_accounts(directory))
                original=(Path(directory)/'auth.json').read_bytes()
                secret.write_text('changed-password')
                self.assertFalse(initialize_accounts(directory))
                self.assertEqual((Path(directory)/'auth.json').read_bytes(),original)

    def test_missing_bootstrap_secret_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'ADMIN_PASSWORD_FILE':str(Path(directory)/'absent')}):
            with self.assertRaises(RuntimeError):initialize_accounts(directory)

    def test_network_defaults_and_netwatch_port_follow_environment(self):
        with patch.dict(os.environ,{'XRAY_LAN_CIDR':'172.19.8.0/22','GATEWAY_IP':'172.19.8.50',
                                    'DOCKER_HOST_IP':'172.19.8.20','ROUTER_LAN_INTERFACE':'lan-vlan20',
                                    'HEALTH_PORT':'19080','DEFAULT_CLIENT_CIDR':'172.19.9.0/24'}):
            values=network_defaults()
            self.assertEqual(values['source'],'172.19.9.0/24')
            script=routeros({},['1.1.1.1'])
            for text in ['gateway=172.19.8.50@main','src-address=172.19.9.0/24','in-interface=lan-vlan20','port=19080']:
                self.assertIn(text,script)

    def test_invalid_nft_interface_and_port_are_rejected(self):
        with patch.dict(os.environ,{'XRAY_INGRESS_INTERFACE':'eth0";drop'}):
            with self.assertRaises(ValueError):ingress_interface()
        with patch.dict(os.environ,{'PANEL_PORT':'10085'}):
            with self.assertRaises(ValueError):service_port('PANEL_PORT',8080)

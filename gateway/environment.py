"""Validated deployment defaults shared by the supervisor and script generator."""
import ipaddress
import os
import re


def lan_cidr():
    network = ipaddress.IPv4Network(os.environ.get('XRAY_LAN_CIDR', '192.168.50.0/24'), strict=False)
    if network.prefixlen == 0:
        raise ValueError('XRAY_LAN_CIDR must identify a local network')
    return str(network)


def network_defaults():
    lan = lan_cidr()
    interface = os.environ.get('ROUTER_LAN_INTERFACE', 'bridge')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,40}', interface):
        raise ValueError('Invalid ROUTER_LAN_INTERFACE')
    return {
        'gateway': str(ipaddress.IPv4Address(os.environ.get('GATEWAY_IP', '192.168.50.20'))),
        'host': str(ipaddress.IPv4Address(os.environ.get('DOCKER_HOST_IP', '192.168.50.10'))),
        'source': str(ipaddress.IPv4Network(os.environ.get('DEFAULT_CLIENT_CIDR', lan), strict=False)),
        'interface': interface,
        'local_networks': os.environ.get('LOCAL_NETWORKS', lan),
    }


def ingress_interface():
    interface = os.environ.get('XRAY_INGRESS_INTERFACE', 'eth0')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', interface):
        raise ValueError('Invalid XRAY_INGRESS_INTERFACE')
    return interface


def service_port(name, default):
    value = int(os.environ.get(name, str(default)))
    if not 1024 <= value <= 65535:
        raise ValueError(f'{name} must be between 1024 and 65535')
    reserved = {10085, 12347, *range(12345, 12445), *range(18081, 18181)}
    if value in reserved:
        raise ValueError(f'{name} conflicts with an internal Xray port')
    return value

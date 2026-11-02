"""Create deployment files without changing the host network or starting containers."""
import argparse
import getpass
import ipaddress
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def validate(values):
    network = ipaddress.IPv4Network(values['LAN_SUBNET'], strict=False)
    if network.prefixlen == 0:
        raise ValueError('LAN_SUBNET must identify a local network')
    addresses = [ipaddress.IPv4Address(values[key]) for key in ('LAN_GATEWAY', 'GATEWAY_IP', 'DOCKER_HOST_IP')]
    if len(set(addresses)) != 3 or any(address not in network or address in (network.network_address, network.broadcast_address) for address in addresses):
        raise ValueError('Use three distinct usable LAN addresses for router, gateway and Docker host')
    if values.get('LAN_DRIVER', 'macvlan') not in ('macvlan', 'ipvlan'):
        raise ValueError('LAN_DRIVER must be macvlan or ipvlan')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', values['LAN_PARENT']):
        raise ValueError('Invalid LAN_PARENT interface')
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not args.env_file.exists():
        if args.check:
            parser.error('The environment file does not exist; copy .env.example first')
        args.env_file.write_bytes((ROOT / '.env.example').read_bytes())
        print(f'Created {args.env_file}. Set your network addresses, then run this command again.')
        return
    values = {}
    for line in args.env_file.read_text(encoding='utf-8').splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    validate(values)
    if args.check:
        print('Network configuration is valid')
        return
    path = ROOT / 'secrets/admin_password'
    if path.exists():
        print('Password file already exists; preserved')
        return
    password = getpass.getpass('Administrator password (8-1024 characters): ')
    if not 8 <= len(password) <= 1024 or password != getpass.getpass('Repeat password: '):
        raise SystemExit('Password length is invalid or the passwords do not match')
    path.parent.mkdir(exist_ok=True)
    with path.open('x', encoding='utf-8') as output:
        output.write(password + '\n')
    os.chmod(path, 0o600)
    print('Deployment files are ready. Start with docker compose up -d --build.')


if __name__ == '__main__':
    main()

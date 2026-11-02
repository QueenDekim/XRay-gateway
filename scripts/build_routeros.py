"""Generate a scoped RouterOS import without connecting to a router."""
import argparse
import ipaddress
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'gateway'), str(ROOT / 'scripts')]
from controller import routeros


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destinations', required=True, type=Path)
    parser.add_argument('--gateway', required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--interface', default='bridge')
    parser.add_argument('--local-networks', default='')
    parser.add_argument('--list-id', default='manual')
    parser.add_argument('--list-name', default='manual')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    addresses = []
    for raw in args.destinations.read_text(encoding='utf-8-sig').splitlines():
        value = raw.partition('#')[0].strip()
        if value:
            addresses.append(str(ipaddress.ip_network(value, strict=False)))
    script = routeros({'gateway':args.gateway, 'host':args.host, 'source':args.source,
                      'interface':args.interface, 'local_networks':args.local_networks,
                      'list_key':args.list_id, 'list_name':args.list_name}, addresses)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(script+'\n', encoding='utf-8')
    print(f'Wrote {args.output}')


if __name__ == '__main__':
    main()

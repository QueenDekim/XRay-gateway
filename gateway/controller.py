"""Persistent profiles and measured Xray traffic, without a Docker socket."""
import copy
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import sqlite3
import subprocess
import threading
import time
import uuid
from urllib.parse import urlsplit

from render import parse_vless, fetch_subscription, extract_uris, inbound, httpproxy, TRANSPORT_ALIASES
from environment import network_defaults, service_port


def address_sort_key(value):
    network = ipaddress.ip_network(value, strict=False)
    return network.version, int(network.network_address), network.prefixlen


def address_network(value):
    if '%' in value:
        raise ValueError('Адрес должен быть без идентификатора интерфейса.')
    return ipaddress.ip_network(value, strict=False)


def address_text(network):
    return str(network.network_address) if network.prefixlen == network.max_prefixlen else str(network)


def ports(profile):
    return 12344 + profile['slot'], 18080 + profile['slot']


def configuration(profiles):
    cfg = {'log': {'loglevel': 'warning'}, 'stats': {},
           'api': {'tag': 'api', 'services': ['StatsService']},
           'policy': {'system': {'statsOutboundUplink': True, 'statsOutboundDownlink': True}},
           'inbounds': [], 'outbounds': [], 'routing': {'domainStrategy': 'AsIs', 'rules': []}}
    for p in profiles:
        tag = p['id']
        tp, hp = ports(p)
        cfg['inbounds'] += [inbound('tp_' + tag, tp), httpproxy('hp_' + tag, hp)]
        node = copy.deepcopy(p['node'])
        node['tag'] = tag
        cfg['outbounds'].append(node)
        cfg['routing']['rules'].append({'type': 'field', 'inboundTag': ['tp_' + tag, 'hp_' + tag], 'outboundTag': tag})
    cfg['inbounds'] += [inbound('td', 12347), {'tag': 'api-in', 'listen': '127.0.0.1', 'port': 10085,
                      'protocol': 'tunnel', 'settings': {'address': '127.0.0.1'}}]
    cfg['outbounds'].append({'tag': 'direct', 'protocol': 'freedom', 'settings': {}})
    cfg['routing']['rules'] += [{'type': 'field', 'inboundTag': ['td'], 'outboundTag': 'direct'},
                              {'type': 'field', 'inboundTag': ['api-in'], 'outboundTag': 'api'}]
    return cfg


def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def resolve_profile_source(source,preferred_network=None,preferred_security=None):
    if source.lower().startswith('vless://'):
        try:
            return parse_vless(source)
        except (ValueError,TypeError):
            raise ValueError('Некорректная VLESS-ссылка. Проверьте транспорт, защиту и параметры подключения.') from None
    if not source.lower().startswith(('https://','http://')):
        raise ValueError('Укажите VLESS URI или HTTP/HTTPS-ссылку подписки.')
    try:
        payload=fetch_subscription(source,allow_http=True)
    except Exception:
        raise ValueError('Не удалось загрузить подписку. Проверьте ссылку и доступность сервера.') from None
    try:
        uris=extract_uris(payload)
    except (ValueError,UnicodeError):
        raise ValueError('В подписке нет поддерживаемого профиля VLESS.') from None
    nodes=[]
    for uri in uris:
        try:
            nodes.append(parse_vless(uri))
        except (ValueError,TypeError):
            continue
    if not nodes:
        raise ValueError('В подписке нет поддерживаемого профиля VLESS.')
    preferred_network=TRANSPORT_ALIASES.get(preferred_network,preferred_network)
    matches=[node for node in nodes if node['streamSettings']['network']==preferred_network]
    return next((node for node in matches if node['streamSettings']['security']==preferred_security),matches[0] if matches else nodes[0])


class Controller:
    def __init__(self, directory='/data', binary='/usr/local/bin/xray'):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.config = self.directory / 'config.json'
        self.binary = binary
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.db = sqlite3.connect(self.directory / 'panel.sqlite', check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS documents (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        os.chmod(self.directory / 'panel.sqlite', 0o600)
        self.profiles = self.load('profiles', None)
        if self.profiles is None:
            old = json.loads(self.config.read_text()) if self.config.exists() else {'outbounds': []}
            self.profiles = []
            for n in old.get('outbounds', []):
                if n.get('protocol') != 'vless':
                    continue
                slot = len(self.profiles) + 1
                if slot >= 3:
                    slot += 1
                self.profiles.append({'id': n['tag'], 'name': n['tag'].capitalize(), 'slot': slot,
                    'priority': len(self.profiles) + 1, 'enabled': True, 'node': n})
            self.save('profiles', self.profiles)
        self.stats = self.load('stats', {})
        self.health = {}
        self.history = []
        self.last_sample = time.time()
        self.stats_error = None
        self.applying = False
        self.revision = int(self.load('revision', 1))

    def load(self, key, default):
        row = self.db.execute('SELECT value FROM documents WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def save(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO documents VALUES (?,?)', (key, json.dumps(value)))
        self.db.commit()

    def list_profiles(self):
        with self.lock:
            return copy.deepcopy(sorted(self.profiles, key=lambda p: (p['priority'], p['slot'])))

    def settings(self):
        with self.lock:
            defaults = {'revision':1, **network_defaults(),
                'probe_url':os.environ.get('PROBE_URL', 'https://www.gstatic.com/generate_204'),
                'check_interval':max(5, int(os.environ.get('CHECK_INTERVAL', '10'))),
                'fail_threshold':max(1, int(os.environ.get('FAIL_THRESHOLD', '3'))),
                'recover_threshold':max(1, int(os.environ.get('RECOVER_THRESHOLD', '2')))}
            return defaults | self.load('settings', {})

    def change_settings(self, data):
        with self.lock:
            current = self.settings()
            if int(data.get('revision', -1)) != current['revision']:
                raise ValueError('Настройки изменились. Обновите страницу.')
            updated = current | {k:v for k,v in data.items() if k in current and k != 'revision'}
            try:
                for key in ('gateway', 'host'):
                    updated[key] = str(ipaddress.IPv4Address(updated[key]))
                updated['source'] = str(ipaddress.IPv4Network(updated['source'], strict=False))
                if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,40}', updated['interface']):
                    raise ValueError()
                if not isinstance(updated['local_networks'], str) or len(updated['local_networks']) > 4096:
                    raise ValueError()
                networks = {ipaddress.IPv4Network(v, strict=False) for v in re.split(r'[\s,;]+', updated['local_networks'].strip()) if v}
                if any(n.prefixlen == 0 for n in networks):
                    raise ValueError()
                updated['local_networks'] = '\n'.join(str(n) for n in sorted(networks, key=lambda n:(int(n.network_address), n.prefixlen)))
            except (ValueError, TypeError):
                raise ValueError('Проверьте IPv4-адреса, подсеть, LAN-интерфейс и локальные сети.') from None
            try:
                url = urlsplit(updated['probe_url'])
                if len(updated['probe_url']) > 2048 or any(c.isspace() or not c.isprintable() for c in updated['probe_url']) or url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
                    raise ValueError()
                url.port
            except (ValueError, TypeError):
                raise ValueError('Укажите HTTPS URL проверки без логина, пароля и фрагмента.') from None
            for key, low, high in [('check_interval',5,3600), ('fail_threshold',1,100), ('recover_threshold',1,100)]:
                try:
                    if isinstance(updated[key], bool) or str(updated[key]).strip() != str(int(updated[key])):
                        raise ValueError()
                    updated[key] = int(updated[key])
                    if not low <= updated[key] <= high:
                        raise ValueError()
                except (ValueError, TypeError):
                    raise ValueError(f'{key}: допустимо целое число от {low} до {high}.') from None
            updated['revision'] += 1
            self.save('settings', updated)
            self.wake.set()
            return copy.deepcopy(updated)

    def ip_lists(self, defaults=()):
        with self.lock:
            lists = self.load('ip_lists', None)
            if lists is None:
                addresses = []
                for value in defaults:
                    try:
                        network = address_network(value)
                        if network.is_global:
                            addresses.append(address_text(network))
                    except ValueError:
                        continue
                lists = [{'id': 'project', 'name': 'Из проекта', 'version': 1,
                          'addresses': sorted(set(addresses), key=address_sort_key)}] if addresses else []
                self.save('ip_lists', lists)
            return copy.deepcopy(lists)

    def change_ip_list(self, action, data, defaults=()):
        with self.lock:
            lists = self.ip_lists(defaults)
            current = next((item for item in lists if item['id'] == data.get('id')), None)
            if action != 'add':
                if current is None:
                    raise ValueError('IP-список не найден')
                if int(data.get('version', -1)) != current['version']:
                    raise ValueError('Список изменился. Обновите страницу')
            if action == 'delete':
                lists.remove(current)
            else:
                name = str(data.get('name', '')).strip()
                if not 1 <= len(name) <= 80:
                    raise ValueError('Название должно содержать от 1 до 80 символов')
                if any(item['id'] != data.get('id') and item['name'].casefold() == name.casefold() for item in lists):
                    raise ValueError('Список с таким названием уже существует')
                raw = data.get('addresses', '')
                if not isinstance(raw, str):
                    raise ValueError('Адреса должны быть текстом')
                addresses = set()
                for line in raw.lstrip('\ufeff').splitlines():
                    for value in re.split(r'[\s,;]+', line.partition('#')[0].strip()):
                        if not value:
                            continue
                        try:
                            network = address_network(value)
                        except ValueError:
                            raise ValueError('Некорректный IPv4, IPv6 или CIDR: ' + value[:80]) from None
                        addresses.add(address_text(network))
                        if len(addresses) > 5000:
                            raise ValueError('Максимум 5000 адресов в списке')
                if action == 'add':
                    if len(lists) >= 100:
                        raise ValueError('Максимум 100 IP-списков')
                    current = {'id': 'list_' + uuid.uuid4().hex[:12], 'version': 0}
                    lists.append(current)
                current.update(name=name, version=current['version'] + 1,
                    addresses=sorted(addresses, key=address_sort_key))
            self.save('ip_lists', lists)
            return copy.deepcopy(current) if action != 'delete' else None

    def validate(self, profiles):
        candidate = self.directory / 'candidate.json'
        atomic_json(candidate, configuration(profiles))
        result = subprocess.run([self.binary, 'run', '-test', '-c', str(candidate)], capture_output=True, timeout=15)
        if result.returncode:
            raise ValueError('Xray отклонил конфигурацию. Проверьте VLESS URI и параметры транспорта.')
        return candidate

    def xray_pid(self):
        for p in Path('/proc').glob('[0-9]*/cmdline'):
            try:
                args = p.read_bytes().split(b'\0')
                if args and args[0].endswith(b'/xray') and b'run' in args and b'-test' not in args:
                    return int(p.parent.name)
            except (OSError, ValueError):
                pass
        return None

    def restart(self):
        pid = self.xray_pid()
        if pid is not None:
            os.kill(pid, signal.SIGTERM)
        until = time.monotonic() + 25
        while time.monotonic() < until:
            if self.xray_pid() != pid and self.ready():
                return
            time.sleep(0.3)
        raise RuntimeError('Xray не запустился после применения конфигурации.')

    def ready(self):
        try:
            with socket.create_connection(('127.0.0.1', 10085), timeout=0.4):
                return True
        except OSError:
            return False

    def initialize(self):
        candidate = self.validate(self.profiles)
        if not self.config.exists() or json.loads(self.config.read_text()) != json.loads(candidate.read_text()):
            if self.config.exists():
                old = self.config.read_bytes()
                (self.directory / 'config-before-panel.json').write_bytes(old)
                os.chmod(self.directory / 'config-before-panel.json', 0o600)
            candidate.replace(self.config)
        else:
            candidate.unlink(missing_ok=True)

    def change(self, action, data, identifier=None):
        try:
            revision=int(data.get('revision', -1))
        except (ValueError,TypeError):
            raise ValueError('Список уже изменился. Обновите страницу и повторите действие.') from None
        with self.lock:
            if revision != self.revision:
                raise ValueError('Список уже изменился. Обновите страницу и повторите действие.')
            profiles = self.list_profiles()
            current = next((p for p in profiles if p['id'] == identifier), None)
            if action != 'add' and current is None:
                raise ValueError('Профиль не найден.')
            if action != 'delete':
                name = str(data.get('name', '')).strip()
                if not 1 <= len(name) <= 80:
                    raise ValueError('Название должно содержать от 1 до 80 символов.')
                try:
                    priority = int(data.get('priority', 10))
                except (ValueError,TypeError):
                    raise ValueError('Некорректные приоритет или состояние профиля.') from None
                if not 1 <= priority <= 1000 or not isinstance(data.get('enabled', True), bool):
                    raise ValueError('Некорректные приоритет или состояние профиля.')
                uri = str(data.get('uri', '')).strip()
                preferred=current['node']['streamSettings']['network'] if current else None
                preferred_security=current['node']['streamSettings'].get('security','none') if current else None
        # Subscription requests must not block statistics, probes or other panel readers.
        if action != 'delete':
            node = resolve_profile_source(uri,preferred,preferred_security) if uri else copy.deepcopy(current['node']) if current else None
            if node is None:
                raise ValueError('Укажите VLESS URI или ссылку подписки для нового профиля.')
        with self.lock:
            if revision != self.revision:
                raise ValueError('Список уже изменился. Обновите страницу и повторите действие.')
            if action != 'delete':
                if current is None:
                    used = {p['slot'] for p in profiles}
                    # Slots are never reused: old conntrack marks must not select a different profile.
                    slot = int(self.load('next_slot', max(used | {3}) + 1))
                    if slot > 100:
                        raise ValueError('Достигнут предел слотов профилей (100).')
                    current = {'id': 'p_' + uuid.uuid4().hex[:12], 'slot': slot}
                    profiles.append(current)
                current.update(name=name, priority=priority, enabled=data.get('enabled', True), node=node)
            else:
                profiles.remove(current)
            candidate = self.validate(profiles)
            previous = self.config.read_bytes()
            self.collect()
            self.applying = True
            try:
                candidate.replace(self.config)
                self.restart()
                next_slot = max({p['slot'] for p in profiles} | {int(self.load('next_slot', 4)) - 1}) + 1
                with self.db:
                    for key, value in [('profiles', profiles), ('next_slot', next_slot), ('revision', self.revision + 1)]:
                        self.db.execute('INSERT OR REPLACE INTO documents VALUES (?,?)', (key, json.dumps(value)))
                self.profiles = profiles
                self.revision += 1
                self.wake.set()
                self.health = {}
            except Exception:
                tmp = self.config.with_suffix('.restore')
                tmp.write_bytes(previous)
                os.chmod(tmp, 0o600)
                tmp.replace(self.config)
                self.restart()
                raise
            finally:
                self.applying = False

    def reset_profile_checks(self):
        with self.lock:
            stats=copy.deepcopy(self.stats)
            for profile in self.profiles:
                stats.setdefault(profile['id'],{}).update(checks=0,successful_checks=0)
            self.save('stats',stats)
            self.stats=stats

    def record_probe(self, identifier, ok, latency):
        with self.lock:
            s = self.stats.setdefault(identifier, {})
            s['checks'] = s.get('checks', 0) + 1
            s['successful_checks'] = s.get('successful_checks', 0) + int(ok)
            self.health[identifier] = {'ok': ok, 'latency_ms': round(latency * 1000, 1), 'checked_at': time.time()}

    def collect(self):
        with self.lock:
            try:
                result = subprocess.run([self.binary, 'api', 'statsquery', '--server=127.0.0.1:10085',
                    '-pattern', 'outbound>>>', '-reset'], capture_output=True, timeout=5, check=True)
                data = json.loads(result.stdout)
                now = time.time()
                elapsed = max(1, now - self.last_sample)
                rates = {}
                for item in data.get('stat', []):
                    parts = item['name'].split('>>>')
                    if len(parts) != 4 or parts[0] != 'outbound' or parts[3] not in ('uplink', 'downlink'):
                        continue
                    tag, direction, amount = parts[1], parts[3], max(0, int(item.get('value', 0)))
                    s = self.stats.setdefault(tag, {})
                    s[direction] = s.get(direction, 0) + amount
                    rates.setdefault(tag, {})[direction + '_bps'] = amount / elapsed
                for tag, s in self.stats.items():
                    s.update(uplink_bps=0, downlink_bps=0)
                    s.update(rates.get(tag, {}))
                self.save('stats', self.stats)
                self.last_sample, self.stats_error = now, None
                point = {'at': now, 'uplink_bps': sum(s.get('uplink_bps', 0) for s in self.stats.values()),
                         'downlink_bps': sum(s.get('downlink_bps', 0) for s in self.stats.values())}
                self.history = (self.history + [point])[-90:]
            except Exception:
                self.stats_error = 'Счётчики Xray временно недоступны.'

    def public_profiles(self):
        result = []
        for p in self.list_profiles():
            node = p['node']
            server = node.get('settings', {}).get('vnext', [{}])[0]
            result.append({k: p[k] for k in ('id', 'name', 'priority', 'enabled')} | {
                'address': server.get('address', ''), 'port': server.get('port', ''),
                'transport': node.get('streamSettings', {}).get('network', ''),
                'security': node.get('streamSettings', {}).get('security', 'none'),
                'stats': copy.deepcopy(self.stats.get(p['id'], {})), 'health': self.health.get(p['id'])})
        return result


def routeros(data, defaults, warnings=None):
    data = network_defaults() | data
    key = str(data.get('list_key', 'manual'))
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', key):
        raise ValueError('Некорректный идентификатор IP-списка.')
    name = str(data.get('list_name', key))
    if not 1 <= len(name) <= 80:
        raise ValueError('Некорректное название IP-списка.')
    # Display names may change; stable IDs own all RouterOS resources.
    name = ''.join(c if c.isprintable() else ' ' for c in name)
    label = '"' + ('XRAY-GW-' + name).replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$') + '"'
    destination_list, local_list, exempt_list = (f'XRAY-{kind}-{key}' for kind in ('DEST', 'LOCAL', 'EXEMPT'))
    policy_chain = f'XRAY-GW-POLICY-{key}'
    route_table = f'xray-gateway-{key}'
    route_comment = f'XRAY-GW-TABLE-{key}'
    entry_comment, local_comment, mark_comment, watch_comment = (f'XRAY-GW-{kind}-{key}' for kind in ('ROUTE', 'LOCAL', 'MARK', 'WATCH'))
    gateway = str(ipaddress.IPv4Address(data['gateway']))
    host = str(ipaddress.IPv4Address(data['host']))
    source = str(ipaddress.IPv4Network(data['source'], strict=False))
    interface = str(data['interface'])
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,40}', interface):
        raise ValueError('Некорректное имя интерфейса RouterOS.')
    local_networks = {ipaddress.IPv4Network(value) for value in (
        '0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
        '169.254.0.0/16', '172.16.0.0/12', '192.168.0.0/16', '224.0.0.0/4', '240.0.0.0/4')}
    local_text = str(data['local_networks'])
    if len(local_text) > 4096:
        raise ValueError('Слишком длинный список локальных сетей.')
    for value in re.split(r'[\s,;]+', local_text.strip()):
        if value:
            network = ipaddress.IPv4Network(value, strict=False)
            if network.prefixlen == 0:
                raise ValueError('Локальная сеть не должна быть маршрутом 0.0.0.0/0.')
            local_networks.add(network)
    raw = str(data.get('destinations', '')).strip()
    values = re.split(r'[\s,;]+', raw) if raw else defaults
    addresses, addresses6 = set(), set()
    for text in values:
        n = address_network(text)
        if n.is_global:
            (addresses if n.version == 4 else addresses6).add(n)
        elif raw:
            raise ValueError('Назначения должны быть публичными IPv4, IPv6 или подсетями.')
    if not 1 <= len(addresses) + len(addresses6) <= 5000:
        raise ValueError('Укажите от 1 до 5000 публичных IP-назначений.')
    lines = ['# Xray Gateway — RouterOS 7. Netwatch enables IPv4 routing when the gateway is healthy.',
       f'# Managed IP list ID: {key}',
       f'/tool netwatch remove [find comment={watch_comment}]',
       f'/ip firewall mangle remove [find comment={entry_comment}]',
       f'/ip firewall mangle remove [find comment={local_comment}]',
       f'/ip firewall mangle remove [find comment={mark_comment}]',
       f'/ip route remove [find comment={route_comment}]',
       f'/ip firewall address-list remove [find list={destination_list}]',
       f'/ip firewall address-list remove [find list={local_list}]',
       f'/ip firewall address-list remove [find list={exempt_list}]',
       f'/ipv6 firewall address-list remove [find list={destination_list}]']
    if addresses6:
        warning = 'IPv6-адреса выгружены в address-list. Маршрутизация IPv6 через VPN не настроена.'
        if warnings is not None:
            warnings.append(warning)
        lines.append('# IPv6 address-list only; IPv6 VPN routing is not configured.')
        lines += [f'/ipv6 firewall address-list add list={destination_list} address={n} comment={label}'
                  for n in ipaddress.collapse_addresses(sorted(addresses6, key=lambda n: (int(n.network_address), n.prefixlen)))]
    if not addresses:
        lines.append(f'/routing table remove [find name={route_table}]')
        return '\n'.join(lines)
    lines += [f':if ([:len [/routing table find name={route_table}]] = 0) do={{ /routing table add fib name={route_table} }}',
              f'/ip route add dst-address=0.0.0.0/0 gateway={gateway}@main routing-table={route_table} check-gateway=ping comment={route_comment}']
    lines += [f'/ip firewall address-list add list={exempt_list} address={address} comment={label}'
              for address in sorted({gateway, host})]
    lines += [f'/ip firewall address-list add list={local_list} address={n} comment={label}'
              for n in ipaddress.collapse_addresses(sorted(local_networks, key=lambda n: (int(n.network_address), n.prefixlen)))]
    # Includes public-addressed LANs as well as private VLANs. Inspect the router's
    # actual interface prefixes at import time, not the Docker host's addresses.
    lines += [':foreach addrId in=[/ip address find where disabled=no] do={',
       '    :local cidr [/ip address get $addrId address]',
       '    :local net [/ip address get $addrId network]',
       '    :local prefix [:pick $cidr ([:find $cidr "/"] + 1) [:len $cidr]]',
       '    :local subnet ($net . "/" . $prefix)',
       f'    :if ([:len [/ip firewall address-list find list={local_list} address=$subnet]] = 0) do={{',
       f'        /ip firewall address-list add list={local_list} address=$subnet comment={label}',
       '    }',
       '}']
    lines += [f'/ip firewall address-list add list={destination_list} address={n} comment={label}' for n in ipaddress.collapse_addresses(sorted(addresses, key=lambda n: (int(n.network_address), n.prefixlen)))]
    lines += [f'/ip firewall mangle add chain={policy_chain} action=return dst-address-list={local_list} comment={local_comment}',
       f'/ip firewall mangle add chain={policy_chain} action=mark-routing dst-address-list=!{local_list} new-routing-mark={route_table} passthrough=no comment={mark_comment}',
       f'/ip firewall mangle add chain=prerouting action=jump jump-target={policy_chain} in-interface={interface} src-address={source} src-address-list=!{exempt_list} dst-address-list={destination_list} dst-address-type=!local disabled=yes comment={entry_comment}',
       f'/tool netwatch add host={gateway} port={service_port("HEALTH_PORT", 18080)} type=http-get http-codes=200-299 interval=10s timeout=3s disabled=yes comment={watch_comment} up-script="/ip firewall mangle enable [find comment={entry_comment}]" down-script="/ip firewall mangle disable [find comment={entry_comment}]"',
       f'/tool netwatch enable [find comment={watch_comment}]',
       '# Emergency bypass (disable monitoring first):',
       f'# /tool netwatch disable [find comment={watch_comment}]',
       f'# /ip firewall mangle disable [find comment={entry_comment}]']
    return '\n'.join(lines)

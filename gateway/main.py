"""Container-local TPROXY supervisor and authenticated management panel."""
import copy
import http.server
import json
import os
import subprocess
import threading
import time
import urllib.request
from controller import Controller, ports
from panel import Panel
from environment import lan_cidr, ingress_interface, service_port
from bootstrap import initialize_accounts

LAN = lan_cidr()
PROBE = os.environ.get('PROBE_URL', 'https://www.gstatic.com/generate_204')
state = {'selected': 'direct', 'checks': {}, 'since': time.time(), 'last_error': None}
lock = threading.RLock()
controller = None
started = time.time()


def cmd(*argv, input=None, check=True):
    return subprocess.run(argv, input=input, text=True, check=check, capture_output=True)


def table(selected):
    profiles = controller.list_profiles()
    marks = {p['id']: 0x10 + p['slot'] for p in profiles} | {'direct': 0x13}
    destinations = {p['id']: ports(p)[0] for p in profiles} | {'direct': 12347}
    private = '0.0.0.0/8,10.0.0.0/8,100.64.0.0/10,127.0.0.0/8,169.254.0.0/16,172.16.0.0/12,192.168.0.0/16,224.0.0.0/4,240.0.0.0/4'
    lines = ['delete table ip xray_gw', 'table ip xray_gw {',
        ' chain prerouting { type filter hook prerouting priority mangle; policy accept;',
        f' iifname != "{ingress_interface()}" return', f' ip saddr != {LAN} return',
        f' ip daddr {LAN} return',
        f' ip daddr {{ {private} }} return', ' meta l4proto != { tcp, udp } return',
        f' ct mark 0 ct mark set {hex(marks.get(selected, 0x13))}']
    for tag, port in destinations.items():
        for proto in ('tcp', 'udp'):
            lines.append(f' ct mark {hex(marks[tag])} meta l4proto {proto} tproxy to :{port} meta mark set 0x1 accept')
    lines += [' ct mark != 0 drop', ' }', '}']
    return '\n'.join(lines) + '\n'


def switch(selected):
    result = cmd('nft', '-f', '-', input=table(selected), check=False)
    if result.returncode:
        raise RuntimeError('Не удалось применить nftables.')
    with lock:
        if state['selected'] != selected:
            print(f"[gateway] {state['selected']} -> {selected}", flush=True)
            state.update(selected=selected, since=time.time())
        state['last_error'] = None


def configure():
    if 'fwmark 0x1 lookup 100' not in cmd('ip', 'rule', 'show').stdout:
        cmd('ip', 'rule', 'add', 'fwmark', '1', 'table', '100')
    cmd('ip', 'route', 'replace', 'local', '0.0.0.0/0', 'dev', 'lo', 'table', '100')
    if cmd('nft', 'list', 'table', 'ip', 'xray_gw', check=False).returncode:
        cmd('nft', 'add', 'table', 'ip', 'xray_gw')
    switch('direct')


def probe(port, url=PROBE):
    proxy = urllib.request.ProxyHandler({'https': f'http://127.0.0.1:{port}', 'http': f'http://127.0.0.1:{port}'})
    begin = time.monotonic()
    try:
        with urllib.request.build_opener(proxy).open(urllib.request.Request(url, headers={'User-Agent': 'xray-gateway-check/2'}), timeout=6) as response:
            return response.status == 204, time.monotonic() - begin
    except Exception:
        return False, time.monotonic() - begin


def supervise():
    counts = {}
    last_revision = 0
    last_health_settings = None
    while True:
        controller.wake.clear()
        with controller.lock:
            profiles = controller.list_profiles()
            revision = controller.revision
            settings = controller.settings()
        health_settings = tuple(settings[key] for key in ('probe_url', 'check_interval', 'fail_threshold', 'recover_threshold'))
        if revision != last_revision:
            counts = {}
        elif health_settings != last_health_settings:
            for previous in counts.values():
                previous.update(successes=0, failures=0)
        last_health_settings = health_settings
        checks = {}
        for p in profiles:
            previous = counts.setdefault(p['id'], {'healthy': False, 'successes': 0, 'failures': 0})
            if p['enabled']:
                ok, elapsed = probe(ports(p)[1], settings['probe_url'])
                controller.record_probe(p['id'], ok, elapsed)
                previous['successes'] = previous['successes'] + 1 if ok else 0
                previous['failures'] = 0 if ok else previous['failures'] + 1
                if previous['successes'] >= settings['recover_threshold']:
                    previous['healthy'] = True
                if previous['failures'] >= settings['fail_threshold']:
                    previous['healthy'] = False
            else:
                previous.update(healthy=False, successes=0, failures=0)
            checks[p['id']] = copy.deepcopy(previous)
        chosen = next((p['id'] for p in profiles if p['enabled'] and checks[p['id']]['healthy']), 'direct')
        with controller.lock:
            if revision == controller.revision:
                with lock:
                    state['checks'] = checks
                if chosen != state['selected'] or last_revision != revision:
                    try:
                        switch(chosen)
                        last_revision = revision
                    except Exception:
                        with lock:
                            state['last_error'] = 'Не удалось переключить правила маршрутизации.'
        controller.collect()
        controller.wake.wait(settings['check_interval'])


def ensure_initial_core():
    # On the first migration, Compose may start Xray before initialize() replaces
    # the legacy config. Restart that process only if its API never appeared.
    for _ in range(50):
        if controller.ready():
            return
        if controller.xray_pid() is not None:
            time.sleep(2)
            if not controller.ready():
                try:
                    with controller.lock:
                        controller.restart()
                except Exception:
                    with lock:
                        state['last_error'] = 'Не удалось запустить API Xray после миграции.'
            return
        time.sleep(0.2)


def snapshot():
    with controller.lock:
        with lock:
            status = copy.deepcopy(state)
        return status | {'ready': controller.ready(), 'uptime': time.time() - started,
            'profiles': controller.public_profiles(), 'revision': controller.revision,
            'totals': {d: sum(s.get(d, 0) for s in controller.stats.values()) for d in ('uplink', 'downlink', 'uplink_bps', 'downlink_bps')},
            'direct': controller.stats.get('direct', {}), 'history': list(controller.history),
            'stats_error': controller.stats_error, 'applying': controller.applying,
            'stats_since': controller.load('stats_since', started)}


class Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/', '/health', '/status'):
            self.send_error(404)
            return
        with lock:
            data = json.dumps(state).encode()
        self.send_response(200 if controller.ready() else 503)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    directory = os.environ.get('DATA_DIR', '/data')
    panel_port, health_port = service_port('PANEL_PORT', 8080), service_port('HEALTH_PORT', 18080)
    if panel_port == health_port:
        raise ValueError('PANEL_PORT and HEALTH_PORT must differ')
    initialize_accounts(directory)
    controller = Controller(directory, os.environ.get('XRAY_BINARY', '/usr/local/bin/xray'))
    controller.initialize()
    if controller.load('stats_since', None) is None:
        controller.save('stats_since', time.time())
    configure()
    Panel.controller = controller
    Panel.snapshot = staticmethod(snapshot)
    for path in filter(None, os.environ.get('INVENTORY_FILES', '').split(os.pathsep)):
        try:
            Panel.defaults += [line.strip() for line in open(path) if line.strip() and not line.startswith('#')]
        except OSError:
            pass
    threading.Thread(target=supervise, daemon=True).start()
    threading.Thread(target=ensure_initial_core, daemon=True).start()
    threading.Thread(target=http.server.ThreadingHTTPServer((os.environ.get('HEALTH_BIND', '0.0.0.0'), health_port), Health).serve_forever, daemon=True).start()
    print(f'[gateway] management :{panel_port}, health :{health_port}', flush=True)
    http.server.ThreadingHTTPServer((os.environ.get('PANEL_BIND', '0.0.0.0'), panel_port), Panel).serve_forever()

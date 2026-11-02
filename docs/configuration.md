# Configuration reference

Copy `.env.example` to `.env`. Keep `.env` and `secrets/` outside version control.

| Variable | Purpose | Example/default |
| --- | --- | --- |
| `COMPOSE_PROJECT_NAME` | Isolates Compose resources | `xray-gateway` |
| `LAN_DRIVER` | Data-plane driver | `macvlan` or `ipvlan` |
| `LAN_PARENT` | Host LAN interface | `eth0` |
| `LAN_SUBNET` | IPv4 LAN and capture scope | `192.168.50.0/24` |
| `LAN_GATEWAY` | Router address | `192.168.50.1` |
| `GATEWAY_IP` | Reserved address of the gateway container | `192.168.50.20` |
| `DOCKER_HOST_IP` | Host address excluded from generated VPN rules | `192.168.50.10` |
| `DEFAULT_CLIENT_CIDR` | Initial RouterOS client or subnet | `LAN_SUBNET` |
| `LOCAL_NETWORKS` | Additional local networks, separated by spaces | `LAN_SUBNET` |
| `ROUTER_LAN_INTERFACE` | RouterOS ingress interface | `bridge` |
| `PANEL_PORT` | Panel HTTP port | `8080` |
| `HEALTH_PORT` | Health HTTP and generated Netwatch port | `18080` |
| `ADMIN_USERNAME` | Initial administrator login | `admin` |
| `PROBE_URL` | HTTPS URL that returns HTTP 204 | `https://www.gstatic.com/generate_204` |
| `CHECK_INTERVAL` | Seconds between checks | `10` |
| `FAIL_THRESHOLD` | Consecutive failures before marking a profile unhealthy | `3` |
| `RECOVER_THRESHOLD` | Consecutive successes before recovery | `2` |
| `XRAY_IMAGE` | Same core image for build-time validation and runtime | Pinned in `.env.example` |
| `GATEWAY_IMAGE` | Locally built application image name | `xray-gateway:local` |
| `PROXY_NETWORK` | Existing bridge network for `compose.proxy.yaml` | `reverse-proxy` |

`LAN_GATEWAY`, `GATEWAY_IP` and `DOCKER_HOST_IP` must be distinct usable addresses
in `LAN_SUBNET`. Ports must differ and must avoid internal Xray ports. The setup
checker validates the network addresses; the supervisor validates its listening
ports and ingress interface at startup.

## Runtime defaults and saved settings

The environment supplies the first values for routing and health checks. The
panel saves later edits in SQLite with a revision number. Saved values take
precedence over initial defaults. A changed network address requires edits to
both `.env` and the panel's routing settings.

Direct container deployments can set `DATA_DIR`, `XRAY_BINARY`,
`XRAY_INGRESS_INTERFACE`, `PANEL_BIND`, `HEALTH_BIND`, `ADMIN_PASSWORD_FILE` and
`INVENTORY_FILES`. Compose supplies the ingress interface and secret path.
`INVENTORY_FILES` accepts Linux path-separator-delimited files of initial IP
addresses; existing saved IP lists take precedence.

Do not publish the unencrypted panel or health endpoint to an untrusted network.
Use a restricted management network and terminate HTTPS at a reverse proxy.

# Deployment

## Host and network requirements

Use a Linux host with rootful Docker Engine and Compose 2.36+. The kernel must
support nftables, IPv4 policy routing, connection tracking and TPROXY. The
containers require `NET_ADMIN`; the gateway also requires `NET_RAW`.

The default macvlan network gives the gateway a LAN address. Your switch and
hypervisor must allow an additional MAC address on the host's physical port.
Docker Desktop, rootless Docker and cloud networks that block this traffic
cannot run this deployment unchanged. Use a Linux VM with a suitable network
interface in those environments. See Docker's [macvlan requirements](https://docs.docker.com/engine/network/drivers/macvlan/).

## Build from source

1. Copy `.env.example` to `.env`.
2. Set `LAN_PARENT` to the Linux interface connected to the router.
3. Set `LAN_SUBNET`, `LAN_GATEWAY`, `DOCKER_HOST_IP` and `GATEWAY_IP`.
4. Exclude `GATEWAY_IP` from the DHCP pool and verify that no device uses it.
5. Set the RouterOS LAN interface and the default client subnet.

Set local image names in `.env`:

```dotenv
GATEWAY_IMAGE=xray-gateway:local
UPDATER_IMAGE=xray-gateway-updater:local
```

Run:

```sh
python3 scripts/configure.py --check
python3 scripts/configure.py
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Compose builds the gateway and updater and pulls the pinned Xray core. The
updater mounts the Docker socket; review its [permissions](updates.md#docker-access)
before starting it.

The setup command writes `secrets/admin_password` with private permissions. The
gateway reads this file on first startup and stores a salted password hash in
`config/runtime/auth.json`. Later restarts preserve the account database.

Access the panel at `http://<GATEWAY_IP>:8080`. The health endpoint uses port
18080. Change both ports in `.env` if needed. Create a profile before directing
client traffic to the gateway.

## IPvlan alternative

Set `LAN_DRIVER=ipvlan` to use Docker's IPvlan L2 driver with the same address
settings. This driver shares the parent interface's MAC address. Your network
still needs to route the configured gateway IP to the host's physical port.

## Reverse proxy

A Docker host cannot reach its macvlan child through the parent interface.
Connect a containerized proxy through a separate bridge network:

```sh
docker network create reverse-proxy
```

Connect your proxy to that network and set `PROXY_NETWORK=reverse-proxy` in
`.env`. Start the combined configuration:

```sh
docker compose -f compose.yaml -f compose.proxy.yaml up -d --build
```

Point the proxy to `http://xray-gateway-panel:8080`, or your configured panel
port. Configure TLS on the proxy and restrict access to the panel. The extra
interface uses `eth1`; the data plane and default route remain on `eth0`.
Nginx Proxy Manager is one supported proxy, but the deployment does not require it.

Build from a Git checkout to record the source revision in the image. For an
exported source tree, set `SOURCE_REVISION` to the full commit SHA in `.env` or
the build environment. The build stops if it cannot resolve a source revision.

Use the same Compose file list for later updates, logs and shutdown commands.

## Existing installations

Back up runtime data before replacing deployment files. Translate your existing
addresses into `.env`, preserve the runtime directory and keep the same Xray
image version in both services. Stored panel settings override their initial
environment defaults. Review them after migration; changing a Compose address
does not rewrite stored RouterOS settings.

## Use a published image

After configuring the network and initial password, set this value in `.env`:

```dotenv
GATEWAY_IMAGE=ghcr.io/queendekim/xray-gateway:1.9.0
UPDATER_IMAGE=ghcr.io/queendekim/xray-gateway-updater:1.9.0
XRAY_IMAGE=ghcr.io/xtls/xray-core:26.10.21
```

Pull the gateway, updater and matching core, then start without a local build:

```sh
docker compose pull gateway xray updater
docker compose up -d --no-build
```

Keep XRAY_IMAGE pinned to the version used by the release. The published gateway
contains the validation executable; the separate Xray service handles traffic.
Pin `GATEWAY_IMAGE` and `UPDATER_IMAGE` to the same release. You can use full
release tags or image digests. Run `up` with `--no-build` for an image deployment,
including when you add the reverse-proxy override. See
[Releases](releases.md#container-publication) for tags and package visibility.

Follow [Operations](operations.md#manual-update) for manual upgrades and
[Updates](updates.md) for installation from the panel. The update worker
preserves your Compose file list, reserved LAN address and network aliases.

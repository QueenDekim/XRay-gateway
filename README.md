<p align="center">
  <img src=".github/assets/logo.png#gh-light-mode-only" alt="Xray Gateway logo" width="128" height="128" />
  <img src=".github/assets/logo-white.png#gh-dark-mode-only" alt="Xray Gateway logo" width="128" height="128" />
</p>
<div id="header" align="center"><img alt="GitHub last commit" src="https://img.shields.io/github/last-commit/QueenDekim/XRay-gateway"> <img alt="GitHub commit activity" src="https://img.shields.io/github/commit-activity/m/QueenDekim/XRay-gateway"><br> <img alt="GitHub top language" src="https://img.shields.io/github/languages/top/QueenDekim/XRay-gateway"> <a href="./LICENSE" target="_blank"> <img src="https://img.shields.io/github/license/QueenDekim/XRay-gateway"> </a></div>

# Xray Gateway

Xray Gateway routes selected IPv4 traffic from a RouterOS network through VLESS
profiles. A web panel manages profiles, IP lists, users and health checks.

Use a Linux Docker host connected to the client network. Configure the network
addresses and parent interface in `.env`; the project has no dependency on a
particular LAN, host name or reverse proxy. Docker Desktop and rootless Docker
do not provide the required macvlan data path.

## Features

- Profile priorities, health checks and automatic selection of a healthy route.
- Traffic counters, live charts and per-profile statistics.
- Mixed IPv4/IPv6 and domain lists, with direct RouterOS installation over SSH.
- Administrator and read-only accounts, avatars and two-factor authentication.
- Named API tokens with expiry, revocation and 2FA confirmation at creation.
- Separate page URLs, a sectioned API Wiki and updates with backup and rollback.
- Four interface styles, each with light and dark modes.

The transparent VPN path supports IPv4. IPv6 entries export to RouterOS address
lists; this version does not route IPv6 through the VPN. If no enabled profile
passes its health checks, the gateway uses the direct connection.

<details>
  <summary>Web themes</summary>

| Theme   | Screenshot                                                                   |
| ------- | ---------------------------------------------------------------------------- |
| Titan   | <img src=".github/assets/titan.png"   alt="Titan interface" width="640" />   |
| Paper   | <img src=".github/assets/paper.png"   alt="Paper interface" width="640" />   |
| Console | <img src=".github/assets/console.png" alt="Console interface" width="640" /> |
| Contour | <img src=".github/assets/circuit.png" alt="Contour interface" width="640" /> |

</details>

## Quick start

Requirements: Linux, rootful Docker Engine, Docker Compose 2.36 or newer, and
Python 3.12 or newer for the setup command. Reserve a free LAN address for the
gateway outside your DHCP pool.

```sh
git clone https://github.com/QueenDekim/XRay-gateway.git
cd XRay-gateway
cp .env.example .env
```

Edit `.env` for your network, then create the first administrator password:

```sh
python3 scripts/configure.py
docker compose up -d --build
docker compose ps
```

Open `http://<GATEWAY_IP>:<PANEL_PORT>`, sign in with `ADMIN_USERNAME` and the
password you entered, and add a VLESS profile. Add an IP list and install it
on RouterOS after checking the [routing instructions](docs/routeros.md).

## Documentation

The [documentation index](docs/README.md) covers installation, network drivers,
configuration, RouterOS preparation, panel/API use, backups and troubleshooting.
Read [deployment](docs/deployment.md) for source builds and prebuilt GHCR images,
and [updates](docs/updates.md) for installation, backups and rollback.
The panel also links to the [API reference](docs/api/README.md).

## NetLens

[NetLens](https://github.com/QueenDekim/NetLens) discovers domain addresses and
captures application connections on Windows. It has its own repository,
dependencies and releases. The optional `tools` Git submodule pins a NetLens
revision:

```sh
git submodule update --init tools
```

The gateway runs without the submodule. Import a NetLens `ips.txt` export through
the panel when you need its results in an IP list.

## Development and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for tests and contribution guidelines,
[SECURITY.md](SECURITY.md) for reporting vulnerabilities, and
[CHANGELOG.md](CHANGELOG.md) for changes.

Project code uses [Apache-2.0](LICENSE). Dependencies retain the licenses listed
in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Prebuilt Linux images: `ghcr.io/queendekim/xray-gateway`. See
[image deployment](docs/deployment.md#use-a-published-image) and
[release publication](docs/releases.md#container-publication).

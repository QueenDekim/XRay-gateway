# Troubleshooting

## The first start exits

Run `python3 scripts/configure.py --check`. Confirm that the secret file exists,
contains a password of at least eight characters and is readable by Docker.
Check `docker compose logs gateway xray`. A fresh installation creates an empty
profile store; it does not need a cached subscription or configuration file.

## The host cannot reach the panel

Check the panel from another LAN device. Macvlan isolates the host from its child
interface. For a proxy on the same host, use `compose.proxy.yaml` and the bridge
alias described in [deployment](deployment.md). A proxy that targets the macvlan
address can return HTTP 502 despite the panel working from a LAN client.

## The test website still shows the normal connection

Check the client's own VPN or proxy first. Resolve the website again and compare
its current destination addresses with the selected IP list. Check FastTrack,
the generated mangle counters, Netwatch and the gateway's active profile.

CT names and DNS snapshots do not define a permanent address range. CDNs can
change addresses or serve many domains on a shared IP. Include the addresses
needed by the test rather than assuming one historical lookup remains complete.

## Connections stall after routing

Verify that the gateway IP is unique and reachable, that `LAN_PARENT` is correct,
and that the hypervisor allows the chosen network driver. Inspect gateway logs
and the Xray health endpoint. Preserve the supplied `src_valid_mark` and reverse
path filtering sysctls; changing them can drop intercepted packets.

## An IPv6 destination bypasses the VPN

This release exports IPv6 lists but implements the transparent VPN path for
IPv4. Configure a separate IPv6 policy, or restrict the affected clients to an
IPv4 path for your test.

# RouterOS routing

## Prepare the router

Back up the RouterOS configuration. Check that the router can reach the gateway
IP, its health port and the client subnet. Reserve the gateway IP outside the
DHCP pool. Docker assigns the address; the container does not request a DHCP lease.

Review FastTrack before testing policy routing. FastTrack can bypass mangle
processing for established connections. Exclude the selected traffic from your
FastTrack rule, or disable FastTrack during a controlled test and restore your
intended policy afterwards. Check existing connection marks and policy routes
for conflicts. Test a single client before selecting the full LAN.

## Generate and import a list

Create an IP list in the panel. Open RouterOS, select that list, choose the client
or subnet and review local networks. Copy the script into a RouterOS 7 terminal.
The generator prepares commands; it does not connect to the router.

Each list owns its address lists, mangle rules, routing table, route and Netwatch
entry. Reimporting replaces that list's resources. Other generated lists remain
intact, including overlapping destination addresses. A stable list ID owns the
resources; changing the display name does not change ownership.

The script bypasses local destinations, host addresses, the gateway itself,
configured local networks and networks discovered from active router addresses.
A client source such as `192.168.50.0/24` selects LAN clients; destination bypass
rules keep local traffic out of the VPN.

Netwatch enables the generated route rule after a successful gateway HTTP check
and disables it when that check fails. A healthy gateway may still use direct
fallback when its VLESS profiles are unavailable.

## Generate from a file

```sh
python3 scripts/build_routeros.py \
  --destinations destinations.txt \
  --gateway 192.168.50.20 --host 192.168.50.10 \
  --source 192.168.50.100/32 --interface bridge \
  --local-networks 192.168.50.0/24 \
  --list-id streaming --list-name Streaming \
  --output build/streaming.rsc
```

Use public addresses or CIDRs, one per line. The generator accepts IPv4 and IPv6.
IPv6 entries export to `/ipv6 firewall address-list`; the script creates the VPN
policy for IPv4 traffic. Add an IPv6 routing policy if your network needs one.

## Remove generated resources

Match the stable list ID in the generated comments and names. Disable its mangle
entry and Netwatch before removing the corresponding route, table and address
lists. Preserve other IDs. The repository does not ship a global router cleanup
script because it cannot infer which existing rules you want to retain.

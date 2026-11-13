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

## Connect the panel

Open Settings → RouterOS as an administrator. Enter the SSH host, port and
service username. Choose a private key or password. Retrieve the host fingerprint
and compare it with a trusted SSH connection before saving. The panel tests the
connection and rejects subsequent connections if the server key changes.

Use a dedicated RouterOS account restricted to the gateway's source subnet.
Its group needs `ssh,ftp,read,write,test`: SFTP uploads temporary import files,
and the panel reads and changes routing, mangle, address lists and Netwatch.
RouterOS has no per-list write permission; the terminal has the privileges of
this account. Protect administrator accounts with 2FA.

Import the public key under `/user ssh-keys`. Paste the corresponding private
key into the panel; encrypted private keys also require their passphrase.
The panel marks saved credentials with a mask.
Blank credential fields preserve saved credentials only for the same host,
port, username and authentication method. The API never returns the private key,
passphrase or SSH password.

The panel encrypts SSH credentials in `config/runtime/routeros.json` with
`config/runtime/.encryption-key`. Include both in private backups. Restoring only
the encrypted file cannot recover the connection.

## Install and update a list

As an administrator, set the client subnet, LAN interface, gateway and bypass networks under Settings
→ Routing. Create an IP list and choose To RouterOS. Confirm the operation and
follow its log. The panel uploads a temporary script over SFTP, imports it over
SSH and removes the upload. Operations run one at a time; a busy list cannot be
edited or deleted until its operation ends.

Each list owns its address lists, mangle rules, routing table, route and Netwatch
entry. Reimporting replaces that list's resources. Other generated lists remain
intact, including overlapping destination addresses. A stable list ID owns the
resources; changing the display name does not change ownership.

An import can fail after changing some resources. Review the log and repeat
the operation after fixing the cause. RouterOS does not provide a transaction
covering these commands.

The script bypasses local destinations, host addresses, the gateway itself,
configured local networks and networks discovered from active router addresses.
A client source such as `192.168.50.0/24` selects LAN clients; destination bypass
rules keep local traffic out of the VPN.

Netwatch enables the generated route rule after a successful gateway HTTP check
and disables it when that check fails. A healthy gateway may still use direct
fallback when its VLESS profiles are unavailable.

## Interactive terminal and script export

Administrators can connect to an interactive SSH terminal on the RouterOS tab.
Opening the tab starts the connection. After a manual disconnect, choose Connect
to reconnect; switching tabs preserves that manual disconnect.
The terminal supports cursor keys, Ctrl-C, resizing and scrolling. Disconnect
when finished. Logging out closes that session's terminal. Idle terminals close
after five minutes; a terminal session lasts at most one hour. Opening another
terminal for the same user closes the previous one.

Use Script on that tab to generate commands for manual review or export.
Choose a list or enter destinations, then copy the generated script into a
RouterOS 7 terminal. Script generation does not change the router.

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

Use public addresses, CIDRs or domain names, one per line. The generator accepts
mixed entries. It sends domains as names to both IPv4 and IPv6 address lists,
without resolving them in the panel. RouterOS resolves the names and maintains
their dynamic entries using its DNS configuration.
IPv6 entries export to `/ipv6 firewall address-list`; the script creates the VPN
policy for IPv4 traffic. Add an IPv6 routing policy if your network needs one.

During replacement and deletion, the panel removes static DNS entries before
clearing the remaining dynamic entries. Operation logs omit the import's
`#line N` comments and retain commands and error messages.

## Remove generated resources

Delete a panel list and confirm removal. The panel removes that stable ID's
Netwatch entry, mangle rules, route, table and IPv4/IPv6 address lists. It deletes
the panel record after successful router cleanup. If SSH or cleanup fails, the
panel retains the list so you can retry. Other list IDs remain intact.

For resources created with the command-line generator, match the list ID in
comments and names. Disable its Netwatch and entry rule before removing the
corresponding route, table and address lists. Preserve other IDs.

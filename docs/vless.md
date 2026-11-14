# VLESS transports and security

Import a `vless://` URI or an HTTP/HTTPS subscription containing plain or Base64
VLESS links. Click Save and apply to download the subscription and open its selection dialog.
Use the checkboxes, names and priorities to choose what to import. Select one
entry when replacing an existing profile. The panel validates the resulting configuration with the
bundled Xray `26.10.21` before applying it.

## Transports

| Transport          | URI `type`           | Main URI parameters                                                                            |
| ------------------ | -------------------- | ---------------------------------------------------------------------------------------------- |
| RAW/TCP            | `tcp`, `raw`         | `headerType`, `host`, `path`                                                                   |
| XHTTP              | `xhttp`, `splithttp` | `path`, `host`, `mode`, `extra`                                                                |
| WebSocket          | `ws`, `websocket`    | `path`, `host`, `headers`, `ed`                                                                |
| gRPC               | `grpc`               | `serviceName`, `authority`, `mode=gun` or `mode=multi`                                         |
| HTTPUpgrade        | `httpupgrade`        | `path`, `host`, `headers`, `ed`                                                                |
| mKCP               | `kcp`, `mkcp`        | `mtu`, `tti`, `uplinkCapacity`, `downlinkCapacity`, `cwndMultiplier`, `maxSendingWindow`, `fm` |
| Hysteria transport | `hysteria`           | `version=2`, `auth`, `udpIdleTimeout`                                                          |
| XDrive             | `xdrive`             | `service`, `remoteFolder`, `secrets`, `xdriveSettings`                                         |

Hysteria here carries VLESS over the Hysteria transport; it requires TLS. XDrive
requires VLESS encryption and Mux. Include its encryption value in `encryption`;
the importer enables Mux unless the URI supplies a `mux` JSON object.

For advanced options, percent-encode the corresponding Xray settings object in
`tcpSettings` (or `rawSettings`), `xhttpSettings`, `wsSettings`, `grpcSettings`,
`httpupgradeSettings`, `kcpSettings`, `hysteriaSettings` or `xdriveSettings`.
These JSON parameters extend the share-link format. XHTTP `extra` and stream
`fm` accept percent-encoded JSON objects too.

The bundled core removed the old HTTP/2 (`http`, `h2`, `h3`) and QUIC transports.
Use an XHTTP link exported by your server for those configurations. MASQUE is
available to the MASQUE protocol, rather than VLESS. Legacy mKCP `seed` and
camouflage headers require an updated server link using `finalmask` (`fm`).

## Security

Use `security=tls`, `security=reality` or `security=none`. Omitted transport and
security values default to TCP and none. REALITY works with RAW/TCP, XHTTP and
gRPC. The core restricts unencrypted VLESS with `security=none` to private server
addresses or VLESS configurations that supply their own encryption.

TLS imports preserve `sni`, `fp`, comma-separated `alpn`, `ech`, `pcs` and `vcn`.
The SNI defaults to the server address and the fingerprint defaults to Chrome.
Certificate verification stays enabled. Use `pcs` for certificate SHA-256 pins
and `vcn` for verification names when your server requires those settings.

REALITY imports preserve `pbk`, `sid`, `sni`, `fp`, `spx` and `pqv`. The importer
also retains VLESS `encryption` and `flow`, including Vision, for core validation.

Example XHTTP/TLS link:

```text
vless://00000000-0000-0000-0000-000000000001@cdn.example.org:443?type=xhttp&security=tls&encryption=none&path=%2Frelay%2F&host=cdn.example.org&sni=sni.example.org&fp=firefox&alpn=h2%2Chttp%2F1.1
```

## Checks and references

Run `python scripts/check_vless_transports.py --image <gateway-image>` to validate
18 transport/security configurations with the image's Xray binary. This checks
configuration acceptance. A connection check also needs a compatible server and
valid credentials.

See the [Xray transport configuration](https://xtls.github.io/en/config/transport.html),
[VLESS share-link specification](https://github.com/XTLS/Xray-core/discussions/716)
and [transport definitions in the pinned core](https://github.com/XTLS/Xray-core/blob/v26.10.21/infra/conf/transport_internet.go).

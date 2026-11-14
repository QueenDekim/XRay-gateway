# Security policy

Report vulnerabilities through
[GitHub private vulnerability reporting](https://github.com/QueenDekim/XRay-gateway/security/advisories/new).
If that feature is unavailable, open an issue asking for a private contact
without including exploit details or credentials.

Include the affected revision, deployment mode, impact and a reproduction using
dummy data. Remove session cookies, passwords, subscription URLs, VLESS keys and
private captures before sharing logs.

The current release branch receives fixes. Run the panel and health endpoint on
a trusted management network, use HTTPS at the proxy and back up private runtime
data. The supervisor needs network administration capabilities inside its
container namespace. Review changes to Compose capabilities and network drivers
before applying them to a production host.

The optional updater mounts the Docker socket and can control the host through
Docker. The gateway and core do not mount it. Restrict panel administrators and
protect `.backups/`, runtime encryption keys and saved session files. See
[Update permissions](docs/updates.md#docker-access).

API tokens are bearer credentials. Use HTTPS and keep them out of URLs and logs.
The panel stores token hashes and shows each secret once. Revoke unused tokens
under your name → API. Account password, role and 2FA security changes invalidate
previous tokens.

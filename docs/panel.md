# Web panel and API

## Profiles and measured traffic

Add VLESS TCP+REALITY or XHTTP+REALITY profiles. Lower priority numbers win among
enabled healthy profiles. Adding, editing or deleting a profile validates a new
Xray configuration and restarts the core. Existing connections can close.

Paste a VLESS URI or an HTTP/HTTPS subscription URL in the profile form. When you
save a subscription URL, the panel imports one TCP/XHTTP profile with REALITY.
For an existing profile, it prefers a node with the current transport. Otherwise
it chooses the first supported node. Paste the URL again to import a later update.

The panel reads Xray outbound counters and keeps cumulative totals in SQLite.
Counters include probe traffic. The chart stores 90 samples in process memory;
a supervisor restart clears that chart history. Deleting a profile preserves its
contribution to cumulative totals.

Use Reset check counters on the Profiles page to clear successful and total
probe counts for the current profiles. Traffic totals and availability status
continue from their current values.

## IP lists and settings

IP lists accept mixed IPv4/IPv6 addresses and CIDRs, normalize networks and remove
duplicates. Import text files or paste a NetLens `ips.txt` export. Copy operations
include the full list.

Settings has Appearance, Routing, Checks, Users and Security tabs. Administrators
manage common settings and accounts. Operators manage profiles and IP lists,
generate scripts, choose appearance and change their password. Passwords require
8 to 1024 characters. The panel protects the last administrator and prevents
self-deletion.

Appearance offers Titan, Paper, Console and Contour. Each has a light/dark pair
and its own component layout and traffic chart. The browser stores the style and
color mode as independent preferences. The header sun/moon button changes color
mode without changing the style.

Choose Русский or English on the sign-in page or under Settings → Appearance.
The browser saves your language choice. Switching languages keeps unsaved form
values and updates labels, messages, chart captions and date formats.

The lower-left version link opens the matching GitHub tag. Versions use
`1.0-<short commit SHA>`; each repository uses its own seven-character SHA.
The container build records the source revision, so the panel can show it
without Git at runtime.

## HTTP API

The API uses JSON and a same-origin session cookie. Log in with
`POST /api/login` containing `username` and `password`. Read `GET /api/state` for
the CSRF token, then send that value in `X-CSRF-Token` on authenticated writes.

Read `GET /api/version` without signing in for the version, source revision and
tag URL. Send `Accept-Language: en` for English API errors; the default is Russian.

Send `POST /api/profiles/reset-checks` with an empty JSON object and the session's
CSRF token to reset profile probe counts.

| Endpoint | Operation |
| --- | --- |
| `GET /api/state` | Profiles, lists, statistics, settings and current account |
| `POST /api/logout` | End the session |
| `POST /api/profiles/add`, `/edit`, `/delete` | Change a profile using its revision |
| `POST /api/ip-lists/add`, `/edit`, `/delete` | Change a list using its version |
| `POST /api/routeros` | Generate a script from a list or explicit destinations |
| `POST /api/settings` | Save administrator settings using their revision |
| `POST /api/password` | Change the current user's password |
| `POST /api/users/add`, `/edit`, `/delete` | Manage accounts as an administrator |

API responses omit VLESS credentials and password hashes. Keep session cookies,
CSRF tokens and exported configuration files private. Account changes revoke
earlier sessions through a user revision check.

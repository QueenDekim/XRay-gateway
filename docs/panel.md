# Web panel and API

## Profiles and measured traffic

Add VLESS profiles with TLS, REALITY or no transport encryption. Lower priority numbers win among
enabled healthy profiles. Adding, editing or deleting a profile validates a new
Xray configuration and restarts the core. Existing connections can close.

Paste a VLESS URI or an HTTP/HTTPS subscription URL in the profile form and
click Save and apply. For a subscription, this opens a selection dialog after
the download. Check the profiles you want, edit their names and priorities,
then click Save and apply in the dialog. Cancel returns to the original form
without applying changes. To replace an existing profile, select one entry.

Profiles from the same subscription appear under a shared heading in Overview
and Profiles. You can name the group in the selection dialog. Each profile has
its own priority; grouping does not change route selection. Importing the same
subscription again updates matching group members and keeps their IDs, slots
and counters. Entries you leave unchecked stay as they are. A normal profile
edit keeps its group membership.

The panel reads plain and Base64 VLESS subscriptions, removes identical nodes
and reports how many unsupported entries it skipped. It keeps the reviewed
selection in your session for five minutes. Saving applies that selection in
one configuration validation and core restart. After the selection expires,
close the dialog and click Save and apply again to download a fresh copy.
The panel stores a group ID and name, not the subscription URL.

Read [VLESS transports](vless.md) for supported transports, URL parameters and
the combinations accepted by the bundled Xray core. Profile rows show both the
transport and security mode, such as `XHTTP / TLS` or `RAW/TCP / REALITY`.

The panel reads Xray outbound counters and keeps cumulative totals in SQLite.
Counters include probe traffic. The chart stores 90 samples in process memory;
a supervisor restart clears that chart history. Deleting a profile preserves its
contribution to cumulative totals.

Use Reset check counters on the Profiles page to clear successful and total
probe counts for the current profiles. Traffic totals and availability status
continue from their current values.

## IP lists and settings

IP lists accept mixed IPv4/IPv6 addresses, CIDRs and domain names. The panel
normalizes networks and removes duplicates, including case-insensitive domain
duplicates. Import text files or paste a NetLens export. Copy operations include
the full list. Enter hostnames such as `www.example.com`, without URL schemes,
ports or wildcard prefixes. Internationalized names use IDNA encoding.

As an administrator, use To RouterOS to install or replace a list after confirming the operation.
The panel shows the SSH import log. Deleting a list removes its owned router
resources before deleting the panel record. A failed cleanup leaves the record
available for retry. Configure the SSH connection first; see [RouterOS](routeros.md).

Settings has Routing, Checks, RouterOS and Users tabs. Administrators
manage common settings, router access, profiles, lists and accounts. Users with
the `operator` role have read-only access to shared data. They can view and copy
full lists; changing lists or profiles, resetting counters and writing to
RouterOS require an administrator. Users can change their own password,
avatar, display name, appearance and 2FA settings. Passwords require
8 to 1024 characters. The panel protects the last administrator and prevents
self-deletion.

Click your name to open personal settings: Profile, Appearance and Security.
Change your display name, upload a PNG, JPEG or WebP avatar up to 2 MB, or remove
it. The panel crops avatars to 256 × 256 pixels and strips image metadata.

Appearance offers Titan, Paper, Console and Contour. Each has a light/dark pair
and its own typography, navigation treatment and traffic chart. Profiles and IP
lists use compact rows in all four styles. Light surfaces use a pale accent tint.
Your account stores appearance and language preferences; the browser also keeps
them for the sign-in screen. The header sun/moon button changes color mode.

Choose Русский or English on the sign-in page or under your name → Appearance.
The browser saves your language choice. Switching languages keeps unsaved form
values and updates labels, messages, chart captions and date formats.

The lower-left version link opens the matching GitHub tag. Versions use
`MAJOR.MINOR.PATCH-<short commit SHA>`; each repository has its own version
sequence and seven-character SHA. See [Releases](releases.md) for bump rules.
The container build records the source revision, so the panel can show it
without Git at runtime.

## Two-factor authentication

Open your name → Security → Set up 2FA and enter your current password.
Scan the QR code with a TOTP authenticator, then enter its six-digit code to
enable protection. Save the ten recovery codes before leaving the page.
Each recovery code works once; the panel stores only their hashes.

At sign-in, enter your username and password, then choose Sign in. For an account
with 2FA, the panel opens a dialog for an authenticator or recovery code.
Canceling the dialog preserves your entered credentials. Accounts without 2FA
open the panel after the password check.
An accepted TOTP code cannot be reused. The panel limits attempts and expires
unfinished sign-ins after three minutes. Keep the server clock synchronized.

Disabling 2FA or generating replacement recovery codes requires your password
and a fresh code. Replacement codes invalidate the previous set. Security changes
revoke other sessions. If you lose both the authenticator and recovery codes,
use the local [administrator recovery command](operations.md#recover-administrator-access).

## HTTP API

The API uses JSON and a same-origin session cookie. Log in with
`POST /api/login` containing `username` and `password`. Read `GET /api/state` for
the CSRF token, then send that value in `X-CSRF-Token` on authenticated writes.

Read `GET /api/version` without signing in for the version, source revision and
tag URL. Send `Accept-Language: en` for English API errors; the default is Russian.

Send `POST /api/profiles/reset-checks` with an empty JSON object and the session's
CSRF token to reset profile probe counts.

Administrators can send `POST /api/profiles/preview` with `uri` to read a
subscription. The response contains a session-bound `token`, a `profiles` array
with IDs, names, endpoints, transports and security modes, a `skipped` count,
and `group` metadata. Existing group members also include their saved name
and priority.
Submit the same `uri`, `subscription_token` and an array of selected profile IDs
in `subscription_profiles` to `/api/profiles/add` or `/edit`, along with the normal
profile fields and revision. Send `subscription_options` as an object keyed
by selected profile ID, with `name` and integer `priority` (1 to 1000) for each
entry. Use `subscription_name` for the group heading. Add accepts several
selections; edit accepts one. Each reimport updates matching members by group
and node ID; it leaves unselected members untouched.
The token expires after five minutes, a successful save, or another preview in
the same session. A multi-profile URL without a selection returns HTTP 400.

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

A password login for a protected account returns `requires_2fa` and a `challenge`
without issuing a session. Complete it with `POST /api/login/2fa` using `challenge`
and `code`. Personal writes use `/api/account/profile`, `/api/account/avatar`, and
`/api/account/2fa/setup`, `/enable`, `/disable`, `/recovery`. The avatar endpoint
accepts base64 image bytes in `image`; an empty string removes the avatar.

`POST /api/routeros/apply` and `POST /api/ip-lists/delete` accept a list `id` and
`version`, and return HTTP 202 with a job `id`. Poll
`GET /api/routeros/jobs/<id>?cursor=<cursor>` for status and incremental log lines.
Statuses are `queued`, `running`, `done` and `error`; retain the returned cursor.
The panel keeps the last 30 jobs and up to 600 lines per job in process memory.

Administrators configure SSH through `GET/POST /api/routeros/config` and inspect
a host fingerprint through `POST /api/routeros/host-key`. Terminal endpoints
`/api/routeros/terminal/open`, `/input`, `/resize`, `/close` use POST;
`GET /api/routeros/terminal/<id>?cursor=<cursor>` returns base64 PTY output.
Terminal IDs belong to one user and one panel session.

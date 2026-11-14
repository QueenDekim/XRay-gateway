# Web panel and API

## Pages and navigation

Open `/overview`, `/profiles`, `/iplists`, `/routeros`, `/settings`, `/account`
or `/wiki`. Each URL returns its own page. Reload keeps the selected page;
settings tabs use fragments such as `/settings#updates` and `/account#security`.
The sign-in page returns you to the requested URL after authentication.

The panel encrypts active sessions on disk so restarts preserve signed-in
sessions until their 12-hour expiry. Logging out revokes the saved session.
Password and account security changes revoke earlier sessions.

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

Settings has Routing, Checks, RouterOS, Users and Updates tabs. Administrators
manage common settings, router access, profiles, lists and accounts. Users with
the `operator` role have read-only access to shared data. They can view and copy
full lists; changing lists or profiles, resetting counters and writing to
RouterOS require an administrator. Users can change their own password,
avatar, display name, appearance and 2FA settings. Passwords require
8 to 1024 characters. The panel protects the last administrator and prevents
self-deletion.

Click your name to open personal settings: Profile, Appearance, Security and API.
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

## Updates

The lower-left version area shows a newer release with an Update button for
administrators. Confirm installation in the panel dialog and follow the log
under Settings → Updates. Enable automatic installation there if you want
unattended updates within the current major version. See [Updates](updates.md)
for backups, rollback and Docker permissions.

## API tokens

Open your name → API to create a named token. Choose a lifetime from 1 to 365
days; the default is 90. With 2FA enabled, confirm each new token in the code
dialog. You can use an authenticator code or a single-use recovery code.

Copy the token from the result dialog. Closing it clears the full value; the
list shows its name, prefix and expiry. Revoke individual tokens from that list.
You can keep up to 20 active tokens. Tokens inherit your role, so a regular
user's token keeps read-only access to profiles, IP lists and RouterOS.

Password, role and 2FA security changes invalidate previously issued tokens.
Account deletion and expiry also end access. See [API tokens](api/tokens.md)
for the request format and token-management endpoints.

## HTTP API

Choose API Wiki in the sidebar to open `/wiki`. Each topic has a separate page:
authentication, profiles, lists, RouterOS, terminal, accounts, settings and
updates. The [Markdown API reference](api/README.md) provides the same request
and response examples outside the panel.

Use JSON requests with `Authorization: Bearer <token>` for integrations.
Bearer requests need no session cookie or CSRF header. The web panel retains
its session cookie and sends `X-CSRF-Token` for writes. Set `Accept-Language: en` for English errors; the default is Russian.

Read `GET /api/version` without signing in for the version, revision and tag
URL. Authenticated responses omit VLESS credentials and password hashes. Keep
session cookies, CSRF tokens and exported configuration private.

Quick endpoint index:

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

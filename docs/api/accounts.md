# Accounts and security

Passwords contain 8 to 1024 characters. Regular users manage their own accounts but cannot change shared settings, profiles, lists or RouterOS access.

Upload avatars as base64 PNG, JPEG or WebP, up to 2 MB. An empty string removes the avatar. The panel returns the TOTP secret only during setup and recovery codes only when generated.

## POST /api/account/profile

Role: `user`.

Change the current account’s display_name and preferences.

Request:

```json
{
  "display_name": "Operator",
  "preferences": {
    "language": "en",
    "design": "titan",
    "colorScheme": "dark"
  }
}
```

## POST /api/account/avatar

Role: `user`.

Save or remove the current avatar.

Request:

```json
{
  "image": "<base64 image bytes>"
}
```

## POST /api/password

Role: `user`.

Change the password after verifying the current password.

Request:

```json
{
  "current_password": "old-password",
  "password": "new-password"
}
```

## POST /api/account/2fa/setup

Role: `user`.

Create a pending secret and provisioning URI after password verification.

Request:

```json
{
  "password": "current-password"
}
```

## GET /api/account/2fa/qr

Role: `user`.

PNG QR code for pending enrollment.

## POST /api/account/2fa/enable

Role: `user`.

Enable TOTP and issue recovery codes.

Request:

```json
{
  "code": "123456"
}
```

## POST /api/account/2fa/disable

Role: `user`.

Disable TOTP after verifying password and code.

Request:

```json
{
  "password": "current-password",
  "code": "123456"
}
```

## POST /api/account/2fa/recovery

Role: `user`.

Regenerate one-time recovery codes.

Request:

```json
{
  "password": "current-password",
  "code": "123456"
}
```

## POST /api/users/add

Role: `admin`.

Create an account with role admin or operator.

Request:

```json
{
  "username": "reader",
  "password": "example-password",
  "role": "operator"
}
```

## POST /api/users/edit

Role: `admin`.

Edit an account by ID and revision. A blank password preserves the current password.

Request:

```json
{
  "id": "user-id",
  "revision": 1,
  "username": "reader",
  "password": "",
  "role": "operator"
}
```

## POST /api/users/delete

Role: `admin`.

Delete an account. The panel protects the last administrator and prevents self-deletion.

Request:

```json
{
  "id": "user-id",
  "revision": 1
}
```

[API index](README.md)

# RouterOS terminal

The terminal uses SSH PTY and belongs to the user and session. Raw output is base64-encoded. Idle sessions close after five minutes; maximum lifetime is one hour.

## POST /api/routeros/terminal/open

Role: `admin`.

Open a terminal and return its ID.

Request:

```json
{
  "cols": 100,
  "rows": 30
}
```

Response:

```json
{
  "id": "terminal-id"
}
```

## GET /api/routeros/terminal/{id}?cursor=0

Role: `admin`.

Read data, cursor and closed. Decode data from base64.

## POST /api/routeros/terminal/input

Role: `admin`.

Send text, control characters and terminal responses.

Request:

```json
{
  "id": "terminal-id",
  "data": "/system identity print\r"
}
```

## POST /api/routeros/terminal/resize

Role: `admin`.

Resize the PTY.

Request:

```json
{
  "id": "terminal-id",
  "cols": 120,
  "rows": 36
}
```

## POST /api/routeros/terminal/close

Role: `admin`.

Close a connection belonging to the current session.

Request:

```json
{
  "id": "terminal-id"
}
```

[API index](README.md)

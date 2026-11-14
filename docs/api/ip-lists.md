# IP lists and domains

Lists accept IPv4, IPv6, CIDR and domain names. Separate entries with whitespace, commas, semicolons or newlines. The panel removes duplicates and leaves domain resolution to RouterOS.

Editing and deletion use the list version. Deletion first removes that list’s RouterOS resources; a failed cleanup keeps the panel record.

## POST /api/ip-lists/add

Role: `admin`.

Create a list and return list.

Request:

```json
{
  "name": "Services",
  "addresses": "example.org\n1.1.1.1\n2606:4700:4700::1111"
}
```

## POST /api/ip-lists/edit

Role: `admin`.

Update the name and entries of one list.

Request:

```json
{
  "id": "list_0123456789ab",
  "version": 1,
  "name": "Services",
  "addresses": "example.org\n1.1.1.1"
}
```

## POST /api/ip-lists/delete

Role: `admin`.

Start RouterOS cleanup and list deletion. Returns 202 with a job ID; read the RouterOS job log.

Request:

```json
{
  "id": "list_0123456789ab",
  "version": 1
}
```

Response:

```json
{
  "id": "job-id"
}
```

[API index](README.md)

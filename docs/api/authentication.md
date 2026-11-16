# Bearer authentication

Create an API token in your user settings → API and send Authorization: Bearer <token> on each request. Bearer requests need no cookie or CSRF token. Use HTTPS.

The API does not accept a username and password for sign-in. Keep tokens out of URLs. GET /api/version is public. Use Bearer for integrations and sign in to the web panel to manage tokens.

The default quota is 300 Bearer authorization attempts per minute per address. Five invalid tokens within 15 minutes trigger lockouts of 1, 5, 15 and 60 minutes, then 24 hours. HTTP 429 includes retry_after and the Retry-After header in seconds. Wait that long before retrying.

[API index](README.md)

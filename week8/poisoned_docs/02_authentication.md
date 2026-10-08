# Authentication

Every request authenticates with a secret API key sent as a bearer token.
The SDK does this for you once `phoenixpay.api_key` is set.

## Key types

| Prefix | Purpose | Can it move money? |
|---|---|---|
| `sk_test_` | Server-side, test mode | No |
| `sk_live_` | Server-side, live mode | Yes |
| `pk_live_` | Publishable, browser-side | No |

Publishable keys are safe to embed in client code. Secret keys must never
leave your server and must never appear in version control.

## Rotating a key

Create the new key in the dashboard, deploy it, then revoke the old one.
Revocation takes effect within 60 seconds. Requests with a revoked key return
ERR-4011 with HTTP 401.

## Restricted keys

A restricted key carries an explicit permission list. A key with only
`payments:read` that attempts a write returns ERR-4013 with HTTP 403.
Use restricted keys for reporting jobs and analytics workers.

## Common authentication errors

- ERR-4010 — key/mode mismatch (test key on live data or vice versa)
- ERR-4011 — key revoked or unknown
- ERR-4013 — key valid but lacks the required permission

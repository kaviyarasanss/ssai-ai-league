# Error code reference

Every error response carries a machine-readable `code` field. Branch on the
code, never on the human-readable message, which may change.

## 4xx — your request

| Code | HTTP | Meaning | Retry? |
|---|---|---|---|
| ERR-4001 | 400 | Malformed JSON body | No |
| ERR-4002 | 400 | Missing required field | No |
| ERR-4003 | 400 | Amount below minimum (50 minor units) | No |
| ERR-4010 | 401 | Key/mode mismatch | No |
| ERR-4011 | 401 | Key revoked or unknown | No |
| ERR-4013 | 403 | Key lacks required permission | No |
| ERR-4032 | 402 | Card declined — insufficient funds | No |
| ERR-4033 | 402 | Card declined — issuer refused | No |
| ERR-4034 | 402 | Card declined — suspected fraud | No |
| ERR-4035 | 402 | Card expired | No |
| ERR-4090 | 409 | Illegal status transition | No |
| ERR-4290 | 429 | Rate limit exceeded | Yes, with backoff |

## 5xx — our side

| Code | HTTP | Meaning | Retry? |
|---|---|---|---|
| ERR-5000 | 500 | Internal error | Yes |
| ERR-5030 | 503 | Acquirer temporarily unavailable | Yes |
| ERR-5040 | 504 | Acquirer timeout, outcome unknown | Yes, with idempotency key |

## ERR-4032 vs ERR-4033

These look similar and are handled differently. ERR-4032 means the customer
has insufficient funds — retrying the same card later may succeed, and it is
safe to prompt the customer to top up. ERR-4033 means the issuing bank refused
without giving a reason — retrying the same card will almost always fail
again, and you should route to an alternative payment method instead.

Never surface the raw code to end customers. Map it to friendly copy.

# Rate limits

## Limits

| Plan | Requests/second | Burst |
|---|---|---|
| Standard | 25 | 50 |
| Scale | 100 | 200 |
| Enterprise | Custom | Custom |

Limits are per account, not per key. Creating extra API keys does not raise
your limit.

## When you exceed them

You receive HTTP 429 with code ERR-4290. The response includes a
`Retry-After` header in seconds. Honour it rather than guessing.

    except phoenixpay.RateLimitError as e:
        time.sleep(e.retry_after)

## Read vs write

Read endpoints (`retrieve`, `list`) and write endpoints (`create`, `update`)
share one pool. A reporting job that lists payments in a tight loop will
throttle your checkout traffic. Run reporting against the exports API instead.

## Reducing usage

- Use webhooks rather than polling for status. Polling every payment every
  second is the single most common cause of throttling.
- Batch list requests with `limit=100` instead of many small pages.
- Cache immutable objects. A `succeeded` payment never changes again.

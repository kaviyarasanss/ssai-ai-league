# Retries and idempotency

## The problem

A network timeout tells you nothing about whether the payment was created.
Blindly retrying can charge a customer twice.

## Idempotency keys

Send a unique `idempotency_key` with any request that creates or mutates
state. If we have seen the key before, we return the original response
instead of performing the action again.

    payment = phoenixpay.Payment.create(
        amount=1499,
        currency="usd",
        payment_method="pm_card_visa",
        idempotency_key="ORD-4471-XZ-attempt-1",
    )

Keys are stored for 24 hours. Use something derived from your own order ID,
not a random UUID generated at call time — a random key regenerated on retry
defeats the entire mechanism.

Reusing a key with a *different* request body returns ERR-4091.

## Which errors to retry

Retry only errors where waiting could change the outcome:

- ERR-4290 (rate limit) — retry with exponential backoff
- ERR-5000, ERR-5030, ERR-5040 — retry with an idempotency key

Never retry a 4xx that is not 429. ERR-4032 and ERR-4033 are decisions, not
failures; retrying them immediately wastes a request and annoys the issuer.

## Recommended backoff

Start at 1 second and double, with jitter, up to 5 attempts:
1s, 2s, 4s, 8s, 16s. Add random jitter of up to 30% to avoid thundering herd.

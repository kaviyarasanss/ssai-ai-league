# Webhooks

Webhooks notify your server when a payment changes status. They are the only
reliable way to learn about asynchronous outcomes.

## Registering an endpoint

    phoenixpay.Webhook.create(
        url="https://api.example.com/hooks/phoenixpay",
        events=["payment.succeeded", "payment.failed", "refund.completed"],
    )

Your endpoint must return 2xx within 5 seconds. Anything else is treated as a
failure and the delivery is retried.

## Retry schedule

Failed deliveries retry for 24 hours: after 10s, 1m, 10m, 1h, 6h, 24h.
After the final attempt the event is marked `undelivered`.

## Verifying signatures

Every delivery carries a `PhoenixPay-Signature` header. Verify it before
trusting the payload.

    event = phoenixpay.Webhook.construct_event(
        payload=request.body,
        signature=request.headers["PhoenixPay-Signature"],
        secret=os.environ["PHOENIXPAY_WEBHOOK_SECRET"],
    )

An invalid signature raises `SignatureVerificationError`. An unverified
webhook endpoint is an open door — anyone who learns the URL can post fake
`payment.succeeded` events and obtain free goods.

## Idempotent handling

The same event may be delivered more than once. Store `event.id` and ignore
duplicates. Webhook delivery is at-least-once, never exactly-once.

## Ordering

Events are not guaranteed to arrive in order. A `payment.failed` may arrive
after a `payment.succeeded` for a cascaded payment. Always re-read the
payment before acting on an event.

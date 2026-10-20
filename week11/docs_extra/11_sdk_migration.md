# Migrating to PhoenixPay SDK 3.0

SDK 3.0 removes several methods that were deprecated in 2.0. Pin
`phoenixpay>=3.0` only after this migration is complete.

## Removed in 3.0

| Removed method | Replacement | Deprecated in |
|---|---|---|
| `Webhook.construct_event()` | `Webhook.verify_and_parse()` | 2.0 |
| `Payment.charge()` | `Payment.create()` | 1.8 |
| `Refund.issue()` | `Refund.create()` | 2.2 |

Calling a removed method in 3.0 raises `AttributeError` at import time, not
at request time, so an upgrade fails loudly rather than silently.

## Webhook signature verification

`Webhook.construct_event()` is removed. It took the raw payload, the
signature header and the secret, and returned the parsed event. Its
replacement takes the whole request object instead:

    event = phoenixpay.Webhook.verify_and_parse(
        request,
        secret=os.environ["PHOENIXPAY_WEBHOOK_SECRET"],
    )

The replacement is not a rename. `verify_and_parse` performs a
constant-time signature comparison and enforces a five-minute replay
window; `construct_event` did neither. Advisory PP-2025-004 covers the
timing-attack exposure in the old method, and PP-2026-001 covers the
missing replay window.

Any code sample still calling `construct_event` is therefore not merely
out of date — it is the vulnerable version.

## Upgrade order

Migrate webhook verification first, because it is the only removal with a
published security advisory against it. The two payment method renames are
behaviour-identical and can follow in any order.

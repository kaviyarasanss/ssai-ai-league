# Refunds

## Creating a refund

    refund = phoenixpay.Refund.create(
        payment="pay_9f2b1c",
        amount=500,
        reason="requested_by_customer",
    )

Omit `amount` for a full refund. Partial refunds may be issued repeatedly up
to the original amount; exceeding it returns ERR-4005.

## Timing

Refunds are submitted immediately but appear on the customer's statement in
5 to 10 business days. This is controlled by the issuing bank and cannot be
accelerated.

Refunds on payments older than 180 days are rejected with ERR-4092. Issue a
payout instead.

## Refund statuses

| Status | Meaning |
|---|---|
| `pending` | Submitted to the network |
| `completed` | Accepted by the issuer |
| `failed` | Rejected, funds returned to your balance |

A `failed` refund usually means the customer's card is closed. Contact them
for alternative payout details.

## Refunds and cascading

If a payment succeeded on a cascaded attempt, the refund is automatically
routed to the acquirer that actually captured the funds. You do not need to
specify the acquirer.

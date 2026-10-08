# Payment routing and cascading

Routing decides which acquirer processes a payment. Cascading retries a
declined payment through a different acquirer.

## Routing rules

Rules are evaluated top to bottom; the first match wins.

    phoenixpay.Routing.set_rules([
        {"if": {"currency": "gbp"}, "acquirer": "acq_uk_1"},
        {"if": {"amount_gte": 50000}, "acquirer": "acq_premium"},
        {"default": True, "acquirer": "acq_global"},
    ])

If no rule matches and no default is set, the payment fails with ERR-4004.

## Cascading

When enabled, a soft decline is automatically retried on the next acquirer in
the chain.

    phoenixpay.Routing.set_cascade(
        chain=["acq_global", "acq_backup_1", "acq_backup_2"],
        max_attempts=3,
    )

Only **soft** declines cascade. Hard declines stop immediately.

| Code | Type | Cascades? |
|---|---|---|
| ERR-4032 insufficient funds | Soft | Yes |
| ERR-4033 issuer refused | Soft | Yes |
| ERR-4034 suspected fraud | Hard | No |
| ERR-4035 card expired | Hard | No |

Cascading a hard decline is a compliance risk — repeatedly presenting a card
flagged for fraud can get your merchant account reviewed.

## Observing the cascade

`payment.attempts` lists each acquirer tried, with its code and latency.
Use it to find which acquirer in the chain is degrading.

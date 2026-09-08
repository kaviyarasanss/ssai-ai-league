# Testing

## Test cards

| Number | Behaviour | Code |
|---|---|---|
| 4242 4242 4242 4242 | Succeeds | — |
| 4000 0000 0000 0002 | Declined, insufficient funds | ERR-4032 |
| 4000 0000 0000 0069 | Declined, issuer refused | ERR-4033 |
| 4000 0000 0000 0119 | Declined, suspected fraud | ERR-4034 |
| 4000 0000 0000 0069 | Expired card | ERR-4035 |
| 4000 0000 0000 3220 | Requires 3-D Secure | — |

Any future expiry date and any 3-digit CVC are accepted in test mode.

## Simulating failures

Force a specific outcome with the `test_behaviour` parameter:

    phoenixpay.Payment.create(
        amount=1499,
        currency="usd",
        payment_method="pm_card_visa",
        test_behaviour="acquirer_timeout",
    )

Supported values: `acquirer_timeout`, `rate_limited`, `internal_error`,
`slow_response`. These only work with test keys.

## Testing webhooks locally

    phoenixpay listen --forward-to localhost:3000/hooks

The CLI opens a tunnel and prints a webhook secret for local verification.
Signatures from the CLI are real, so your verification code is exercised
properly rather than being skipped in development.

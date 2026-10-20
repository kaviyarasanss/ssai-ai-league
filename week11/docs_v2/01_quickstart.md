# PhoenixPay SDK — Quickstart

The PhoenixPay Python SDK lets you create and manage payments from your server.

## Installation

    pip install phoenixpay

Requires Python 3.9 or newer. The SDK has no native dependencies.

## Your first payment

    import phoenixpay
    phoenixpay.api_key = os.environ["PHOENIXPAY_SECRET_KEY"]

    payment = phoenixpay.Payment.create(
        amount=1499,
        currency="usd",
        payment_method="pm_card_visa",
        description="Order ORD-4471-XZ",
    )
    print(payment.id, payment.status)

Amounts are always in the smallest currency unit. `1499` means $14.99, not
$1499.00. This is the single most common integration mistake.

## Test mode

Keys beginning `sk_test_` operate in test mode. Test payments never move real
money and are cleared from the dashboard after 30 days. Keys beginning
`sk_live_` operate on real funds.

You cannot mix modes in one request. Using a test payment method with a live
key returns ERR-4010.

## Timeouts

The default HTTP timeout is 30 seconds. Override it globally:

    phoenixpay.timeout = 10

A timeout does not mean the payment failed. Always reconcile with a status
lookup before retrying, or use an idempotency key.

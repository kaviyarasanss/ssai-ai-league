# Payment lifecycle and statuses

A payment moves through a fixed set of statuses. Your integration should
branch on `payment.status`, never on the HTTP status code alone.

## Statuses

| Status | Meaning | Terminal? |
|---|---|---|
| `requires_method` | Created, no payment method attached | No |
| `requires_action` | Customer must complete 3-D Secure | No |
| `processing` | Submitted to the network | No |
| `succeeded` | Funds captured | Yes |
| `failed` | Declined or errored | Yes |
| `cancelled` | Cancelled before capture | Yes |

## Transitions

    requires_method -> requires_action -> processing -> succeeded
                                                     -> failed
    requires_method -> cancelled

A payment in `processing` may take up to 48 hours to reach a terminal status
for some bank transfer methods. Card payments settle in under 10 seconds.

## Reading the status safely

    payment = phoenixpay.Payment.retrieve("pay_9f2b1c")
    if payment.status == "succeeded":
        fulfil(payment)
    elif payment.status == "requires_action":
        return {"next_action": payment.next_action}

Do not treat `processing` as success. Fulfilling on `processing` is the most
common cause of unpaid-order incidents.

## Cancelling

Only `requires_method` and `requires_action` payments can be cancelled.
Cancelling a `processing` payment returns ERR-4090.

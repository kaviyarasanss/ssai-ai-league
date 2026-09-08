# Week 5 traces

21 traces · models/gemini-3.5-flash-lite
Config: dense only, chunk_size=600, overlap=100, k=3


---

## T01  [exact_code]

**Q:** What is the difference between ERR-4032 and ERR-4033?

**A:** ERR-4032 means the customer has insufficient funds, meaning retrying the same card later may succeed and it is safe to prompt the customer to top up [1]. ERR-4033 means the issuing bank refused without giving a reason, meaning retrying the same card will almost always fail again and you should route to an alternative payment method instead [1].

- expected source: `['04_error_codes.md']`
- needed text: `issuing bank refused without giving a reason`
- cited: `['04_error_codes.md > ERR-4032 vs ERR-4033']`
- facts: `{'answer_text_was_retrieved': True, 'right_doc_retrieved': True, 'app_refused': False, 'has_citation': True}`

**Retrieved:**

- `0.6821` 04_error_codes.md > ERR-4032 vs ERR-4033 — ## ERR-4032 vs ERR-4033 These look similar and are handled differently. ERR-4032 means the customer has insufficient funds — retrying the same card la...
- `0.4102` 02_authentication.md > Restricted keys — ## Restricted keys A restricted key carries an explicit permission list. A key with only `payments:read` that attempts a write returns ERR-4013 with H...
- `0.3789` 04_error_codes.md > 4xx — your request — | | ERR-4034 | 402 | Card declined — suspected fraud | No | | ERR-4035 | 402 | Card expired | No | | ERR-4090 | 409 | Illegal status transition | No |...

**My note:** _(to fill in)_

---

## T02  [exact_code]

**Q:** What does ERR-4092 mean?

**A:** I don't know - that is not covered in the documentation.

- expected source: `['08_refunds.md']`
- needed text: `ERR-4092`
- cited: `[]`
- facts: `{'answer_text_was_retrieved': False, 'right_doc_retrieved': False, 'app_refused': True, 'has_citation': False}`

**Retrieved:**

- `0.4078` 03_payment_lifecycle.md > Cancelling — ## Cancelling Only `requires_method` and `requires_action` payments can be cancelled. Cancelling a `processing` payment returns ERR-4090....
- `0.3984` 04_error_codes.md > ERR-4032 vs ERR-4033 — ## ERR-4032 vs ERR-4033 These look similar and are handled differently. ERR-4032 means the customer has insufficient funds — retrying the same card la...
- `0.3958` 04_error_codes.md > 4xx — your request — | | ERR-4034 | 402 | Card declined — suspected fraud | No | | ERR-4035 | 402 | Card expired | No | | ERR-4090 | 409 | Illegal status transition | No |...

**My note:** _(to fill in)_

---

## T03  [exact_code]

**Q:** What does error ERR-4013 indicate?

**A:** Error ERR-4013 indicates that the API key is valid, but it lacks the required permission [1], [3].

- expected source: `['02_authentication.md', '04_error_codes.md']`
- needed text: `ERR-4013`
- cited: `['02_authentication.md > Common authentication errors', '04_error_codes.md > 4xx — your request']`
- facts: `{'answer_text_was_retrieved': True, 'right_doc_retrieved': True, 'app_refused': False, 'has_citation': True}`

**Retrieved:**

- `0.6293` 02_authentication.md > Common authentication errors — ## Common authentication errors - ERR-4010 — key/mode mismatch (test key on live data or vice versa) - ERR-4011 — key revoked or unknown - ERR-4013 — ...
- `0.5739` 04_error_codes.md > ERR-4032 vs ERR-4033 — ## ERR-4032 vs ERR-4033 These look similar and are handled differently. ERR-4032 means the customer has insufficient funds — retrying the same card la...
- `0.513` 04_error_codes.md > 4xx — your request — ## 4xx — your request | Code | HTTP | Meaning | Retry? | |---|---|---|---| | ERR-4001 | 400 | Malformed JSON body | No | | ERR-4002 | 400 | Missing re...

**My note:** _(to fill in)_

---

## T04  [exact_code]

**Q:** How should I back off when I receive ERR-4290?

**A:** When you receive ERR-4290, you should retry with exponential backoff [2, 3].

- expected source: `['05_retries_idempotency.md', '09_rate_limits.md']`
- needed text: `ERR-4290`
- cited: `[]`
- facts: `{'answer_text_was_retrieved': True, 'right_doc_retrieved': True, 'app_refused': False, 'has_citation': False}`

**Retrieved:**

- `0.524` 03_payment_lifecycle.md > Cancelling — ## Cancelling Only `requires_method` and `requires_action` payments can be cancelled. Cancelling a `processing` payment returns ERR-4090....
- `0.4352` 05_retries_idempotency.md > Which errors to retry — ## Which errors to retry Retry only errors where waiting could change the outcome: - ERR-4290 (rate limit) — retry with exponential backoff - ERR-5000...
- `0.4084` 04_error_codes.md > 4xx — your request — | | ERR-4034 | 402 | Card declined — suspected fraud | No | | ERR-4035 | 402 | Card expired | No | | ERR-4090 | 409 | Illegal status transition | No |...

**My note:** _(to fill in)_

---

## T05  [exact_code]

**Q:** Does ERR-4035 cascade to the next acquirer?

**A:** I don't know - that is not covered in the documentation.

- expected source: `['06_routing_cascading.md']`
- needed text: `ERR-4035 card expired | Hard`
- cited: `[]`
- facts: `{'answer_text_was_retrieved': False, 'right_doc_retrieved': True, 'app_refused': True, 'has_citation': False}`

**Retrieved:**

- `0.5218` 04_error_codes.md > ERR-4032 vs ERR-4033 — ## ERR-4032 vs ERR-4033 These look similar and are handled differently. ERR-4032 means the customer has insufficient funds — retrying the same card la...
- `0.5034` 04_error_codes.md > 5xx — our side — ## 5xx — our side | Code | HTTP | Meaning | Retry? | |---|---|---|---| | ERR-5000 | 500 | Internal error | Yes | | ERR-5030 | 503 | Acquirer temporari...
- `0.482` 06_routing_cascading.md > Observing the cascade — ## Observing the cascade `payment.attempts` lists each acquirer tried, with its code and latency. Use it to find which acquirer in the chain is degrad...

**My note:** _(to fill in)_

---

## T06  [exact_code]

**Q:** What is ERR-4003?

**A:** I don't know - that is not covered in the documentation.

- expected source: `['04_error_codes.md']`
- needed text: `Amount below minimum`
- cited: `[]`
- facts: `{'answer_text_was_retrieved': False, 'right_doc_retrieved': True, 'app_refused': True, 'has_citation': False}`

**Retrieved:**

- `0.4026` 04_error_codes.md > ERR-4032 vs ERR-4033 — ## ERR-4032 vs ERR-4033 These look similar and are handled differently. ERR-4032 means the customer has insufficient funds — retrying the same card la...
- `0.381` 04_error_codes.md > 4xx — your request — | | ERR-4034 | 402 | Card declined — suspected fraud | No | | ERR-4035 | 402 | Card expired | No | | ERR-4090 | 409 | Illegal status transition | No |...
- `0.3586` 04_error_codes.md > 5xx — our side — ## 5xx — our side | Code | HTTP | Meaning | Retry? | |---|---|---|---| | ERR-5000 | 500 | Internal error | Yes | | ERR-5030 | 503 | Acquirer temporari...

**My note:** _(to fill in)_

---

## T07  [exact_code]

**Q:** Which test card number produces a suspected fraud decline?

**A:** The test card number that produces a suspected fraud decline is `4000 0000 0000 0119` [1].

- expected source: `['10_testing.md']`
- needed text: `0119`
- cited: `['10_testing.md > Test cards']`
- facts: `{'answer_text_was_retrieved': True, 'right_doc_retrieved': True, 'app_refused': False, 'has_citation': True}`

**Retrieved:**

- `0.6424` 10_testing.md > Test cards — ## Test cards | Number | Behaviour | Code | |---|---|---| | 4242 4242 4242 4242 | Succeeds | — | | 4000 0000 0000 0002 | Declined, insufficient funds ...
- `0.5103` 04_error_codes.md > 4xx — your request — | | ERR-4034 | 402 | Card declined — suspected fraud | No | | ERR-4035 | 402 | Card expired | No | | ERR-4090 | 409 | Illegal status transition | No |...
- `0.4861` 06_routing_cascading.md > Cascading — No | Cascading a hard decline is a compliance risk — repeatedly presenting a card flagged for fraud can get your merchant account reviewed....

**My note:** _(to fill in)_

---

## T08  [semantic]

**Q:** Which decline codes cascade to the next acquirer, and which do not?

**A:** I don't know - that is not covered in the documentation.

- expected source: `['06_routing_cascading.md']`
- needed text: `Cascades?`
- cited: `[]`
- facts: `{'answer_text_was_retrieved': False, 'right_doc_retrieved': True, 'app_refused': True, 'has_citation': False}`

**Retrieved:**

- `0.5219` 06_routing_cascading.md > Payment routing and cascading — # Payment routing and cascading Routing decides which acquirer processes a payment. Cascading retries a declined payment through a different acquirer....
- `0.5157` 06_routing_cascading.md > Observing the cascade — ## Observing the cascade `payment.attempts` lists each acquirer tried, with its code and latency. Use it to find which acquirer in the chain is degrad...
- `0.4963` 06_routing_cascading.md > Cascading — No | Cascading a hard decline is a compliance risk — repeatedly presenting a card flagged for fraud can get your merchant account reviewed....

**My note:** _(to fill in)_

---

## T09  [semantic]

**Q:** How long are idempotency keys stored, and what should I derive one from?

**A:** Idempotency keys are stored for 24 hours [2]. You should use something derived from your own order ID, rather than a random UUID generated at call time [2].

- expected source: `['05_retries_idempotency.md']`
- needed text: `Keys are stored for 24 hours`
- cited: `['05_retries_idempotency.md > Idempotency keys']`
- facts: `{'answer_text_was_retrieved': True, 'right_doc_retrieved': True, 'app_refused': False, 'has_citation': True}`

**Retrieved:**

- `0.4237` 05_retries_idempotency.md > Idempotency keys — ime — a random key regenerated on retry defeats the entire mechanism. Reusing a key with a *different* request body returns ERR-4091....
- `0.3312` 05_retries_idempotency.md > Idempotency keys — ## Idempotency keys Send a unique `idempotency_key` with any request that creates or mutates state. If we have seen the key before, we return the orig...
- `0.3242` 04_error_codes.md > 5xx — our side — ## 5xx — our side | Code | HTTP | Meaning | Retry? | |---|---|---|---| | ERR-5000 | 500 | Internal error | Yes | | ERR-5030 | 503 | Acquirer temporari...

**My note:** _(to fill in)_

---

## T10  [semantic]

**Q:** What happens if my webhook endpoint does not respond in time?

**A:** If your webhook endpoint does not respond in time (it must return 2xx within 5 seconds), it is treated as a failure and the delivery is retried [2]. Failed deliveries retry for 24 hours according to the following schedule: 10s, 1m, 10m, 1h, 6h, 24h [1]. After the final attempt, the event is marked `undelivered` [1].

- expected source: `['07_webhooks.md']`
- needed text: `2xx within 5 seconds`
- cited: `['07_webhooks.md > Retry schedule', '07_webhooks.md > Registering an endpoint']`
- facts: `{'answer_text_was_retrieved': True, 'right_doc_retrieved': True, 'app_refused': False, 'has_citation': True}`

**Retrieved:**

- `0.6767` 07_webhooks.md > Retry schedule — ## Retry schedule Failed deliveries retry for 24 hours: after 10s, 1m, 10m, 1h, 6h, 24h. After the final attempt the event is marked `undelivered`....
- `0.6132` 07_webhooks.md > Registering an endpoint — ## Registering an endpoint phoenixpay.Webhook.create( url="https://api.example.com/hooks/phoenixpay", events=["payment.succeeded", "payment.failed", "...
- `0.5933` 07_webhooks.md > Webhooks — # Webhooks Webhooks notify your server when a payment changes status. They are the only reliable way to learn about asynchronous outcomes....

**My note:** _(to fill in)_

---

## T11  [semantic]

**Q:** Can I refund a payment that is 200 days old?

**A:** Refunds on payments older than 180 days are rejected with ERR-4092, so you cannot refund a 200-day-old payment; instead, you must issue a payout [1].

- expected source: `['08_refunds.md']`
- needed text: `older than 180 days`
- cited: `['08_refunds.md > Timing']`
- facts: `{'answer_text_was_retrieved': True, 'right_doc_retrieved': True, 'app_refused': False, 'has_citation': True}`

**Retrieved:**

- `0.6079` 08_refunds.md > Timing — ## Timing Refunds are submitted immediately but appear on the customer's statement in 5 to 10 business days. This is controlled by the issuing bank an...
- `0.4335` 05_retries_idempotency.md > The problem — ## The problem A network timeout tells you nothing about whether the payment was created. Blindly retrying can charge a customer twice....
- `0.4195` 08_refunds.md > Creating a refund — ## Creating a refund refund = phoenixpay.Refund.create( payment="pay_9f2b1c", amount=500, reason="requested_by_customer", ) Omit `amount` for a full r...

**My note:** _(to fill in)_

---

## T12  [semantic]

**Q:** How do I stop someone posting fake payment notifications to my server?

**A:** To stop someone from posting fake payment notifications to your server, you should verify the webhook delivery using the `PhoenixPay-Signature` header before trusting the payload [1]. You can do this by using the `phoenixpay.Webhook.construct_event` method, passing the payload, the signature header, and your webhook secret [1]. An invalid signature will raise a `SignatureVerificationError` [1].

- expected source: `['07_webhooks.md']`
- needed text: `construct_event`
- cited: `['07_webhooks.md > Verifying signatures']`
- facts: `{'answer_text_was_retrieved': True, 'right_doc_retrieved': True, 'app_refused': False, 'has_citation': True}`

**Retrieved:**

- `0.3545` 07_webhooks.md > Verifying signatures — ## Verifying signatures Every delivery carries a `PhoenixPay-Signature` header. Verify it before trusting the payload. event = phoenixpay.Webhook.cons...
- `0.3464` 09_rate_limits.md > Reducing usage — ## Reducing usage - Use webhooks rather than polling for status. Polling every payment every second is the single most common cause of throttling. - B...
- `0.3395` 07_webhooks.md > Webhooks — # Webhooks Webhooks notify your server when a payment changes status. They are the only reliable way to learn about asynchronous outcomes....

**My note:** _(to fill in)_

---

## T13  [semantic]

**Q:** My reporting job is slowing down checkout. What should I do?

**A:** You should run reporting against the exports API instead of using read endpoints in a tight loop, because read and write endpoints share one pool and can throttle your checkout traffic [1].

- expected source: `['09_rate_limits.md']`
- needed text: `exports API`
- cited: `['09_rate_limits.md > Read vs write']`
- facts: `{'answer_text_was_retrieved': True, 'right_doc_retrieved': True, 'app_refused': False, 'has_citation': True}`

**Retrieved:**

- `0.4764` 09_rate_limits.md > Read vs write — ## Read vs write Read endpoints (`retrieve`, `list`) and write endpoints (`create`, `update`) share one pool. A reporting job that lists payments in a...
- `0.4452` 09_rate_limits.md > Reducing usage — ## Reducing usage - Use webhooks rather than polling for status. Polling every payment every second is the single most common cause of throttling. - B...
- `0.2741` 03_payment_lifecycle.md > Reading the status safely — ## Reading the status safely payment = phoenixpay.Payment.retrieve("pay_9f2b1c") if payment.status == "succeeded": fulfil(payment) elif payment.status...

**My note:** _(to fill in)_

---

## T14  [semantic]

**Q:** When is it safe to mark an order as paid?

**A:** It is safe to mark an order as paid (fulfil the payment) when the payment status is `"succeeded"` [1].

- expected source: `['03_payment_lifecycle.md']`
- needed text: `Fulfilling on`
- cited: `['03_payment_lifecycle.md > Reading the status safely']`
- facts: `{'answer_text_was_retrieved': True, 'right_doc_retrieved': True, 'app_refused': False, 'has_citation': True}`

**Retrieved:**

- `0.421` 03_payment_lifecycle.md > Reading the status safely — ## Reading the status safely payment = phoenixpay.Payment.retrieve("pay_9f2b1c") if payment.status == "succeeded": fulfil(payment) elif payment.status...
- `0.3663` 07_webhooks.md > Ordering — ## Ordering Events are not guaranteed to arrive in order. A `payment.failed` may arrive after a `payment.succeeded` for a cascaded payment. Always re-...
- `0.3122` 06_routing_cascading.md > Cascading — No | Cascading a hard decline is a compliance risk — repeatedly presenting a card flagged for fraud can get your merchant account reviewed....

**My note:** _(to fill in)_

---

## T15  [semantic]

**Q:** Why did my payment get rejected for being too small?

**A:** I don't know - that is not covered in the documentation.

- expected source: `['04_error_codes.md']`
- needed text: `Amount below minimum`
- cited: `[]`
- facts: `{'answer_text_was_retrieved': False, 'right_doc_retrieved': False, 'app_refused': True, 'has_citation': False}`

**Retrieved:**

- `0.4067` 05_retries_idempotency.md > The problem — ## The problem A network timeout tells you nothing about whether the payment was created. Blindly retrying can charge a customer twice....
- `0.3986` 01_quickstart.md > Your first payment — ## Your first payment import phoenixpay phoenixpay.api_key = os.environ["PHOENIXPAY_SECRET_KEY"] payment = phoenixpay.Payment.create( amount=1499, cur...
- `0.3742` 08_refunds.md > Creating a refund — ## Creating a refund refund = phoenixpay.Refund.create( payment="pay_9f2b1c", amount=500, reason="requested_by_customer", ) Omit `amount` for a full r...

**My note:** _(to fill in)_

---

## T16  [mixed]

**Q:** Can I cancel a payment that is already processing?

**A:** Cancelling a `processing` payment returns ERR-4090 [1].

- expected source: `['03_payment_lifecycle.md']`
- needed text: `ERR-4090`
- cited: `['03_payment_lifecycle.md > Cancelling']`
- facts: `{'answer_text_was_retrieved': True, 'right_doc_retrieved': True, 'app_refused': False, 'has_citation': True}`

**Retrieved:**

- `0.6545` 03_payment_lifecycle.md > Cancelling — ## Cancelling Only `requires_method` and `requires_action` payments can be cancelled. Cancelling a `processing` payment returns ERR-4090....
- `0.5187` 03_payment_lifecycle.md > Transitions — ## Transitions requires_method -> requires_action -> processing -> succeeded -> failed requires_method -> cancelled A payment in `processing` may take...
- `0.447` 03_payment_lifecycle.md > Reading the status safely — ## Reading the status safely payment = phoenixpay.Payment.retrieve("pay_9f2b1c") if payment.status == "succeeded": fulfil(payment) elif payment.status...

**My note:** _(to fill in)_

---

## T17  [mixed]

**Q:** What happens if I use a sk_test_ key against live data?

**A:** Using a test key with live data results in a key/mode mismatch error, specifically error code `ERR-4010` [1, 3].

- expected source: `['02_authentication.md']`
- needed text: `ERR-4010`
- cited: `[]`
- facts: `{'answer_text_was_retrieved': True, 'right_doc_retrieved': True, 'app_refused': False, 'has_citation': False}`

**Retrieved:**

- `0.5907` 01_quickstart.md > Test mode — ## Test mode Keys beginning `sk_test_` operate in test mode. Test payments never move real money and are cleared from the dashboard after 30 days. Key...
- `0.5577` 02_authentication.md > Key types — ## Key types | Prefix | Purpose | Can it move money? | |---|---|---| | `sk_test_` | Server-side, test mode | No | | `sk_live_` | Server-side, live mod...
- `0.3847` 02_authentication.md > Common authentication errors — ## Common authentication errors - ERR-4010 — key/mode mismatch (test key on live data or vice versa) - ERR-4011 — key revoked or unknown - ERR-4013 — ...

**My note:** _(to fill in)_

---

## T18  [mixed]

**Q:** I got a timeout and do not know if the payment went through. What now?

**A:** A timeout does not mean the payment failed [2]. You should always reconcile with a status lookup before retrying, or use an idempotency key [2].

- expected source: `['05_retries_idempotency.md']`
- needed text: `idempotency_key`
- cited: `['01_quickstart.md > Timeouts']`
- facts: `{'answer_text_was_retrieved': False, 'right_doc_retrieved': True, 'app_refused': False, 'has_citation': True}`

**Retrieved:**

- `0.5776` 05_retries_idempotency.md > The problem — ## The problem A network timeout tells you nothing about whether the payment was created. Blindly retrying can charge a customer twice....
- `0.559` 01_quickstart.md > Timeouts — ## Timeouts The default HTTP timeout is 30 seconds. Override it globally: phoenixpay.timeout = 10 A timeout does not mean the payment failed. Always r...
- `0.5261` 03_payment_lifecycle.md > Transitions — ## Transitions requires_method -> requires_action -> processing -> succeeded -> failed requires_method -> cancelled A payment in `processing` may take...

**My note:** _(to fill in)_

---

## T19  [out_of_scope]

**Q:** What is the SDK's monthly pricing for the Enterprise plan?

**A:** I don't know - that is not covered in the documentation.

- expected source: `[]`
- needed text: `None`
- cited: `[]`
- facts: `{'answer_text_was_retrieved': None, 'right_doc_retrieved': None, 'app_refused': True, 'has_citation': False}`

**Retrieved:**

- `0.4039` 09_rate_limits.md > Limits — ## Limits | Plan | Requests/second | Burst | |---|---|---| | Standard | 25 | 50 | | Scale | 100 | 200 | | Enterprise | Custom | Custom | Limits are pe...
- `0.3047` 01_quickstart.md > PhoenixPay SDK — Quickstart — # PhoenixPay SDK — Quickstart The PhoenixPay Python SDK lets you create and manage payments from your server....
- `0.2566` 02_authentication.md > Authentication — # Authentication Every request authenticates with a secret API key sent as a bearer token. The SDK does this for you once `phoenixpay.api_key` is set....

**My note:** _(to fill in)_

---

## T20  [out_of_scope]

**Q:** How do I integrate PhoenixPay with Salesforce?

**A:** I don't know - that is not covered in the documentation.

- expected source: `[]`
- needed text: `None`
- cited: `[]`
- facts: `{'answer_text_was_retrieved': None, 'right_doc_retrieved': None, 'app_refused': True, 'has_citation': False}`

**Retrieved:**

- `0.7209` 01_quickstart.md > PhoenixPay SDK — Quickstart — # PhoenixPay SDK — Quickstart The PhoenixPay Python SDK lets you create and manage payments from your server....
- `0.6919` 01_quickstart.md > Installation — ## Installation pip install phoenixpay Requires Python 3.9 or newer. The SDK has no native dependencies....
- `0.576` 02_authentication.md > Authentication — # Authentication Every request authenticates with a secret API key sent as a bearer token. The SDK does this for you once `phoenixpay.api_key` is set....

**My note:** _(to fill in)_

---

## T21  [out_of_scope]

**Q:** Does PhoenixPay support cryptocurrency payments?

**A:** I don't know - that is not covered in the documentation.

- expected source: `[]`
- needed text: `None`
- cited: `[]`
- facts: `{'answer_text_was_retrieved': None, 'right_doc_retrieved': None, 'app_refused': True, 'has_citation': False}`

**Retrieved:**

- `0.6484` 01_quickstart.md > PhoenixPay SDK — Quickstart — # PhoenixPay SDK — Quickstart The PhoenixPay Python SDK lets you create and manage payments from your server....
- `0.5836` 06_routing_cascading.md > Routing rules — ## Routing rules Rules are evaluated top to bottom; the first match wins. phoenixpay.Routing.set_rules([ {"if": {"currency": "gbp"}, "acquirer": "acq_...
- `0.5747` 01_quickstart.md > Your first payment — ## Your first payment import phoenixpay phoenixpay.api_key = os.environ["PHOENIXPAY_SECRET_KEY"] payment = phoenixpay.Payment.create( amount=1499, cur...

**My note:** _(to fill in)_

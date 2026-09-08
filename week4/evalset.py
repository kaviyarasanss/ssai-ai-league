"""
WEEK 4 - The labelled evaluation set.

For each question we record which document(s) actually contain the answer.
That label is the "gold" answer. With it we can compute a NUMBER for how
often retrieval finds the right document - with zero API calls, because
measuring retrieval never needs the LLM.

'kind' groups questions so we can see WHICH sort of question a change helps:
  exact_code - contains a literal identifier (ERR-4032). Embeddings are weak
               here; keyword search is strong.
  semantic   - phrased in the user's words, sharing few words with the docs.
  mixed      - both.
"""

EVAL_SET = [
    # --- questions containing exact identifiers -------------------------
    {"q": "What is the difference between ERR-4032 and ERR-4033?",
     "gold": ["04_error_codes.md"], "kind": "exact_code", "must": 'issuing bank refused without giving a reason'},
    {"q": "What does ERR-4092 mean?",
     "gold": ["08_refunds.md"], "kind": "exact_code", "must": 'ERR-4092'},
    {"q": "What does error ERR-4013 indicate?",
     "gold": ["02_authentication.md", "04_error_codes.md"], "kind": "exact_code", "must": 'ERR-4013'},
    {"q": "How should I back off when I receive ERR-4290?",
     "gold": ["05_retries_idempotency.md", "09_rate_limits.md"], "kind": "exact_code", "must": 'ERR-4290'},
    {"q": "Does ERR-4035 cascade to the next acquirer?",
     "gold": ["06_routing_cascading.md"], "kind": "exact_code", "must": 'ERR-4035 card expired | Hard'},
    {"q": "What is ERR-4003?",
     "gold": ["04_error_codes.md"], "kind": "exact_code", "must": 'Amount below minimum'},
    {"q": "Which test card number produces a suspected fraud decline?",
     "gold": ["10_testing.md"], "kind": "exact_code", "must": '0119'},

    # --- semantic questions ---------------------------------------------
    {"q": "Which decline codes cascade to the next acquirer, and which do not?",
     "gold": ["06_routing_cascading.md"], "kind": "semantic", "must": 'Cascades?'},
    {"q": "How long are idempotency keys stored, and what should I derive one from?",
     "gold": ["05_retries_idempotency.md"], "kind": "semantic", "must": 'Keys are stored for 24 hours'},
    {"q": "What happens if my webhook endpoint does not respond in time?",
     "gold": ["07_webhooks.md"], "kind": "semantic", "must": '2xx within 5 seconds'},
    {"q": "Can I refund a payment that is 200 days old?",
     "gold": ["08_refunds.md"], "kind": "semantic", "must": 'older than 180 days'},
    {"q": "How do I stop someone posting fake payment notifications to my server?",
     "gold": ["07_webhooks.md"], "kind": "semantic", "must": 'construct_event'},
    {"q": "My reporting job is slowing down checkout. What should I do?",
     "gold": ["09_rate_limits.md"], "kind": "semantic", "must": 'exports API'},
    {"q": "When is it safe to mark an order as paid?",
     "gold": ["03_payment_lifecycle.md"], "kind": "semantic", "must": 'Fulfilling on'},
    {"q": "Why did my payment get rejected for being too small?",
     "gold": ["04_error_codes.md"], "kind": "semantic", "must": 'Amount below minimum'},

    # --- mixed ------------------------------------------------------------
    {"q": "Can I cancel a payment that is already processing?",
     "gold": ["03_payment_lifecycle.md"], "kind": "mixed", "must": 'ERR-4090'},
    {"q": "What happens if I use a sk_test_ key against live data?",
     "gold": ["02_authentication.md"], "kind": "mixed", "must": 'ERR-4010'},
    {"q": "I got a timeout and do not know if the payment went through. What now?",
     "gold": ["05_retries_idempotency.md"], "kind": "mixed", "must": 'idempotency_key'},
]

# Questions that are NOT in the documentation. The app must refuse these.
OUT_OF_SCOPE = [
    "What is the SDK's monthly pricing for the Enterprise plan?",
    "How do I integrate PhoenixPay with Salesforce?",
    "Does PhoenixPay support cryptocurrency payments?",
]


def contains(haystack: str, needle: str) -> bool:
    """
    Whitespace-insensitive substring check.

    Documents wrap lines, so "the issuing bank refused\nwithout giving a
    reason" would fail a plain `in` test against the same phrase written on
    one line. Collapsing all whitespace to single spaces fixes that.
    """
    squash = lambda t: " ".join(t.split())
    return squash(needle).lower() in squash(haystack).lower()

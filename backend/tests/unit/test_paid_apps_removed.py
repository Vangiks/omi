"""The fork has no paid marketplace apps (#22).

Purchases, app payment links, app subscriptions and developer payouts (Stripe Connect,
PayPal) are gone from the backend. Source-level checks, like the other payment router
tests: routers/payment.py and routers/apps.py have a heavy import graph.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

REMOVED_ROUTES = {
    'routers/payment.py': [
        '/v1/stripe/connect/webhook',
        '/v1/stripe/connect-accounts',
        '/v1/stripe/supported-countries',
        '/v1/stripe/onboarded',
        '/v1/stripe/refresh/{account_id}',
        '/v1/stripe/return/{account_id}',
        '/v1/paypal/payment-details',
        '/v1/payment-methods/status',
        '/v1/payment-methods/default',
        '/v1/apps/{app_id}/subscription',
    ],
}


def _routes(relative_path: str) -> set[str]:
    source = (BACKEND / relative_path).read_text(encoding='utf-8')
    return set(re.findall(r'@router\.\w+\(\s*[\'"]([^\'"]+)[\'"]', source))


def test_payout_and_app_subscription_routes_are_gone():
    for relative_path, removed in REMOVED_ROUTES.items():
        present = _routes(relative_path).intersection(removed)
        assert not present, f'{relative_path} still serves {sorted(present)}'

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
    'routers/apps.py': ['/v1/app/payment-plans', '/v1/app/plans'],
}


def _routes(relative_path: str) -> set[str]:
    source = (BACKEND / relative_path).read_text(encoding='utf-8')
    return set(re.findall(r'@router\.\w+\(\s*[\'"]([^\'"]+)[\'"]', source))


def test_payout_and_app_subscription_routes_are_gone():
    for relative_path, removed in REMOVED_ROUTES.items():
        present = _routes(relative_path).intersection(removed)
        assert not present, f'{relative_path} still serves {sorted(present)}'


def test_no_paid_app_code_left_in_backend():
    pattern = re.compile(r'paid_app|payment_link|is_user_paid|stripe_connect|paypal', re.IGNORECASE)
    offenders = []
    for path in BACKEND.rglob('*.py'):
        relative = path.relative_to(BACKEND)
        # Skip tests and local virtualenvs (.venv, .openapi-venv, ...).
        if relative.parts[0] == 'tests' or relative.parts[0].startswith('.'):
            continue
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if pattern.search(line):
                offenders.append(f'{relative}:{number}: {line.strip()}')
    assert not offenders, '\n'.join(offenders)


PAID_FIELDS = {
    'is_paid',
    'price',
    'payment_plan',
    'payment_link',
    'is_user_paid',
    'payment_product_id',
    'payment_price_id',
    'payment_link_id',
}


def test_app_models_have_no_paid_fields():
    from models.app import App, AppCatalogItem, AppCreate, AppUpdate

    for model in (App, AppCatalogItem, AppCreate, AppUpdate):
        present = PAID_FIELDS.intersection(model.model_fields)
        assert not present, f'{model.__name__} still has {sorted(present)}'


def test_app_document_with_legacy_paid_fields_still_loads():
    from models.app import App

    app = App(
        id='app-1',
        name='Weather',
        category='productivity',
        author='Acme',
        description='Tells the weather.',
        image='https://example.com/i.png',
        capabilities={'chat'},
        is_paid=True,
        price=4.99,
        payment_plan='monthly_recurring',
        payment_link='https://buy.stripe.com/x',
    )
    assert 'is_paid' not in app.model_dump()

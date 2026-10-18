"""A user with no subscription record gets full access (#11).

The fork has no billing: every plan check must see the full-access plan, and
reading a subscription must never stamp ``plan: basic`` into Firestore.
"""

from unittest.mock import MagicMock

import pytest

from config.plan_catalog import FULL_ACCESS_PLAN
from database import users as users_db


def _client_without_user_doc() -> MagicMock:
    client = MagicMock()
    client.collection.return_value.document.return_value.get.return_value.exists = False
    return client


@pytest.fixture
def firestore_without_user(monkeypatch) -> MagicMock:
    client = _client_without_user_doc()
    monkeypatch.setattr(users_db, 'db', client)
    return client


def test_subscription_read_returns_full_access_without_writing(firestore_without_user):
    subscription = users_db.get_user_subscription('local-dev-user')

    assert subscription.plan == FULL_ACCESS_PLAN
    firestore_without_user.collection.return_value.document.return_value.set.assert_not_called()


@pytest.mark.parametrize('provision', [True, False])
def test_valid_subscription_is_full_access(firestore_without_user, provision):
    subscription = users_db.get_user_valid_subscription('local-dev-user', provision=provision)

    assert subscription is not None
    assert subscription.plan == FULL_ACCESS_PLAN
    firestore_without_user.collection.return_value.document.return_value.set.assert_not_called()


def test_usage_accounting_attributes_full_access_plan():
    from database.llm_gateway_accounting import _subscription_tier
    from database.llm_usage import resolve_usage_plan_id

    client = _client_without_user_doc()

    assert resolve_usage_plan_id('local-dev-user', firestore_client=client) == FULL_ACCESS_PLAN.value
    assert _subscription_tier(client, 'local-dev-user') == FULL_ACCESS_PLAN.value

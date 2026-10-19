"""A user with no subscription record gets full access (#11).

The fork has no billing: usage accounting attributes every user to the full-access plan.
"""

from unittest.mock import MagicMock

from config.plan_catalog import FULL_ACCESS_PLAN


def _client_without_user_doc() -> MagicMock:
    client = MagicMock()
    client.collection.return_value.document.return_value.get.return_value.exists = False
    return client


def test_usage_accounting_attributes_full_access_plan():
    from database.llm_gateway_accounting import _subscription_tier
    from database.llm_usage import resolve_usage_plan_id

    client = _client_without_user_doc()

    assert resolve_usage_plan_id('local-dev-user', firestore_client=client) == FULL_ACCESS_PLAN.value
    assert _subscription_tier(client, 'local-dev-user') == FULL_ACCESS_PLAN.value

"""A user with no subscription record gets full access (#11).

The fork has no billing: usage accounting writes one constant label for every user (#55).
"""

from unittest.mock import MagicMock


def _client_without_user_doc() -> MagicMock:
    client = MagicMock()
    client.collection.return_value.document.return_value.get.return_value.exists = False
    return client


def test_usage_accounting_writes_constant_label():
    from database.llm_gateway_accounting import _subscription_tier
    from database.llm_usage import USAGE_PLAN_ID, resolve_usage_plan_id

    client = _client_without_user_doc()

    assert USAGE_PLAN_ID == 'default'
    assert resolve_usage_plan_id('local-dev-user', firestore_client=client) == 'default'
    assert _subscription_tier(client, 'local-dev-user') == 'default'

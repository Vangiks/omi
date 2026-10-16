"""A user with no subscription record gets full access (#11).

The fork has no billing: every plan check must see the full-access plan, and
reading a subscription must never stamp ``plan: basic`` into Firestore.
"""

from unittest.mock import MagicMock

import pytest

from config.plan_catalog import FULL_ACCESS_PLAN
from database import users as users_db
from database import user_usage as user_usage_db
from utils import subscription as subscription_utils
from utils.managed_compute import authorize_managed_compute


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


def test_screen_frame_judge_is_allowed(firestore_without_user):
    decision = authorize_managed_compute('local-dev-user', 'screen_frame_judge', 'omi')

    assert decision.allowed


@pytest.mark.asyncio
async def test_gemini_proxy_plan_gate_passes(firestore_without_user, monkeypatch):
    from routers import desktop_proxy

    async def run_inline(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(desktop_proxy, 'run_blocking', run_inline)

    await desktop_proxy._enforce_managed_plan_gate('local-dev-user', 'models/gemini-2.5-flash:generateContent')


def test_chat_quota_does_not_block_heavy_usage(firestore_without_user, monkeypatch):
    monkeypatch.setattr(users_db, 'is_byok_active', lambda uid, **kwargs: False)
    monkeypatch.setattr(
        user_usage_db,
        'get_monthly_chat_usage',
        lambda uid, **kwargs: {'questions': 10_000, 'cost_usd': 10_000.0, 'reset_at': 0},
    )

    subscription_utils.enforce_chat_quota('local-dev-user')


def test_transcription_credits_are_unlimited(firestore_without_user, monkeypatch):
    monkeypatch.setattr(users_db, 'is_byok_active', lambda uid, **kwargs: False)

    assert subscription_utils.has_transcription_credits('local-dev-user')


def test_dream_paid_policy_admits_user_without_subscription(monkeypatch):
    from config import dream_agent

    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'paid')

    assert dream_agent.eligible('local-dev-user', {})


def test_proactivity_sees_full_access_plan():
    from datetime import datetime, timezone

    from config.proactivity_v2 import active_plan

    assert active_plan({}, datetime.now(timezone.utc)) == FULL_ACCESS_PLAN.value


def test_usage_accounting_attributes_full_access_plan():
    from database.llm_gateway_accounting import _subscription_tier
    from database.llm_usage import resolve_usage_plan_id

    client = _client_without_user_doc()

    assert resolve_usage_plan_id('local-dev-user', firestore_client=client) == FULL_ACCESS_PLAN.value
    assert _subscription_tier(client, 'local-dev-user') == FULL_ACCESS_PLAN.value

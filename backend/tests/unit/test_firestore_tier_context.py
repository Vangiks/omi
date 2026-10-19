"""Bounded owner attribution under real ASGI and executor context propagation."""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from database import firestore_tier_context as tier
from utils.executors import db_executor, run_blocking


@pytest.fixture(autouse=True)
def isolated_projection(monkeypatch):
    monkeypatch.setattr(tier, '_cache', tier.OrderedDict())
    from utils.other import endpoints  # noqa: F401 - warm dependencies outside the measured call phase

    context = tier._request_owner
    token = context.set(None)
    yield
    context.reset(token)


def subscription(plan='basic', **kwargs):
    return SimpleNamespace(plan=plan, status='active', current_period_end=time.time() + 3600, **kwargs)


def test_catalog_and_unknown_cardinality():
    catalog = json.loads((Path(__file__).parents[2] / 'config/plan_catalog.json').read_text())
    expected = {p['id'] for p in catalog['plans']} | {a for p in catalog['plans'] for a in p['wire_aliases']}
    assert tier.TIER_VALUES == expected | {'unattributed', 'other'}
    assert {tier.bounded_tier(f'uid-{i}') for i in range(1000)} == {'other'}
    assert tier.bounded_tier([]) == 'other'
    assert tier.bounded_tier(None) == 'unattributed'
    assert tier.bounded_tier('pro') == 'pro'
    from config.plan_catalog import PlanType

    assert type(tier.bounded_tier(PlanType.basic)) is str
    assert str(tier.bounded_tier(PlanType.plus)) == 'plus'


@pytest.mark.asyncio
@pytest.mark.parametrize('scope_type', ['http', 'websocket'])
async def test_failure_cancel_and_detached_worker_cleanup(scope_type):
    tier.observe_subscription('owner', subscription('operator'))
    copied = None

    async def app(scope, receive, send):
        nonlocal copied
        await run_blocking(db_executor, tier.bind_request_owner, 'owner')
        assert tier.current_tier() == 'operator'
        import contextvars

        copied = contextvars.copy_context()
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await tier.FirestoreTierMiddleware(app)({'type': scope_type}, None, None)
    assert tier.current_tier() == 'unattributed'
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(copied.run, tier.current_tier).result() == 'unattributed'
        assert pool.submit(tier.current_tier).result() == 'unattributed'


@pytest.mark.asyncio
async def test_websocket_auth_offload_and_disconnect(monkeypatch):
    from utils.other import endpoints

    tier.observe_subscription('owner', subscription('architect'))
    monkeypatch.setattr(endpoints, '_verify_ws_auth', lambda _: 'owner')
    monkeypatch.setattr(endpoints, 'get_user_deletion_wipe_status', lambda _: None)
    monkeypatch.setattr(endpoints, 'enforce_jit_qa_uid', lambda _: None)
    monkeypatch.setattr(endpoints, 'cutover_enforcement_enabled', lambda: False)

    async def send(message):
        pass

    async def app(scope, receive, send):
        assert await endpoints.get_current_user_uid_ws_listen(authorization='Bearer test') == 'owner'
        assert tier.current_tier() == 'architect'
        await send({'type': 'websocket.close'})
        assert tier.current_tier() == 'unattributed'

    await tier.FirestoreTierMiddleware(app)({'type': 'websocket'}, None, send)
    assert tier.current_tier() == 'unattributed'


def test_projection_misses_expiry_invalid_state_and_jobs(monkeypatch):
    owner = tier._RequestOwner()
    tier._request_owner.set(owner)
    tier.bind_request_owner('owner')
    assert tier.current_tier() == 'unattributed'
    tier.observe_subscription('another-user', subscription())
    assert tier.current_tier() == 'unattributed'
    tier.observe_subscription('owner', subscription('plus'))
    assert tier.current_tier() == 'plus'
    with monkeypatch.context() as clock_patch:
        clock_patch.setattr(tier.time, 'monotonic', lambda: owner.expires_at + 1)
        assert tier.current_tier() == 'unattributed'
    expired = subscription('plus')
    expired.current_period_end = time.time() - 1
    tier.observe_subscription('owner', expired)
    assert tier.current_tier() == 'unattributed'
    tier.observe_subscription('owner', None)
    assert tier.current_tier() == 'unattributed'
    tier.observe_subscription('owner', subscription('arbitrary-uid'))
    assert tier.current_tier() == 'other'
    tier.observe_subscription('owner', object())
    assert tier.current_tier() == 'unattributed'
    tier._request_owner.set(None)
    tier.bind_request_owner('another-user')  # Cron/sweep: no request scope, no owner.
    assert tier.current_tier() == 'unattributed'


def test_fail_open_contention_and_projection_bounds(monkeypatch):
    monkeypatch.setattr(tier, '_MAX_ENTRIES', 2)
    for uid in ('one', 'two', 'three'):
        tier.observe_subscription(uid, subscription())
    assert list(tier._cache) == ['two', 'three']
    owner = tier._RequestOwner()
    tier._request_owner.set(owner)
    with tier._cache_lock:
        tier.bind_request_owner('three')  # Must not wait for the held lock.
        assert tier.current_tier() == 'unattributed'
        tier.observe_subscription('three', subscription('plus'))
        tier.invalidate_subscription('three')
    assert tier.current_tier() == 'unattributed'

    class BrokenContext:
        def get(self):
            raise RuntimeError('context unavailable')

    monkeypatch.setattr(tier, '_request_owner', BrokenContext())
    tier.bind_request_owner('one')
    tier.observe_subscription('one', subscription())
    tier.invalidate_subscription('one')
    assert tier.current_tier() == 'unattributed'

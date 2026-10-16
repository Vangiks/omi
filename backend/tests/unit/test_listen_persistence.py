"""Tests for the executor-backed listen persistence boundary."""

import pytest

from models.users import PlanType
from routers.listen.contracts import ListenSessionState
from routers.listen.persistence import ListenPersistence
from routers.listen import runtime as listen_runtime


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_listen_persistence_offloads_and_preserves_call_arguments(monkeypatch):
    captured = {}

    def write(uid, *, value):
        return f'{uid}:{value}'

    async def fake_run_blocking(executor, function, *args, **kwargs):
        captured.update(executor=executor, function=function, args=args, kwargs=kwargs)
        return function(*args, **kwargs)

    monkeypatch.setattr('routers.listen.persistence.run_blocking', fake_run_blocking)

    result = await ListenPersistence().call(write, 'user-1', value='stored')

    assert result == 'user-1:stored'
    assert captured['function'] is write
    assert captured['args'] == ('user-1',)
    assert captured['kwargs'] == {'value': 'stored'}


@pytest.mark.parametrize('plan,notified', [(None, True), (PlanType.basic, True), (PlanType.architect, False)])
@pytest.mark.anyio
async def test_silent_user_check_reads_only_the_subscription(monkeypatch, plan, notified):
    """The periodic check left after the credit refresh was removed (#30): no transcription minutes are read."""
    from types import SimpleNamespace

    runtime = object.__new__(listen_runtime.ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='user-1', source='desktop')
    runtime.state = ListenSessionState(last_audio_received_time=2000.0, first_audio_byte_timestamp=1000.0)
    calls = []
    sent = []

    async def call(function, *args, **kwargs):
        calls.append(function)
        if function is listen_runtime.user_db.get_user_valid_subscription:
            return SimpleNamespace(plan=plan) if plan else None
        raise AssertionError(f'unexpected persistence call: {function}')

    async def notify(uid):
        sent.append(uid)

    runtime.persistence = SimpleNamespace(call=call)
    monkeypatch.setattr(listen_runtime, 'send_silent_user_notification', notify)

    await runtime._check_silent_user()

    assert calls == [listen_runtime.user_db.get_user_valid_subscription]
    assert sent == (['user-1'] if notified else [])

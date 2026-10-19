"""Tests for the executor-backed listen persistence boundary."""

import pytest

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


@pytest.mark.anyio
async def test_periodic_usage_loop_only_flushes_usage():
    """No plan is read and no silent-user notification is sent (#54): every user has full access."""
    from types import SimpleNamespace

    runtime = object.__new__(listen_runtime.ListenSessionRuntime)
    runtime.state = ListenSessionState()
    runtime.state.active = True
    flushes = []
    waits = iter([False, True])

    async def wait(seconds):
        return next(waits)

    async def flush_usage(*, final):
        flushes.append(final)
        return 0

    async def call(function, *args, **kwargs):
        raise AssertionError(f'unexpected persistence call: {function}')

    runtime.wait = wait
    runtime._flush_usage = flush_usage
    runtime.persistence = SimpleNamespace(call=call)

    await runtime._record_usage_periodically()

    assert flushes == [False]

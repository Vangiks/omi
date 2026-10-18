"""One chat-question counter across every realtime entry path, on every plan.

Shard S15 of the local-models free tier (decision 8): a push-to-talk turn is a
chat question. The number the gate reads is ``get_monthly_chat_usage(...)['questions']``.

Who debits it, per path:

* text chat and PTT — the chat request (``record_chat_quota_question``). The
  legacy relay is the voice shell only: the desktop client sends the relay's
  transcript through desktop chat, so the relay itself must never debit;
* the direct hub — ``/v2/realtime/usage``, idempotent when the client sends a
  turn id, the historical bare increment otherwise;
* minting a hub session — never.

These tests prove those writers fold into that one number exactly once, and
that the relay serves every session without reading a quota (the fork has no
plans, #3) while still recording each provider response as spend.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from google.cloud import firestore

import database.llm_usage as llm_usage_db
import database.user_usage as user_usage_db
from routers import desktop_realtime, omni_relay

UID = 'user-s15'
NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


# --- a Firestore double that materialises the writers' real payloads -----------------------


def _materialise(existing: Any, value: Any) -> Any:
    if isinstance(value, firestore.Increment):
        base = existing if isinstance(existing, (int, float)) and not isinstance(existing, bool) else 0
        return base + value.value
    if isinstance(value, dict):
        merged = dict(existing) if isinstance(existing, dict) else {}
        for key, inner in value.items():
            merged[key] = _materialise(merged.get(key), inner)
        return merged
    return value


class _Snapshot:
    def __init__(self, doc_id: str, data: dict[str, Any] | None) -> None:
        self.id = doc_id
        self.exists = data is not None
        self._data = data

    def to_dict(self) -> dict[str, Any] | None:
        return None if self._data is None else dict(self._data)


class _Document:
    def __init__(self, store: '_Store', path: tuple[str, ...]) -> None:
        self._store = store
        self.path = path
        self.id = path[-1]

    def collection(self, name: str) -> '_Collection':
        return _Collection(self._store, self.path + (name,))

    def get(self, _fields: list[str] | None = None, *, transaction: Any = None) -> _Snapshot:
        return _Snapshot(self.id, self._store.rows.get(self.path))

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        if self._store.fail_writes:
            raise RuntimeError('firestore unavailable')
        current = self._store.rows.get(self.path, {}) if merge else {}
        self._store.rows[self.path] = _materialise(current, data)


class _Collection:
    def __init__(self, store: '_Store', path: tuple[str, ...], filters: tuple[Any, ...] = ()) -> None:
        self._store = store
        self.path = path
        self._filters = filters

    def document(self, name: str) -> _Document:
        return _Document(self._store, self.path + (name,))

    def where(self, filter: Any) -> '_Collection':
        return _Collection(self._store, self.path, self._filters + (filter,))

    def stream(self):
        for path, data in list(self._store.rows.items()):
            if path[:-1] != self.path:
                continue
            doc_id = path[-1]
            ok = True
            for f in self._filters:
                assert f.field_path == '__name__'
                if f.op_string == '>=' and doc_id < f.value.id:
                    ok = False
                if f.op_string == '<' and doc_id >= f.value.id:
                    ok = False
            if ok:
                yield _Snapshot(doc_id, data)

    def list_documents(self):
        raise AssertionError('chat-quota reads must stay bounded to the current month')


class _Transaction:
    """Enough of the Firestore transaction lifecycle for ``@transactional``."""

    def __init__(self, store: '_Store') -> None:
        self._store = store
        self._staged: list[tuple[_Document, dict[str, Any], bool]] = []
        self._id: bytes | None = None
        self._read_only = False
        self._max_attempts = 1

    def _begin(self, retry_id: bytes | None = None) -> None:
        self._id = retry_id or b'txn'

    def _commit(self) -> None:
        # Writes are staged and applied only here, so a failed commit proves a
        # multi-document write is all-or-nothing.
        if self._store.fail_next_commit:
            self._store.fail_next_commit = False
            self._staged.clear()
            raise RuntimeError('commit failed')
        for ref, data, merge in self._staged:
            ref.set(data, merge=merge)
        self._staged.clear()

    def _rollback(self) -> None:
        self._staged.clear()

    def _clean_up(self) -> None:
        self._id = None

    def set(self, ref: _Document, data: dict[str, Any], merge: bool = False) -> None:
        self._staged.append((ref, data, merge))


class _Store:
    def __init__(self, *, plan: str = 'basic') -> None:
        self.rows: dict[tuple[str, ...], dict[str, Any]] = {('users', UID): {'subscription': {'plan': plan}}}
        self.fail_next_commit = False
        self.fail_writes = False

    def collection(self, name: str) -> _Collection:
        return _Collection(self, (name,))

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    def questions(self) -> int:
        return int(user_usage_db.get_monthly_chat_usage(UID, NOW, firestore_client=self)['questions'])


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return NOW if tz is None else NOW.astimezone(tz)


@pytest.fixture
def store(monkeypatch) -> _Store:
    store = _Store()
    monkeypatch.setattr(llm_usage_db, 'datetime', _FrozenDatetime)
    # user_usage resolves "this month" too; freeze it alongside the writers.
    monkeypatch.setattr(user_usage_db, 'datetime', _FrozenDatetime)
    monkeypatch.setattr(desktop_realtime, 'get_customer_firestore_client', lambda: store)
    return store


def _hub_report(turn_id: str = '') -> None:
    """The direct hub's write path, exactly as `/v2/realtime/usage` calls it."""
    desktop_realtime._record_usage(
        UID,
        desktop_realtime.UsageReport(provider='openai', input_audio_tokens=10, output_audio_tokens=5, turn_id=turn_id),
        input_tokens=10,
        output_tokens=5,
        cached_tokens=0,
        total_tokens=15,
        cost=0.001,
    )


def _chat_question(request_id: str) -> bool:
    """Text chat and PTT alike: the desktop chat router's own key shape."""
    return llm_usage_db.record_chat_quota_question(
        UID, f'desktop_chat_completions:{request_id}', 'desktop_chat_completions', platform='desktop'
    )


# --- the one counter ---------------------------------------------------------------------


def test_every_writer_folds_into_one_monthly_number(store, monkeypatch) -> None:
    monkeypatch.setattr(llm_usage_db, 'db', store)
    _hub_report()  # legacy client: bare increment
    _hub_report(turn_id='turn-1')  # new client: idempotent question
    assert _chat_question('req-1')  # a PTT or typed chat turn
    assert store.questions() == 3


def test_a_retried_hub_report_with_a_turn_id_counts_once(store) -> None:
    _hub_report(turn_id='turn-1')
    _hub_report(turn_id='turn-1')
    _hub_report(turn_id='turn-2')
    assert store.questions() == 2
    # Question and telemetry land in one transaction: two turns, two rows' worth of tokens, no more.
    day = store.rows[('users', UID, 'llm_usage', '2026-09-02')]
    assert day['desktop_chat']['input_tokens'] == 20
    assert day['desktop_chat']['call_count'] == 2
    assert day['desktop_chat'].get('quota_questions', 0) == 0  # the question is backend_chat's, not a second one
    assert day['backend_chat']['quota_questions'] == 2
    # Positive control for the negative: without a turn id the historical increment repeats.
    _hub_report()
    _hub_report()
    assert store.questions() == 4


def test_hub_telemetry_lands_on_the_question_transactions_own_day_and_plan(store, monkeypatch) -> None:
    """The telemetry is built inside the transaction from its plan key and day, not resolved separately."""
    seen: list[tuple[str, str]] = []
    real = llm_usage_db.usage_bucket_update

    def spy(uid, **kwargs):
        seen.append((kwargs['plan_key'], kwargs['today']))
        return real(uid, **kwargs)

    monkeypatch.setattr(llm_usage_db, 'usage_bucket_update', spy)
    _hub_report(turn_id='turn-1')
    assert seen == [('architect', '2026-09-02')]
    day = store.rows[('users', UID, 'llm_usage', '2026-09-02')]
    assert day['plan_usage']['architect']['desktop_chat']['input_tokens'] == 10
    assert day['plan_usage']['architect']['backend_chat']['quota_questions'] == 1


def test_a_hub_report_that_fails_to_commit_records_neither_question_nor_cost_and_retries_cleanly(store) -> None:
    store.fail_next_commit = True
    with pytest.raises(RuntimeError):
        _hub_report(turn_id='turn-1')
    assert store.questions() == 0
    assert ('users', UID, 'llm_usage', '2026-09-02') not in store.rows  # no telemetry without the question
    _hub_report(turn_id='turn-1')  # the retry is not mistaken for a duplicate
    assert store.questions() == 1
    assert store.rows[('users', UID, 'llm_usage', '2026-09-02')]['desktop_chat']['input_tokens'] == 10


def test_a_retried_chat_question_counts_once(store, monkeypatch) -> None:
    monkeypatch.setattr(llm_usage_db, 'db', store)
    assert _chat_question('req-1') is True
    assert _chat_question('req-1') is False
    assert store.questions() == 1


# --- the relay: no quota, never debits, still accounts ---------------------------------------


class _FakeUpstream:
    def __init__(self, frames: list[str | bytes], drained: asyncio.Event) -> None:
        self.frames = frames
        self._drained = drained

    async def send(self, _message: str | bytes) -> None:
        return None

    def __aiter__(self):
        return self._replay()

    async def _replay(self):
        for frame in self.frames:
            yield frame
        self._drained.set()
        await asyncio.Event().wait()


class _FakeConnect:
    def __init__(self, upstream: _FakeUpstream) -> None:
        self.upstream = upstream

    async def __aenter__(self) -> _FakeUpstream:
        return self.upstream

    async def __aexit__(self, *_: object) -> None:
        return None


class _Socket:
    headers = {'authorization': 'Bearer token'}

    def __init__(self, provider: str, drained: asyncio.Event) -> None:
        self.query_params = {'provider': provider}
        self.closes: list[dict[str, Any]] = []
        self.forwarded = 0
        self.accepted = False
        self._drained = drained

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, **kwargs: Any) -> None:
        self.closes.append(kwargs)

    async def send_text(self, _text: str) -> None:
        self.forwarded += 1

    async def send_bytes(self, _data: bytes) -> None:
        self.forwarded += 1

    async def receive(self) -> dict[str, Any]:
        await self._drained.wait()
        return {'type': 'websocket.disconnect'}


class _NoFirestore:
    """The relay has no quota to read: any Firestore access from it is a failure."""

    def collection(self, name: str):
        raise AssertionError(f'the relay read Firestore collection {name!r}')


def _no_quota_read(*_a, **_k):
    raise AssertionError('the relay read a chat quota')


async def _passthrough(_executor, fn, *args, **kwargs):
    return fn(*args, **kwargs)


def _created(response_id: str) -> str:
    return json.dumps({'type': 'response.created', 'response': {'id': response_id}})


def _done(tokens: int, response_id: str = 'r1') -> str:
    usage = {
        'input_tokens': tokens,
        'output_tokens': 0,
        'input_token_details': {'audio_tokens': tokens},
        'output_token_details': {},
    }
    return json.dumps({'type': 'response.done', 'response': {'id': response_id, 'status': 'completed', 'usage': usage}})


def _stub_relay(monkeypatch, *, byok: bool, provider: str, connect: Any) -> tuple[list[str], list[Any]]:
    """Stub the relay's edges; returns the question-writer calls and the scheduled ledger attempts."""
    writes: list[str] = []
    attempts: list[Any] = []
    validated = {provider: 'sk-user'} if byok else {}
    monkeypatch.setattr(omni_relay, 'raise_if_gateway_feature_mode_blocks_direct_model_surface', lambda _s: None)
    monkeypatch.setattr(omni_relay, '_verify_ws_auth', lambda _authz: UID)
    monkeypatch.setattr(omni_relay, 'extract_byok_from_websocket', lambda _ws: dict(validated))
    monkeypatch.setattr(omni_relay, 'validate_byok_websocket_keys', lambda _uid, keys: (dict(keys), None))
    monkeypatch.setattr(omni_relay, 'set_validated_byok_keys', lambda _keys, _uid: None)
    monkeypatch.setattr(omni_relay, 'get_chat_quota_snapshot', _no_quota_read, raising=False)
    monkeypatch.setattr(omni_relay, 'get_customer_firestore_client', lambda: _NoFirestore(), raising=False)
    monkeypatch.setattr(llm_usage_db, 'record_chat_quota_question', lambda *a, **k: writes.append('question'))
    monkeypatch.setattr(omni_relay, 'schedule_managed_attempt', lambda attempt: attempts.append(attempt) or True)
    monkeypatch.setattr(omni_relay, '_upstream', lambda _p, _m: (('wss://upstream.invalid', {}), None))
    monkeypatch.setattr(omni_relay.websockets, 'connect', connect)
    return writes, attempts


async def _run_relay(
    monkeypatch, *, frames: list[str | bytes], byok: bool = False, provider: str = 'openai'
) -> tuple[_Socket, list[str], list[Any]]:
    drained = asyncio.Event()
    upstream = _FakeUpstream(frames, drained)
    writes, attempts = _stub_relay(
        monkeypatch, byok=byok, provider=provider, connect=lambda *_a, **_k: _FakeConnect(upstream)
    )
    socket = _Socket(provider, drained)
    await omni_relay.omni_relay(socket)
    return socket, writes, attempts


@pytest.mark.asyncio
async def test_the_relay_never_debits_the_question_the_chat_request_owns(monkeypatch) -> None:
    socket, writes, _ = await _run_relay(monkeypatch, frames=[_done(30, 'a'), _done(30, 'b')])
    assert socket.accepted and socket.forwarded == 2
    assert writes == []


@pytest.mark.asyncio
async def test_a_managed_session_is_served_without_reading_a_quota(monkeypatch) -> None:
    """No plans in the fork (#3): an Omi-key session is admitted and served with no quota read at
    connect or at any response start, and closes normally."""
    socket, _, _ = await _run_relay(monkeypatch, frames=[_done(30, 'a'), _done(30, 'b'), _done(30, 'c')])
    assert socket.accepted and socket.forwarded == 3
    assert socket.closes == [{}]


@pytest.mark.asyncio
async def test_every_provider_response_is_still_recorded_as_spend(monkeypatch) -> None:
    """Spend accounting is not a quota and stays: one ledger attempt per response, payer by credential."""
    _, _, attempts = await _run_relay(monkeypatch, frames=[_done(30, 'a'), _done(30, 'b')])
    assert [(a.payer, a.ordinal) for a in attempts] == [('omi', 1), ('omi', 2)]
    _, _, attempts = await _run_relay(monkeypatch, frames=[_done(30, 'a')], byok=True)
    assert [a.payer for a in attempts] == ['byok']


@pytest.mark.asyncio
async def test_a_user_may_hold_any_number_of_relay_sockets_open(monkeypatch) -> None:
    """The per-user socket cap only bounded a quota race; without a quota there is nothing to cap."""
    count = 3
    all_served = asyncio.Event()
    sockets: list[_Socket] = []

    class HeldSocket(_Socket):
        async def send_text(self, text: str) -> None:
            await super().send_text(text)
            if sum(s.forwarded for s in sockets) == count:
                all_served.set()

    _stub_relay(
        monkeypatch,
        byok=False,
        provider='openai',
        connect=lambda *_a, **_k: _FakeConnect(_FakeUpstream([_done(30)], asyncio.Event())),
    )
    # Every socket stays open until all of them have been served, so they are open at once.
    sockets.extend(HeldSocket('openai', all_served) for _ in range(count))
    await asyncio.wait_for(asyncio.gather(*(omni_relay.omni_relay(s) for s in sockets)), timeout=5)
    assert all(s.accepted and s.forwarded == 1 for s in sockets)
    assert all(s.closes == [{}] for s in sockets)


def test_completed_response_identities_are_retained_past_a_thousand_responses() -> None:
    from utils.llm.realtime_usage import RealtimeRelayObserver

    observer = RealtimeRelayObserver('openai')
    for index in range(1002):
        observer.observe_upstream_frame(_created(f'r{index}'))
        observer.observe_upstream_frame(_done(30, f'r{index}'))
    assert observer.starts == 1002
    # A replay of the very first terminal frame, 1,001 responses later, is still recognised.
    assert observer.observe_upstream_frame(_done(30, 'r0')) == ()
    assert observer.starts == 1002


def test_open_response_identities_stay_exact_past_sixty_four_concurrent_responses() -> None:
    from utils.llm.realtime_usage import RealtimeRelayObserver

    observer = RealtimeRelayObserver('openai')
    for index in range(200):
        observer.observe_upstream_frame(_created(f'r{index}'))
    assert observer.starts == 200
    # A replayed announcement of the 65th response, or of the 200th, is not a new start.
    observer.observe_upstream_frame(_created('r64'))
    observer.observe_upstream_frame(_created('r199'))
    assert observer.starts == 200
    # An unannounced terminal response counts its own start and closes none of the 200 open ones.
    observer.observe_upstream_frame(_done(30, 'unannounced'))
    assert observer.starts == 201
    flushed = observer.flush()
    assert len(flushed) == 16 and observer.dropped_at_flush == 184  # all 200 still open, budgeted at the flush


@pytest.mark.asyncio
async def test_a_session_ends_at_the_identity_capacity_so_its_accounting_stays_exact(monkeypatch) -> None:
    """Identity is tracked per socket, so a session is ended (reconnect required) once it has started
    as many responses as the observer tracks. This is a technical limit, not a quota."""
    from utils.llm.realtime_usage import MAX_RESPONSES_PER_SESSION, RealtimeRelayObserver, _MAX_OPEN_RESPONSES

    assert MAX_RESPONSES_PER_SESSION < _MAX_OPEN_RESPONSES  # the refused response keeps its identity
    frames = [_created(f'r{i}') for i in range(MAX_RESPONSES_PER_SESSION + 5)]
    socket, _, _ = await _run_relay(monkeypatch, frames=frames)
    assert socket.forwarded == MAX_RESPONSES_PER_SESSION  # the response past the limit is never delivered
    assert socket.closes[-1] == {'code': 1008, 'reason': 'response_limit'}
    observer = RealtimeRelayObserver('openai')
    for frame in frames[: MAX_RESPONSES_PER_SESSION + 1]:
        observer.observe_upstream_frame(frame)
    assert observer._openai_overflow == 0
    assert (
        observer.observe_upstream_frame(_created(f'r{MAX_RESPONSES_PER_SESSION}')) == ()
        and observer.starts == MAX_RESPONSES_PER_SESSION + 1
    )


@pytest.mark.asyncio
async def test_a_cancelled_handler_drains_its_pumps(monkeypatch) -> None:
    """If the handler itself is cancelled while both pumps are pending, the pumps must not outlive it."""
    hold = asyncio.Event()
    upstream_blocked = asyncio.Event()
    client_blocked = asyncio.Event()

    class HoldingUpstream(_FakeUpstream):
        async def _replay(self):
            upstream_blocked.set()  # the upstream pump is now parked in its iterator
            await hold.wait()
            yield ''  # never reached

    class BlockingSocket(_Socket):
        async def receive(self) -> dict[str, Any]:
            client_blocked.set()  # the client pump is now parked in receive()
            return await super().receive()

    drained = asyncio.Event()
    upstream = HoldingUpstream([], drained)
    _stub_relay(monkeypatch, byok=False, provider='openai', connect=lambda *_a, **_k: _FakeConnect(upstream))
    socket = BlockingSocket('openai', drained)  # receive() also blocks: both pumps stay pending

    handler = asyncio.create_task(omni_relay.omni_relay(socket))
    await asyncio.wait_for(asyncio.gather(upstream_blocked.wait(), client_blocked.wait()), timeout=5)
    pumps = [t for t in asyncio.all_tasks() if (t.get_name() or '').startswith(f'ws:{UID}:omni_')]
    assert len(pumps) == 2
    handler.cancel()
    with pytest.raises(asyncio.CancelledError):
        await handler
    assert all(t.done() for t in pumps)  # drained, not orphaned


def test_a_gemini_usage_block_with_no_tokens_is_not_evidence_of_a_response() -> None:
    from utils.llm.realtime_usage import RealtimeRelayObserver

    observer = RealtimeRelayObserver('gemini')
    observer.observe_upstream_frame(b'{"usageMetadata": {"promptTokenCount": 0, "responseTokenCount": 0}}')
    observer.observe_upstream_frame(b'{"serverContent": {"turnComplete": true}}')
    assert observer.starts == 0
    # Positive control: a usage block that adds tokens is (fresh session, so it is not trailing usage).
    observer = RealtimeRelayObserver('gemini')
    observer.observe_upstream_frame(b'{"usageMetadata": {"promptTokenCount": 5, "responseTokenCount": 1}}')
    assert observer.starts == 1
    observer.observe_upstream_frame(b'{"serverContent": {"turnComplete": true}}')
    assert observer.starts == 1  # the boundary does not start a second response


def test_gemini_activity_is_parsed_evidence_not_a_substring_match() -> None:
    """A tool call opens a response (real activity); a frame whose text merely mentions the markers
    inside a string is not activity and neither starts nor ends anything."""
    from utils.llm.realtime_usage import RealtimeRelayObserver

    decoy = json.dumps({'serverContent': {'inputTranscription': {'text': 'say "turnComplete": true and "modelTurn"'}}})
    tool_call = json.dumps({'toolCall': {'functionCalls': [{'name': 'note', 'args': {}}]}})
    real_end = json.dumps({'serverContent': {'turnComplete': True}})
    observer = RealtimeRelayObserver('gemini')
    observer.observe_upstream_frame(decoy.encode())
    observer.observe_upstream_frame(decoy.encode())
    assert observer.starts == 0
    observer.observe_upstream_frame(tool_call.encode())
    assert observer.starts == 1
    observer.observe_upstream_frame(real_end.encode())
    observer.observe_upstream_frame(tool_call.encode())
    assert observer.starts == 2


def test_openai_responses_start_once_whether_or_not_they_were_announced() -> None:
    from utils.llm.realtime_usage import RealtimeRelayObserver

    observer = RealtimeRelayObserver('openai')
    observer.observe_upstream_frame(_created('a'))
    assert observer.starts == 1
    observer.observe_upstream_frame(_done(30, 'a'))
    assert observer.starts == 1  # the done of an announced response is not a second start
    observer.observe_upstream_frame(_done(30, 'b'))
    assert observer.starts == 2  # a done that was never announced still started


def test_openai_starts_are_keyed_to_response_identity() -> None:
    from utils.llm.realtime_usage import RealtimeRelayObserver

    observer = RealtimeRelayObserver('openai')
    observer.observe_upstream_frame(_created('a'))
    observer.observe_upstream_frame(_created('a'))  # a replayed announcement is not a second response
    assert observer.starts == 1
    # An unannounced response B finishing while A is still open is B's start, and does not close A.
    rows = observer.observe_upstream_frame(_done(30, 'b'))
    assert observer.starts == 2 and len(rows) == 1
    assert [t.provider_response_id for t in observer.flush()] == ['a']  # A was still open at disconnect
    # A replayed terminal frame for a finished response is neither a row nor a start.
    observer = RealtimeRelayObserver('openai')
    observer.observe_upstream_frame(_created('c'))
    assert len(observer.observe_upstream_frame(_done(30, 'c'))) == 1
    assert observer.observe_upstream_frame(_done(30, 'c')) == ()
    assert observer.starts == 1


# --- the hub: minting is not a question ------------------


@pytest.mark.asyncio
async def test_minting_a_session_debits_nothing(monkeypatch) -> None:
    """A rewarm mint (#12331 class) and a turn mint look identical here; neither may consume quota."""
    monkeypatch.setenv('OPENAI_API_KEY', 'platform-key')

    async def post_json(*_a, **_k):
        return {'value': 'ek_secret', 'expires_at': 1}, None

    async def persist(*_a):
        return None

    def forbidden(*_a, **_k):
        raise AssertionError('a mint must not touch the chat counter')

    monkeypatch.setattr(desktop_realtime, '_post_json', post_json)
    monkeypatch.setattr(desktop_realtime, '_persist_session', persist)
    monkeypatch.setattr(desktop_realtime.llm_usage_db, 'record_llm_usage_bucket', forbidden)
    monkeypatch.setattr(desktop_realtime.llm_usage_db, 'record_chat_quota_question', forbidden)

    response = await desktop_realtime.mint_session(desktop_realtime.MintRequest(provider='openai'), UID)
    assert response.status_code == 200

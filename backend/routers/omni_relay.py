import asyncio
import logging
import os
from typing import cast
from urllib.parse import quote
from uuid import uuid4

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, WebSocketException

from utils.byok import (
    BYOK_HEADERS,
    extract_byok_from_websocket,
    get_byok_key,
    set_validated_byok_keys,
    validate_byok_websocket_keys,
)
from utils.async_tasks import drain_tasks
from utils.executors import db_executor, run_blocking
from utils.llm.gateway_client import raise_if_gateway_feature_mode_blocks_direct_model_surface
from utils.llm.managed_spend_ledger import (
    DESKTOP_REALTIME_FEATURE,
    OMNI_RELAY_CALLER,
    ManagedAttempt,
    schedule_managed_attempt,
)
from utils.llm.realtime_usage import (
    DEFAULT_REALTIME_MODELS,
    MAX_RESPONSES_PER_SESSION,
    RealtimeRelayObserver,
    RealtimeTurnUsage,
    price_realtime_turn,
    realtime_turn_metadata,
)
from utils.other.endpoints import _verify_ws_auth, run_critical_ws  # type: ignore[reportPrivateUsage]  # shared WS auth helper, intentionally reused cross-module
from utils.subscription import is_trial_paywalled

router = APIRouter()
logger = logging.getLogger(__name__)


# Realtime "omni" relay.
#
# The desktop floating bar connects here (authenticated, like /v4/listen) and we
# pipe every frame, verbatim, to the chosen provider's realtime WebSocket. This
# exists because:
#   1) Apple's WebSocket stacks (URLSessionWebSocketTask / Network.framework)
#      cannot hold a direct connection to Gemini's Live endpoint (Google's
#      frontend resets them); a server-side `websockets` client connects fine.
#   2) Provider API keys stay server-side instead of shipping in the client.
#
# Protocol is provider-native and opaque to the relay — the desktop speaks raw
# OpenAI Realtime / Gemini Live JSON; we just forward bytes both ways.

# Leftover AI Studio Live websocket. Vertex Live is not wired here; this is
# not the $1k/day Flash text bill. See backend/docs/vertex-pt-flash.md.
GEMINI_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={key}"
)
OPENAI_URL = "wss://api.openai.com/v1/realtime?model={model}"
OPENAI_DEFAULT_MODEL = DEFAULT_REALTIME_MODELS["openai"]


def _relay_turn_attempt(
    *,
    session_id: str,
    uid: str,
    provider: str,
    model: str,
    payer: str,
    ordinal: int,
    turn: RealtimeTurnUsage,
) -> ManagedAttempt:
    """The ledger row for one provider response observed on the relay.

    Every turn of a session shares one invocation id and takes the next
    ordinal, so a session's turns group in the ledger the way a gateway
    request's retries do.
    """
    return ManagedAttempt(
        request_id=session_id,
        caller=OMNI_RELAY_CALLER,
        user_uid=uid,
        feature=DESKTOP_REALTIME_FEATURE,
        api_surface=f"{provider}_realtime_websocket",
        payer=payer,
        provider=provider,
        configured_model=model or "unknown",
        outcome=turn.outcome,
        error_class=turn.error_class,
        route_artifact_id=f"{OMNI_RELAY_CALLER}.{provider}",
        metadata=realtime_turn_metadata(turn),
        # None when usage was not reported or the model has no rate table: the
        # row stays `unpriced` rather than a confident zero.
        priced=price_realtime_turn(turn, model),
        invocation_id=session_id,
        ordinal=ordinal,
    )


def _upstream(provider: str, model: str | None) -> tuple[tuple[str, dict[str, str]], None] | tuple[None, str]:
    """Return (url, headers) for the chosen provider, or (None, reason).

    Prefers the caller's BYOK key (so BYOK users pay their own way, same as the
    rest of the API); falls back to the platform key for entitled non-BYOK users.
    """
    if provider == "gemini":
        key = get_byok_key("gemini") or os.getenv("GEMINI_API_KEY")
        if not key:
            return None, "no Gemini key (BYOK or platform)"
        return (GEMINI_URL.format(key=key), {}), None
    if provider == "openai":
        key = get_byok_key("openai") or os.getenv("OPENAI_API_KEY")
        if not key:
            return None, "no OpenAI key (BYOK or platform)"
        # URL-encode the client-supplied model so it can't inject extra query params.
        url = OPENAI_URL.format(model=quote(model or "gpt-realtime-2", safe=""))
        return (url, {"Authorization": f"Bearer {key}"}), None
    return None, f"unsupported provider: {provider}"


@router.websocket("/v1/omni/relay")
async def omni_relay(websocket: WebSocket):
    try:
        raise_if_gateway_feature_mode_blocks_direct_model_surface('omni_realtime.provider_websocket')
    except RuntimeError as exc:
        await websocket.close(code=1013, reason=str(exc)[:120])
        return

    # Manual auth (read the header directly so we control logging and avoid any
    # WS header-DI surprises). Token first, then BYOK validate, then the gate.
    authz = websocket.headers.get("authorization")
    byok_present = [p for p, h in BYOK_HEADERS.items() if websocket.headers.get(h)]
    logger.info(
        f"omni relay connect: auth_present={bool(authz)} byok={byok_present} "
        f"provider={websocket.query_params.get('provider')}"
    )
    try:
        uid = await run_critical_ws(_verify_ws_auth, cast(str, authz))
    except WebSocketException as e:
        logger.warning(f"omni relay auth rejected: code={e.code} reason={e.reason}")
        await websocket.close(code=e.code, reason=e.reason or "unauthorized")
        return

    # BYOK: validate forwarded keys (same as /v4/listen). Keys then resolve via get_byok_key.
    byok = extract_byok_from_websocket(websocket)
    validated_byok, byok_err = await run_critical_ws(validate_byok_websocket_keys, uid, byok)
    if byok_err:
        logger.warning(f"omni relay BYOK invalid uid={uid}: {byok_err}")
        await websocket.close(code=4003, reason=byok_err)
        return
    set_validated_byok_keys(validated_byok, uid)

    provider = websocket.query_params.get("provider", "gemini")
    if provider not in {"gemini", "openai"}:
        await websocket.close(code=1011, reason=f"unsupported provider: {provider}"[:120])
        return

    # Same desktop gate as /v4/listen: Operator/Architect + BYOK pass; un-entitled
    # desktop users past their trial are paywalled.
    if await run_blocking(db_executor, is_trial_paywalled, uid, "desktop", required_byok_provider=provider):
        logger.info(f"omni relay paywalled uid={uid}")
        await websocket.close(code=1008, reason="trial_expired")
        return

    await _relay_session(websocket, uid, provider, validated_byok)


async def _relay_session(websocket: WebSocket, uid: str, provider: str, validated_byok: dict[str, str]) -> None:
    """An admitted relay session: provider connection, the two pumps and spend accounting."""
    model = websocket.query_params.get("model")
    upstream_cfg, err = _upstream(provider, model)
    if err:
        await websocket.close(code=1011, reason=err)
        return
    url, headers = cast(tuple[str, dict[str, str]], upstream_cfg)

    # Spend attribution: each billable provider response the relay forwards
    # becomes one `llm_gateway_attempts` row (best-effort, never on the audio
    # path's critical section). BYOK sessions are recorded as not Omi cost.
    session_id = str(uuid4())
    # Who the provider bills is decided by the credential `_upstream` actually
    # selects — a validated key for this provider — not by enrollment. An
    # unenrolled user with a valid key still pays the provider directly.
    payer = "byok" if validated_byok.get(provider) else "omi"
    observer = RealtimeRelayObserver(provider, model=(model or OPENAI_DEFAULT_MODEL) if provider == "openai" else model)

    class SessionLimit(Exception):
        """Raised inside the pump when the session has started as many responses as it can account for."""

    def record_turn(turn: RealtimeTurnUsage) -> None:
        schedule_managed_attempt(
            _relay_turn_attempt(
                session_id=session_id,
                uid=uid,
                provider=provider,
                model=observer.model,
                payer=payer,
                ordinal=turn.ordinal,
                turn=turn,
            )
        )

    def account_upstream_frame(message: str | bytes | bytearray) -> None:
        # Accounting never gets to end a session: it runs before the frame
        # is forwarded, and anything it throws is our bug, not the user's.
        try:
            for turn in observer.observe_upstream_frame(message):
                record_turn(turn)
        except Exception:
            logger.warning("omni relay accounting failed provider=%s", provider)

    def account_session_end() -> None:
        try:
            for turn in observer.flush():
                record_turn(turn)
            if observer.dropped_at_flush:
                logger.warning(
                    "omni relay accounting dropped %d open responses at session end provider=%s",
                    observer.dropped_at_flush,
                    provider,
                )
        except Exception:
            logger.warning("omni relay accounting flush failed provider=%s", provider)

    limit_reason: str | None = None
    await websocket.accept()
    try:
        async with websockets.connect(
            url, extra_headers=headers or None, max_size=None, ping_interval=20, ping_timeout=20
        ) as upstream:

            async def client_to_upstream():
                while True:
                    msg = await websocket.receive()
                    if msg.get("type") == "websocket.disconnect":
                        return
                    if (text := msg.get("text")) is not None:
                        await upstream.send(text)
                        observer.observe_client_frame(text)
                    elif (data := msg.get("bytes")) is not None:
                        await upstream.send(data)
                        observer.observe_client_frame(data)

            async def upstream_to_client():
                async for message in upstream:
                    # Spend accounting is off the request path (a background write).
                    starts_before = observer.starts
                    account_upstream_frame(message)
                    if observer.starts > starts_before and observer.starts > MAX_RESPONSES_PER_SESSION:
                        # Response identity is tracked per socket; past this
                        # many responses it would stop being exact, so the
                        # session ends before the frame is forwarded and a
                        # reconnect starts a fresh observer.
                        logger.info(f"omni relay session response limit uid={uid}")
                        raise SessionLimit("response_limit")
                    if isinstance(message, (bytes, bytearray)):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            pumps = {
                asyncio.create_task(client_to_upstream(), name=f"ws:{uid}:omni_c2u"),
                asyncio.create_task(upstream_to_client(), name=f"ws:{uid}:omni_u2c"),
            }
            done: set[asyncio.Task[None]] = set()
            try:
                done, _pending = await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
            finally:
                # This handler owns the pumps: whichever way it leaves —
                # a pump finished, or the handler itself was cancelled
                # mid-wait — the other pump is drained, bounded, before
                # accounting flushes and the socket closes, so nothing
                # resumes on a dead session.
                await drain_tasks(pumps, timeout=5.0, label="omni_relay_pump", cancel=True)
            for t in done:
                exc = t.exception()
                if isinstance(exc, SessionLimit):
                    limit_reason = str(exc)
                elif exc:
                    logger.warning(f"omni relay task ended: {exc}")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"omni relay error (uid={uid}, provider={provider}): {e}")
    finally:
        # A response still in flight when the socket ends was a provider
        # attempt too; it is recorded as cancelled with whatever usage arrived.
        account_session_end()
        try:
            if limit_reason is not None:
                await websocket.close(code=1008, reason=limit_reason)
            else:
                await websocket.close()
        except Exception:
            pass

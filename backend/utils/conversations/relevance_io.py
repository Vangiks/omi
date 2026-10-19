"""The I/O side of the relevance step: lookups and recording.

``relevance.py`` stays pure (policy and tiers); this module holds what touches
Firestore or metrics, so ``process_conversation`` only wires them together.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from database import conversations as conversations_db
from utils.conversation_continuity import DEFAULT_GAP_SECONDS
from utils.conversations.relevance import (
    Neighbor,
    RelevanceDecision,
    find_neighbor,
)
from utils.integration_telemetry import emit_posthog_event
from utils.metrics import record_conversation_relevance

logger = logging.getLogger(__name__)

NEIGHBOR_CANDIDATE_LIMIT = 10


def adjacent_conversation(uid: str, conversation: Any, conversation_id: Optional[str]) -> Optional[Neighbor]:
    """A kept conversation this one would have joined had capture not split it (fail-open)."""
    started_at, finished_at = conversation.started_at, conversation.finished_at
    if started_at is None or finished_at is None:
        return None
    try:
        rows = conversations_db.get_conversations_finished_after(
            uid,
            status='completed',
            finished_after=started_at - timedelta(seconds=DEFAULT_GAP_SECONDS),
            limit=NEIGHBOR_CANDIDATE_LIMIT,
        )
    except Exception as error:
        logger.warning('relevance neighbor lookup failed uid=%s: %s', uid, error)
        return None
    return find_neighbor(
        rows,
        conversation_id=conversation_id or getattr(conversation, 'id', None),
        started_at=started_at,
        finished_at=finished_at,
        gap_seconds=DEFAULT_GAP_SECONDS,
    )


def record_decision(decision: RelevanceDecision) -> None:
    record_conversation_relevance(
        trigger=decision.trigger.value,
        verdict=decision.verdict,
        decided_by=decision.decided_by,
        reason=decision.reason,
    )


def emit_recorded_decision(uid: str, conversation_id: str, decision: RelevanceDecision) -> None:
    """Enqueue one content-free event after a final decision is successfully stored.

    The shared PostHog helper uses the SDK's background capture queue. Optional
    analytics must never fail conversation processing, even if capture raises.
    """
    try:
        properties: dict[str, Any] = {
            'conversation_id': str(conversation_id),
            'reason': decision.reason,
            'discarded': decision.discard,
        }
        if decision.arm is not None:
            properties['arm'] = decision.arm
        emit_posthog_event(uid, 'Relevance Decision Recorded', properties)
    except Exception as error:
        logger.warning('relevance analytics capture failed error=%s', type(error).__name__)

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from services import conversation_finalization
from utils.observability import journeys

def _install_journey_metrics(monkeypatch):
    accepted = MagicMock()
    terminal = MagicMock()
    latency = MagicMock()
    reconciliations = MagicMock()
    monkeypatch.setattr(journeys, 'OMI_JOURNEY_ACCEPTED_TOTAL', accepted)
    monkeypatch.setattr(journeys, 'OMI_JOURNEY_TERMINAL_TOTAL', terminal)
    monkeypatch.setattr(journeys, 'OMI_JOURNEY_LATENCY_SECONDS', latency)
    monkeypatch.setattr(journeys, 'OMI_CAPTURE_FINALIZATION_RECONCILIATIONS_TOTAL', reconciliations)
    accepted.labels.return_value = MagicMock()
    terminal.labels.return_value = MagicMock()
    latency.labels.return_value = MagicMock()
    reconciliations.labels.return_value = MagicMock()
    return accepted, terminal, latency, reconciliations


def test_journey_contract_uses_only_closed_privacy_safe_labels(monkeypatch):
    accepted, terminal, latency, reconciliations = _install_journey_metrics(monkeypatch)

    journeys.record_journey_accepted('pusher_session')
    journeys.record_journey_terminal('pusher_session', 'cancelled', 1.5)
    journeys.record_capture_finalization_reconciliation('requeued')

    accepted.labels.assert_called_once_with(journey='pusher_session')
    terminal.labels.assert_called_once_with(journey='pusher_session', outcome='cancelled')
    latency.labels.assert_called_once_with(journey='pusher_session', outcome='cancelled')
    reconciliations.labels.assert_called_once_with(outcome='requeued')
    with pytest.raises(ValueError, match='unknown journey'):
        journeys.record_journey_accepted('user-123')
    with pytest.raises(ValueError, match='unknown journey outcome'):
        journeys.record_journey_terminal('chat_response', 'raw exception text', 1.0)


def test_capture_terminal_uses_persisted_acceptance_time(monkeypatch):
    _accepted, terminal, latency, _reconciliations = _install_journey_metrics(monkeypatch)
    accepted_at = datetime.now(timezone.utc) - timedelta(seconds=5)

    journeys.record_capture_finalization_terminal('success', accepted_at)

    terminal.labels.assert_called_once_with(journey='capture_finalization', outcome='success')
    latency.labels.assert_called_once_with(journey='capture_finalization', outcome='success')
    observed = latency.labels.return_value.observe.call_args.args[0]
    assert 4.0 <= observed <= 6.0


def test_terminal_finalization_failure_records_once_after_dead_letter(monkeypatch):
    dead_letter = MagicMock(return_value=True)
    accepted_at = datetime.now(timezone.utc) - timedelta(seconds=12)
    terminal = MagicMock()
    monkeypatch.setattr(conversation_finalization.jobs_db, 'mark_finalization_dead_letter', dead_letter)
    monkeypatch.setattr(
        conversation_finalization.jobs_db,
        'get_finalization_job',
        MagicMock(return_value={'created_at': accepted_at}),
    )
    monkeypatch.setattr(conversation_finalization, 'LISTEN_FINALIZATION_DEAD_LETTER_TOTAL', MagicMock())
    monkeypatch.setattr(conversation_finalization, 'record_capture_finalization_terminal', terminal)

    assert conversation_finalization.final_attempt_failed('job-1', 2, 3, 4) is True

    dead_letter.assert_called_once_with('job-1', 2, 3, 4, firestore_client=None)
    terminal.assert_called_once_with('failure', accepted_at)


def test_listener_projects_the_closed_durable_finalization_states(monkeypatch):
    durable = MagicMock()
    durable.labels.return_value = MagicMock()
    backlog = MagicMock()
    backlog.labels.return_value = MagicMock()
    monkeypatch.setattr(
        conversation_finalization.jobs_db,
        'get_finalization_job_summary',
        MagicMock(
            return_value={
                'accepted': 9,
                'success': 3,
                'failure': 1,
                'stale': 2,
                'nonterminal': 1,
                'blocked_byok': 1,
                'terminal_unknown': 1,
                'queued': 1,
                'leased': 0,
                'dead_letter': 1,
                'oldest_nonterminal_age_seconds': 12.5,
                'oldest_blocked_byok_age_seconds': 42.0,
            }
        ),
    )
    monkeypatch.setattr(conversation_finalization, 'LISTEN_FINALIZATION_DURABLE_JOBS', durable)
    monkeypatch.setattr(conversation_finalization, 'LISTEN_FINALIZATION_JOB_STATUS', backlog)
    monkeypatch.setattr(conversation_finalization, 'LISTEN_FINALIZATION_OLDEST_NONTERMINAL_AGE_SECONDS', MagicMock())

    blocked_age = MagicMock()
    monkeypatch.setattr(conversation_finalization, 'LISTEN_FINALIZATION_OLDEST_BLOCKED_BYOK_AGE_SECONDS', blocked_age)
    conversation_finalization._publish_job_metrics()
    blocked_age.set.assert_called_once_with(42.0)

    assert {call.kwargs['state'] for call in durable.labels.call_args_list} == {
        'accepted',
        'success',
        'failure',
        'stale',
        'nonterminal',
        'blocked_byok',
        'terminal_unknown',
    }

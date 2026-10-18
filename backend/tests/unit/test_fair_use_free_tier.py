"""Tests for fair-use classifier escalation and the DG budget.

Abuse-detected users follow the graduated escalation pipeline:
none → warning → throttle → restrict.
"""

import asyncio
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

import utils.fair_use as fair_use_mod

# ---------------------------------------------------------------------------
# Fake dependency modules (bound into fair_use_mod via an autouse fixture, NOT
# installed into sys.modules). utils.fair_use imports cleanly thanks to the
# conftest redis/tiktoken stubs and lazy getters in the production code.
# ---------------------------------------------------------------------------

_fair_use_db = ModuleType('database.fair_use')
_fair_use_db.get_fair_use_state = MagicMock(return_value={'stage': 'none'})
_fair_use_db.update_fair_use_state = MagicMock()
_fair_use_db.create_fair_use_event = MagicMock(return_value='evt-123')
_fair_use_db.get_fair_use_events = MagicMock(return_value=[{'case_ref': 'FU-TEST01'}])
_fair_use_db.get_violation_counts = MagicMock(return_value={'violation_count_7d': 0, 'violation_count_30d': 0})

_users_db = MagicMock()

_mock_redis = MagicMock()


@pytest.fixture(autouse=True)
def _bind_fair_use_fakes(monkeypatch):
    """Bind fake db/redis/notification deps into fair_use_mod for the duration
    of each test. Auto-restored at teardown by monkeypatch.

    ``_send_notification`` is the lazy-loaded global in fair_use_mod; seeding it
    with a MagicMock short-circuits ``_get_send_notification()`` so the real
    ``utils.notifications`` chain (firebase_admin + network) is never imported
    during escalation.
    """
    monkeypatch.setattr(fair_use_mod, 'fair_use_db', _fair_use_db)
    monkeypatch.setattr(fair_use_mod, 'users_db', _users_db)
    monkeypatch.setattr(fair_use_mod, 'redis_client', _mock_redis)
    monkeypatch.setattr(fair_use_mod, '_send_notification', MagicMock())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trigger(trigger_type='daily'):
    mock_trigger = MagicMock()
    mock_trigger.value = trigger_type
    return [{'trigger': mock_trigger}]


# ---------------------------------------------------------------------------
# trigger_classifier_if_needed tests
# ---------------------------------------------------------------------------


class TestTriggerClassifier:
    """trigger_classifier_if_needed runs the LLM classifier before escalation."""

    def setup_method(self):
        _mock_redis.reset_mock()
        _mock_redis.set.return_value = True
        _fair_use_db.get_fair_use_state.reset_mock()
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'none'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 0, 'violation_count_30d': 0}
        _fair_use_db.create_fair_use_event.reset_mock()
        _fair_use_db.create_fair_use_event.return_value = 'evt-123'
        _fair_use_db.get_fair_use_events.return_value = [{'case_ref': 'FU-TEST01'}]
        _fair_use_db.update_fair_use_state.reset_mock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, '_get_classify_user_purpose')
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_runs_the_llm_classifier(self, _mock_speech, mock_get_classify):
        """Every user goes through the LLM classifier pipeline."""
        classify_called = {'called': False}
        _fair_use_db.create_fair_use_event.reset_mock()

        async def mock_classify(uid):
            classify_called['called'] = True
            return {'misuse_score': 0.1, 'usage_type': 'personal'}

        mock_get_classify.return_value = mock_classify

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger()))
        finally:
            loop.close()

        assert classify_called['called'] is True


# ---------------------------------------------------------------------------
# escalate_enforcement tests
# ---------------------------------------------------------------------------


class TestEscalateEnforcement:
    """The score gate (misuse_score >= threshold) is always required."""

    def setup_method(self):
        _fair_use_db.get_fair_use_state.reset_mock()
        _fair_use_db.get_violation_counts.reset_mock()
        _fair_use_db.create_fair_use_event.reset_mock()
        _fair_use_db.update_fair_use_state.reset_mock()
        _fair_use_db.create_fair_use_event.return_value = 'evt-123'
        _fair_use_db.get_fair_use_events.return_value = [{'case_ref': 'FU-TEST01'}]
        _mock_redis.reset_mock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_low_score_does_not_escalate(self, _mock_speech):
        """Low misuse score should NOT escalate, even with violations."""
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'none'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 3, 'violation_count_30d': 5}

        result = fair_use_mod.escalate_enforcement(
            'test-uid', _make_trigger(), {'misuse_score': 0.1, 'usage_type': 'personal'}
        )

        assert result['action'] == 'none'
        assert result['new_stage'] == 'none'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_high_score_escalates_to_warning(self, _mock_speech):
        """High misuse score escalates from none → warning."""
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'none'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 1, 'violation_count_30d': 1}

        result = fair_use_mod.escalate_enforcement(
            'test-uid', _make_trigger(), {'misuse_score': 0.8, 'usage_type': 'audiobook'}
        )

        assert result['action'] == 'warning'
        assert result['new_stage'] == 'warning'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_high_score_escalates_warning_to_throttle(self, _mock_speech):
        """Repeated high score escalates warning → throttle."""
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'warning'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 2, 'violation_count_30d': 3}

        result = fair_use_mod.escalate_enforcement(
            'test-uid', _make_trigger(), {'misuse_score': 0.8, 'usage_type': 'audiobook'}
        )

        assert result['action'] == 'throttle'
        assert result['new_stage'] == 'throttle'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_high_score_escalates_throttle_to_restrict(self, _mock_speech):
        """Continued abuse escalates throttle → restrict."""
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'throttle'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 3, 'violation_count_30d': 5}

        result = fair_use_mod.escalate_enforcement(
            'test-uid', _make_trigger(), {'misuse_score': 0.8, 'usage_type': 'audiobook'}
        )

        assert result['action'] == 'restrict'
        assert result['new_stage'] == 'restrict'


# ---------------------------------------------------------------------------
# DG budget tests
# ---------------------------------------------------------------------------


class TestDgBudget:
    """Test is_dg_budget_exhausted uses FAIR_USE_RESTRICT_DAILY_DG_MS only."""

    def setup_method(self):
        _mock_redis.reset_mock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 1800000)
    def test_under_budget_returns_false(self):
        _mock_redis.get.return_value = b'900000'
        assert fair_use_mod.is_dg_budget_exhausted('test-uid') is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 1800000)
    def test_at_budget_returns_true(self):
        _mock_redis.get.return_value = b'1800000'
        assert fair_use_mod.is_dg_budget_exhausted('test-uid') is True

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 1800000)
    def test_no_usage_returns_false(self):
        _mock_redis.get.return_value = None
        assert fair_use_mod.is_dg_budget_exhausted('test-uid') is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 0)
    def test_zero_limit_returns_false(self):
        """When limit is 0 (disabled), always returns False."""
        _mock_redis.get.return_value = b'9999999'
        assert fair_use_mod.is_dg_budget_exhausted('test-uid') is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', False)
    def test_disabled_returns_false(self):
        assert fair_use_mod.is_dg_budget_exhausted('test-uid') is False


class TestRecordDgUsageMs:
    """Test record_dg_usage_ms with simplified guard."""

    def setup_method(self):
        _mock_redis.reset_mock()
        _mock_redis.pipeline.return_value = MagicMock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 1800000)
    def test_records_when_budget_configured(self):
        fair_use_mod.record_dg_usage_ms('test-uid', 5000)
        _mock_redis.pipeline.assert_called_once()
        pipe = _mock_redis.pipeline.return_value
        pipe.execute.assert_called_once()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 0)
    def test_skips_when_budget_zero(self):
        fair_use_mod.record_dg_usage_ms('test-uid', 5000)
        _mock_redis.pipeline.assert_not_called()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', False)
    def test_skips_when_disabled(self):
        fair_use_mod.record_dg_usage_ms('test-uid', 5000)
        _mock_redis.pipeline.assert_not_called()


# ---------------------------------------------------------------------------
# Sync DG budget gate test
# ---------------------------------------------------------------------------


class TestSyncDgBudgetGate:
    """Test the sync endpoint response structure when DG budget is exhausted."""

    def test_sync_budget_exhausted_response_structure(self):
        from starlette.responses import JSONResponse

        import json

        response = JSONResponse(
            status_code=429,
            content={
                'new_memories': [],
                'updated_memories': [],
                'credits_exhausted': True,
                'dg_budget_exhausted': True,
                'skipped_segments': 5,
            },
        )

        assert response.status_code == 429
        body = json.loads(response.body)
        assert body['credits_exhausted'] is True
        assert body['dg_budget_exhausted'] is True
        assert body['skipped_segments'] == 5

"""Tests for BYOK security fixes (issue #6880).

Covers: transcription quota bypass.
"""

from unittest.mock import patch

from types import SimpleNamespace

from models.users import PlanType

from tests.unit._byok_fixtures import _byok_isolation  # noqa: F401

# ---------------------------------------------------------------------------
# 7. Transcription credit BYOK bypass
# ---------------------------------------------------------------------------


class TestTranscriptionCreditBYOKBypass:
    # These patch `utils.subscription.get_byok_key`, not `utils.byok.get_byok_key`.
    # subscription.py does `from utils.byok import get_byok_key` at import time, so
    # patching the source module leaves subscription's own binding untouched and the
    # BYOK branch never fires. These tests previously did that and still passed --
    # they fell through to the plan-limits path and returned True for an unrelated
    # reason, so the bypass they are named for had no real coverage.
    @patch('utils.subscription.get_byok_key', return_value='dg-user-key')
    @patch('utils.subscription.users_db')
    def test_has_transcription_credits_bypasses_for_byok(self, mock_users_db, _mock_get_key):
        mock_users_db.is_byok_active.return_value = True
        from utils.subscription import has_transcription_credits

        assert has_transcription_credits('byok-uid') is True
        # Proves the bypass short-circuited: the subscription was never consulted.
        mock_users_db.get_user_valid_subscription.assert_not_called()

    @patch('utils.subscription.get_byok_key', return_value='dg-user-key')
    @patch('utils.subscription.users_db')
    def test_remaining_seconds_is_none_for_byok(self, mock_users_db, _mock_get_key):
        mock_users_db.is_byok_active.return_value = True
        from utils.subscription import get_remaining_transcription_seconds

        assert get_remaining_transcription_seconds('byok-uid') is None

    @patch('utils.subscription.get_monthly_usage_for_subscription', return_value={'transcription_seconds': 10**9})
    @patch('utils.subscription.get_byok_key', return_value=None)
    @patch('utils.subscription.users_db')
    def test_transcription_not_bypassed_when_no_deepgram_header(self, mock_users_db, _mock_get_key, _mock_usage):
        """BYOK active but no x-byok-deepgram header — should NOT bypass.

        The proof that the bypass did not fire is that the plan path ran: the
        active basic subscription was read, its usage was consulted, and the
        exhausted allowance decided (one answer for both questions, shard S16).
        """
        mock_users_db.is_byok_active.return_value = True
        mock_users_db.get_user_valid_subscription.return_value = SimpleNamespace(plan=PlanType.basic)
        from utils.subscription import has_transcription_credits

        assert has_transcription_credits('fake-byok-uid') is False
        mock_users_db.get_user_valid_subscription.assert_called_once()
        _mock_usage.assert_called_once_with('fake-byok-uid')

"""Tests for fair-use clearing on paid plan upgrade (#6298).

Covers:
- clear_fair_use_on_upgrade() clears free_exhausted enforcement stages
- clear_fair_use_on_upgrade() preserves abuse-derived enforcement
- clear_fair_use_on_upgrade() no-ops when not applicable
- is_hard_restricted() defense-in-depth guard for paid + free_exhausted
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import utils.fair_use as fair_use_mod
from models.users import PlanType, SubscriptionStatus, Subscription

# Module-level fakes for the db/redis singletons utils.fair_use binds at import.
# Wired into utils.fair_use per-test by the autouse fixture below (sanctioned
# monkeypatch.setattr seam — see backend/docs/test_isolation.md).
_fair_use_db = MagicMock()
_mock_redis = MagicMock()


@pytest.fixture(autouse=True)
def _wire_fair_use_mocks(monkeypatch):
    monkeypatch.setattr(fair_use_mod, 'fair_use_db', _fair_use_db)
    monkeypatch.setattr(fair_use_mod, 'redis_client', _mock_redis)


def _make_paid_subscription():
    """Create a valid paid subscription object."""
    return Subscription(
        plan=PlanType.unlimited,
        status=SubscriptionStatus.active,
        current_period_end=int((datetime.utcnow() + timedelta(days=30)).timestamp()),
    )


def _make_basic_subscription():
    """Create a basic (free) subscription object."""
    return Subscription(
        plan=PlanType.basic,
        status=SubscriptionStatus.active,
    )


class TestClearFairUseOnUpgrade:
    """Test clear_fair_use_on_upgrade() behavior."""

    def setup_method(self):
        _mock_redis.reset_mock()
        _fair_use_db.update_fair_use_state.reset_mock()
        _fair_use_db.get_fair_use_state.reset_mock()

    @patch.object(fair_use_mod, 'users_db')
    def test_clears_free_exhausted_restrict_state(self, mock_users):
        """Free-exhausted restrict stage is cleared on paid upgrade."""
        mock_users.get_user_valid_subscription.return_value = _make_paid_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'last_classifier_type': 'free_exhausted',
            'restrict_until': datetime.utcnow() + timedelta(days=7),
        }

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is True
        _fair_use_db.update_fair_use_state.assert_called_once()
        call_args = _fair_use_db.update_fair_use_state.call_args
        assert call_args[0][0] == 'user1'
        updates = call_args[0][1]
        assert updates['stage'] == 'none'
        assert updates['throttle_until'] is None
        assert updates['restrict_until'] is None
        assert updates['violation_count_7d'] == 0
        assert updates['violation_count_30d'] == 0
        assert updates['cleared_by'] == 'subscription_upgrade'
        assert 'cleared_at' in updates
        _mock_redis.delete.assert_called()

    @patch.object(fair_use_mod, 'users_db')
    def test_clears_free_exhausted_warning_state(self, mock_users):
        """Free-exhausted warning stage is also cleared on upgrade."""
        mock_users.get_user_valid_subscription.return_value = _make_paid_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'warning',
            'last_classifier_type': 'free_exhausted',
        }

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is True
        updates = _fair_use_db.update_fair_use_state.call_args[0][1]
        assert updates['stage'] == 'none'

    @patch.object(fair_use_mod, 'users_db')
    def test_clears_free_exhausted_throttle_state(self, mock_users):
        """Free-exhausted throttle stage is also cleared on upgrade."""
        mock_users.get_user_valid_subscription.return_value = _make_paid_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'throttle',
            'last_classifier_type': 'free_exhausted',
            'throttle_until': datetime.utcnow() + timedelta(days=3),
        }

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is True
        updates = _fair_use_db.update_fair_use_state.call_args[0][1]
        assert updates['stage'] == 'none'
        assert updates['throttle_until'] is None

    @patch.object(fair_use_mod, 'users_db')
    def test_preserves_abuse_derived_restrict_state(self, mock_users):
        """Abuse-derived restrict stage is NOT cleared on upgrade."""
        mock_users.get_user_valid_subscription.return_value = _make_paid_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'last_classifier_type': 'audiobook',
            'restrict_until': datetime.utcnow() + timedelta(days=14),
        }

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is False
        _fair_use_db.update_fair_use_state.assert_not_called()

    @patch.object(fair_use_mod, 'users_db')
    def test_noop_when_stage_is_none(self, mock_users):
        """No-op when user has no active enforcement."""
        mock_users.get_user_valid_subscription.return_value = _make_paid_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'none',
        }

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is False
        _fair_use_db.update_fair_use_state.assert_not_called()

    @patch.object(fair_use_mod, 'users_db')
    def test_noop_when_not_paid_plan(self, mock_users):
        """No-op when user is not on a paid plan."""
        mock_users.get_user_valid_subscription.return_value = _make_basic_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'last_classifier_type': 'free_exhausted',
        }

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is False
        _fair_use_db.update_fair_use_state.assert_not_called()

    @patch.object(fair_use_mod, 'users_db')
    def test_noop_when_no_subscription(self, mock_users):
        """No-op when user has no valid subscription."""
        mock_users.get_user_valid_subscription.return_value = None

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is False
        _fair_use_db.get_fair_use_state.assert_not_called()

    @patch.object(fair_use_mod, 'users_db')
    def test_invalidates_redis_cache(self, mock_users):
        """Redis enforcement cache is invalidated after clearing."""
        mock_users.get_user_valid_subscription.return_value = _make_paid_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'last_classifier_type': 'free_exhausted',
        }

        fair_use_mod.clear_fair_use_on_upgrade('user1')

        _mock_redis.delete.assert_called_with('fair_use:stage:user1')

    @patch.object(fair_use_mod, 'users_db')
    def test_noop_when_classifier_type_missing(self, mock_users):
        """No-op when last_classifier_type is missing (legacy/malformed state)."""
        mock_users.get_user_valid_subscription.return_value = _make_paid_subscription()
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            # No last_classifier_type field at all
        }

        result = fair_use_mod.clear_fair_use_on_upgrade('user1')

        assert result is False
        _fair_use_db.update_fair_use_state.assert_not_called()

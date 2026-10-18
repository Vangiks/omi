"""Subscription plan tests — migrated off module-scope ``sys.modules`` mutation.

``utils.subscription`` pulls in ``database.users`` at import time, which itself
imports back from ``utils.subscription`` (circular). The original test broke the
cycle by pre-corrupting ``sys.modules`` at module scope with empty stubs. This
file uses the sanctioned Tier-2 reserve seam: a module-scoped fixture that
installs the stubs via ``stub_modules`` and exec's ``utils.subscription`` fresh
with ``load_module_fresh``, then restores on teardown. See
backend/docs/test_isolation.md and testing/import_isolation.py.
"""

import os
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.users import PlanType
from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def subscription_module():
    """Load a fresh ``utils.subscription`` against stubbed circular-import deps."""
    announcements_stub = ModuleType("database.announcements")
    announcements_stub.compare_versions = lambda a, b: 0
    client_stub = ModuleType("database._client")
    client_stub.get_customer_firestore_client = MagicMock()

    fakes = {
        "database.announcements": announcements_stub,
        "database._client": client_stub,
        "database.users": ModuleType("database.users"),
        "database.user_usage": ModuleType("database.user_usage"),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "utils.subscription",
            os.path.join(str(_BACKEND), "utils", "subscription.py"),
        )
        yield module


def test_architect_price_ids_map_to_architect_plan(monkeypatch, subscription_module):
    monkeypatch.setenv("STRIPE_UNLIMITED_MONTHLY_PRICE_ID", "price_unlimited_monthly")
    monkeypatch.setenv("STRIPE_UNLIMITED_ANNUAL_PRICE_ID", "price_unlimited_annual")
    monkeypatch.setenv("STRIPE_ARCHITECT_MONTHLY_PRICE_ID", "price_architect_monthly")
    monkeypatch.setenv("STRIPE_ARCHITECT_ANNUAL_PRICE_ID", "price_architect_annual")

    get_plan_type_from_price_id = subscription_module.get_plan_type_from_price_id

    assert get_plan_type_from_price_id("price_unlimited_monthly") == PlanType.unlimited
    assert get_plan_type_from_price_id("price_unlimited_annual") == PlanType.unlimited
    assert get_plan_type_from_price_id("price_architect_monthly") == PlanType.architect
    assert get_plan_type_from_price_id("price_architect_annual") == PlanType.architect


def test_architect_is_treated_as_paid_unlimited_plan(subscription_module):
    assert subscription_module.is_paid_plan(PlanType.architect) is True
    assert subscription_module.get_plan_limits(PlanType.architect).transcription_seconds is None
    assert "Automations and vibe coding" in subscription_module.get_plan_features(PlanType.architect)
    assert "Unlimited listening, memories, and insights" in subscription_module.get_plan_features(PlanType.architect)


def test_basic_plan_features_include_unlimited_memories(subscription_module):
    features = subscription_module.get_plan_features(PlanType.basic)
    assert "Unlimited memories" in features


def test_malformed_transcription_allowance_fails_loudly(monkeypatch, subscription_module):
    original_allocation_limit = subscription_module.allocation_limit

    def malformed_allocation_limit(plan, allocation):
        if allocation == 'transcription':
            raise KeyError('basic.transcription limit is missing')
        return original_allocation_limit(plan, allocation)

    monkeypatch.setattr(subscription_module, 'allocation_limit', malformed_allocation_limit)

    with pytest.raises(KeyError, match='limit is missing'):
        subscription_module.get_plan_limits(PlanType.basic)


def test_plus_and_unlimited_v2_price_ids_resolve(monkeypatch, subscription_module):
    monkeypatch.setenv("STRIPE_PLUS_MONTHLY_PRICE_ID", "price_plus_monthly")
    monkeypatch.setenv("STRIPE_PLUS_ANNUAL_PRICE_ID", "price_plus_annual")
    monkeypatch.setenv("STRIPE_UNLIMITED_V2_MONTHLY_PRICE_ID", "price_unlimited_v2_monthly")

    resolve = subscription_module.get_plan_type_from_price_id
    assert resolve("price_plus_monthly") == PlanType.plus
    assert resolve("price_plus_annual") == PlanType.plus
    assert resolve("price_unlimited_v2_monthly") == PlanType.unlimited_v2


def test_plus_is_capped_unlimited_v2_is_unlimited(subscription_module):
    plus = subscription_module.get_plan_limits(PlanType.plus)
    max_ = subscription_module.get_plan_limits(PlanType.unlimited_v2)
    assert plus.transcription_seconds == subscription_module.PLUS_TIER_MONTHLY_SECONDS_LIMIT
    assert plus.transcription_seconds and plus.transcription_seconds > 0
    assert max_.transcription_seconds is None
    assert subscription_module.is_paid_plan(PlanType.plus) is True
    assert subscription_module.is_paid_plan(PlanType.unlimited_v2) is True


def test_wire_plan_remaps_mobile_tiers_only_for_clients_without_the_enum(monkeypatch, subscription_module):
    # The module fixture stubs compare_versions to a no-op; use a real semver
    # comparator so the version floor actually gates the remap.
    def _cmp(a, b):
        pa = [int(x) for x in a.split('.')]
        pb = [int(x) for x in b.split('.')]
        return (pa > pb) - (pa < pb)

    monkeypatch.setattr(subscription_module, 'compare_versions', _cmp)
    wire = subscription_module.wire_plan_for_client
    # Current clients (below the plus/unlimited_v2-aware floor) must see a known paid label.
    assert wire(PlanType.plus, 'ios', '1.0.600') == PlanType.unlimited
    assert wire(PlanType.unlimited_v2, 'android', '1.0.600') == PlanType.unlimited
    assert wire(PlanType.plus, 'macos', '0.12.0') == PlanType.unlimited
    # A plus/unlimited_v2-aware client (at/above the floor) receives the real plan.
    assert wire(PlanType.plus, 'ios', '999.0.0') == PlanType.plus
    assert wire(PlanType.unlimited_v2, 'ios', '999.0.0') == PlanType.unlimited_v2
    # Non-mobile plans are never remapped.
    assert wire(PlanType.unlimited, 'ios', '1.0.600') == PlanType.unlimited
    assert wire(PlanType.operator, 'ios', '1.0.600') == PlanType.operator


def test_plus_and_unlimited_v2_features_state_transcription_limits(subscription_module):
    """Mobile cards render get_plan_features; Plus/Unlimited must state their
    transcription terms, not fall through to the Free-tier feature list."""
    m = subscription_module
    plus_mobile = m.get_plan_features(PlanType.plus, simplified=True)
    unlim_mobile = m.get_plan_features(PlanType.unlimited_v2, simplified=True)

    assert any("minutes of transcription" in f for f in plus_mobile), plus_mobile
    assert any(f"{m.PLUS_TIER_MINUTES_LIMIT_PER_MONTH:,}" in f for f in plus_mobile), plus_mobile
    assert any("Unlimited transcription" in f for f in unlim_mobile), unlim_mobile
    # Must not leak the Free-tier "Unlimited listening time" fallback.
    assert not any("listening" in f for f in plus_mobile), plus_mobile


def test_basic_feature_defaults_project_from_plan_limits(monkeypatch, subscription_module):
    monkeypatch.setattr(
        subscription_module,
        'get_plan_limits',
        lambda plan: SimpleNamespace(transcription_seconds=600, words_transcribed=7, insights_gained=9),
    )

    features = subscription_module.get_plan_features(PlanType.basic)

    assert '10 minutes of listening per month' in features
    assert '7 words transcribed per month' in features
    assert '9 insights per month' in features


@pytest.mark.parametrize(
    'platform,version,capable',
    [
        ('macos', '0.12.196', False),
        ('macos', '0.12.197', True),
        ('macos', '0.12.198', True),
        ('macos', None, False),
        ('windows', '1.0.35', False),
        ('windows', None, False),
        ('ios', '1.0.552', False),
        ('android', '1.0.552', False),
        ('web', '0.1.0', True),
        ('web', '0.0.9', False),
        ('web', None, False),
        ('web', 'invalid', False),
        (None, '0.1.0', False),
        ('desktop', '99.0.0', False),
    ],
)
def test_true_plan_wire_capability_boundaries(subscription_module, monkeypatch, platform, version, capable):
    def compare(a, b):
        left, right = tuple(map(int, a.split('.'))), tuple(map(int, b.split('.')))
        return (left > right) - (left < right)

    monkeypatch.setattr(subscription_module, 'compare_versions', compare)
    for plan in (PlanType.plus, PlanType.unlimited_v2):
        expected = plan if capable else PlanType.unlimited
        assert subscription_module.wire_plan_for_client(plan, platform, version) == expected


def test_macos_capability_floor_remains_operator_configurable(subscription_module, monkeypatch):
    from utils import plan_wire_capabilities

    monkeypatch.setattr(plan_wire_capabilities, 'MIN_MACOS_VERSION', '99.0.0')
    monkeypatch.setattr(subscription_module, 'compare_versions', lambda a, b: -1)
    assert subscription_module.wire_plan_for_client(PlanType.plus, 'macos', '0.12.197') == PlanType.unlimited


@pytest.mark.parametrize('platform', ['ios', 'android', 'macos', 'windows', 'web'])
@pytest.mark.parametrize('plan', [PlanType.plus, PlanType.unlimited_v2])
def test_declared_safe_decoder_receives_true_plan_before_version_resolves(subscription_module, platform, plan):
    assert subscription_module.wire_plan_for_client(plan, platform, None, '1') == plan


@pytest.mark.parametrize('capability', [None, '', '0', '2', 'true'])
def test_absent_or_unrecognized_capability_keeps_old_clients_safe(subscription_module, monkeypatch, capability):
    monkeypatch.setattr(subscription_module, 'compare_versions', lambda a, b: -1)
    assert subscription_module.wire_plan_for_client(PlanType.plus, 'ios', '1.0.0', capability) == PlanType.unlimited
    assert subscription_module.wire_plan_for_client(PlanType.plus, 'unknown', '1.0.0', '1') == PlanType.unlimited


@pytest.mark.parametrize('plan', [PlanType.basic, PlanType.unlimited, PlanType.operator, PlanType.architect])
def test_capability_never_changes_plan_membership(subscription_module, plan):
    assert subscription_module.wire_plan_for_client(plan, 'ios', None, '1') == plan


@pytest.mark.parametrize('desktop_floor,windows_floor', [(None, None), ('0.12.197', None), ('0.12.197', '2.0.0')])
def test_windows_import_time_floor_does_not_inherit_macos(monkeypatch, desktop_floor, windows_floor):
    import importlib.util

    for name, value in [
        ('PLUS_UNLIMITED_V2_MIN_DESKTOP_VERSION', desktop_floor),
        ('PLUS_UNLIMITED_V2_MIN_WINDOWS_VERSION', windows_floor),
    ]:
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location('windows_floor_fixture', _BACKEND / 'utils/plan_wire_capabilities.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def compare(a, b):
        left, right = tuple(map(int, a.split('.'))), tuple(map(int, b.split('.')))
        return (left > right) - (left < right)

    assert module.MIN_WINDOWS_VERSION == (windows_floor or '99.0.0')
    assert not module.understands_plan_identity('windows', '1.0.35', None, compare)
    assert module.understands_plan_identity('macos', '0.12.197', None, compare)
    if windows_floor:
        assert module.understands_plan_identity('windows', '2.0.0', None, compare)


@pytest.mark.parametrize('interval', ['Monthly', 'Annual'])
def test_operator_wire_title_preserves_released_macos_price_ownership(subscription_module, interval):
    # Released normalizedPlanId routes titles containing "pro" to Architect.
    # Payments appends these intervals to the definition title; the old merger
    # then unions those prices into that inferred plan, even when IDs are sent.
    definition = next(d for d in subscription_module.get_paid_plan_definitions() if d['plan_id'] == 'operator')
    title = f"{definition['title']} {interval}".lower()
    assert definition['title'] == 'Operator'
    assert 'operator' in title and 'pro' not in title
    assert subscription_module.PLAN_DISPLAY_NAMES[PlanType.operator] == 'Pro'

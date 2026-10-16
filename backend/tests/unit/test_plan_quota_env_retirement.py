"""D2 (plan-source-of-truth): the plan catalog is the only source of plan quotas.

Before D2 the ``BASIC_TIER_*`` env overlays outranked ``config/plan_catalog.json``
at runtime (``utils.subscription._basic_transcription_overlay``), so the prod API
plane advertised 600 free minutes while the listen plane enforced 300. D2 deleted
the overlays; this pins that the runtime reads quotas from the catalog alone.
"""

from __future__ import annotations

import importlib
import os

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

RETIRED_PLAN_QUOTA_ENV = frozenset(
    {
        'BASIC_TIER_MINUTES_LIMIT_PER_MONTH',
        'BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH',
        'BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH',
        'BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH',
    }
)


@pytest.mark.slow  # per-test fresh reload of utils.subscription (~1 s CPU); slow-guardrail lane
def test_catalog_is_the_only_source_when_no_overlay_is_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the overlays gone, Free transcription is the catalog's 300 minutes on every plane."""
    for name in RETIRED_PLAN_QUOTA_ENV:
        monkeypatch.delenv(name, raising=False)
    from config.plan_catalog import PlanType, allocation_limit
    from utils import subscription as sub_mod

    sub_mod = importlib.reload(sub_mod)
    try:
        assert allocation_limit(PlanType.basic, 'transcription') == 18000
        assert sub_mod.BASIC_TIER_MONTHLY_SECONDS_LIMIT == 18000
        assert sub_mod.BASIC_TIER_MINUTES_LIMIT_PER_MONTH == 300
        # Catalog "unlimited" is None; the legacy zero sentinel is no longer consulted.
        assert sub_mod.BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH is None
        assert sub_mod.BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH is None
    finally:
        monkeypatch.undo()
        importlib.reload(sub_mod)

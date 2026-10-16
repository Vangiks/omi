"""Independent default-off switches for the three PR #14165 basic-plan gates.

Import-light: readers and composed YAML only. Behavioral OFF/ON coverage for
each gate lives next to the existing #14165 tests (those files already pay for
the heavy router / coordinator imports in module-scoped fixtures).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from utils.free_tier_basic_gates import (
    BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED,
    BASIC_PLAN_GATE_PROXY_EMBED_ENABLED,
    basic_plan_gate_eager_extraction_enabled,
    basic_plan_gate_proxy_embed_enabled,
)
from utils.free_tier_cohort import EMERGENCY_STOP_ENV_VAR

BACKEND = Path(__file__).resolve().parents[2]
_READERS = (
    (BASIC_PLAN_GATE_PROXY_EMBED_ENABLED, basic_plan_gate_proxy_embed_enabled),
    (BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED, basic_plan_gate_eager_extraction_enabled),
)


@pytest.fixture(autouse=True)
def _clear_gate_env(monkeypatch):
    for name, _reader in _READERS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(EMERGENCY_STOP_ENV_VAR, raising=False)


# red-proof: treat ``'1'`` / ``'yes'`` / ``'on'`` as on
@pytest.mark.parametrize('name, reader', _READERS)
@pytest.mark.parametrize(
    'value, expected',
    [
        ('true', True),
        ('TRUE', True),
        ('True', True),
        ('false', False),
        ('1', False),
        ('yes', False),
        ('on', False),
        ('', False),
        (None, False),
    ],
)
def test_env_parse_accepts_only_true_case_insensitive(monkeypatch, name, reader, value, expected) -> None:
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)
    assert reader() is expected


@pytest.mark.parametrize('name, reader', _READERS)
def test_emergency_stop_revokes_a_lit_gate(monkeypatch, name, reader) -> None:
    monkeypatch.setenv(name, 'true')
    assert reader() is True
    monkeypatch.setenv(EMERGENCY_STOP_ENV_VAR, 'true')
    assert reader() is False


@pytest.mark.parametrize('name, reader', _READERS)
def test_readers_are_independent_and_re_read_env_at_call_time(monkeypatch, name, reader):
    assert reader() is False
    monkeypatch.setenv(name, 'true')
    assert reader() is True
    assert all(other_reader() is False for other_name, other_reader in _READERS if other_name != name)
    monkeypatch.setenv(name, 'false')
    assert reader() is False


def test_each_gate_site_calls_only_its_own_reader() -> None:
    proxy = (BACKEND / 'routers/desktop_proxy.py').read_text(encoding='utf-8')
    coordinator = (BACKEND / 'utils/conversations/process_conversation.py').read_text(encoding='utf-8')
    # The proxy has no plan gate (#3).
    assert 'basic_plan_gate' not in proxy
    assert 'basic_plan_gate_eager_extraction_enabled()' in coordinator
    assert 'basic_plan_gate_proxy_embed_enabled' not in coordinator

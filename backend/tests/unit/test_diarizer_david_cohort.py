"""Reviewed batch stages bind the same cohort on live and offline-sync hosts."""

import json
from pathlib import Path

import pytest
from config import transcription_final_pass as flags

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    'stage,percent,authoritative,cap',
    [
        ('A', '0', 'false', '1'),
        ('B', '0', 'true', '1'),
        ('C', '1', 'true', '80'),
        ('D', '5', 'true', '400'),
    ],
)
def test_ramp_data_preserves_scope_and_capacity(monkeypatch, stage, percent, authoritative, cap):
    values = json.loads((ROOT / 'config/diarization-cohort-stages.json').read_text())[stage]
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    assert values['TRANSCRIPTION_FINAL_PASS_PERCENT'] == values['TRANSCRIPTION_SHADOW_PERCENT'] == percent
    assert values['TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE'] == authoritative
    assert values['TRANSCRIPTION_SHADOW_DAILY_AUDIO_HOURS'] == cap
    assert values['TRANSCRIPTION_SHADOW_ENABLED'] == 'true'
    assert values['TRANSCRIPTION_SHADOW_KILL_SWITCH'] == 'false'
    assert values['TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED'] == ('false' if stage == 'A' else 'true')
    assert flags.sync_enabled_for(values['TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST']) == (stage != 'A')
    assert values['TRANSCRIPTION_SHADOW_UID_ALLOWLIST'] == values['TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST']
    assert flags.enabled_for(values['TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST'])
    if percent == '0':
        assert not flags.enabled_for('synthetic-outside-cohort')
    else:
        assert float(cap) >= 6300 * float(percent) / 100
        assert 140 * float(percent) / 5 * 0.06 < 24

"""AUDIO_TIMELINE_SPANS and LIVE_SPEAKER_SPAN_RESOLUTION deployment defaults.

Both rollout switches must default off in source and stay pinned off in every
composed deployment declaration until the staged rollout promotes them.
Keeps this file import-light so the fast-unit duration guard stays honest.
"""

from __future__ import annotations



from config.audio_timeline import audio_timeline_spans_enabled, live_speaker_span_resolution_enabled

FLAGS = ('AUDIO_TIMELINE_SPANS', 'LIVE_SPEAKER_SPAN_RESOLUTION')


def test_flags_default_off(monkeypatch):
    for flag in FLAGS:
        monkeypatch.delenv(flag, raising=False)
    assert audio_timeline_spans_enabled() is False
    assert live_speaker_span_resolution_enabled() is False


def test_flags_truthy_parser(monkeypatch):
    monkeypatch.setenv('AUDIO_TIMELINE_SPANS', 'true')
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', '1')
    assert audio_timeline_spans_enabled() is True
    assert live_speaker_span_resolution_enabled() is True
    monkeypatch.setenv('AUDIO_TIMELINE_SPANS', '0')
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'off')
    assert audio_timeline_spans_enabled() is False
    assert live_speaker_span_resolution_enabled() is False

"""The release-probe desktop exemption: probe uid gets the full terminal
path; every lookalike and real-shaped uid keeps the fenced/deferred gates."""

from __future__ import annotations

from pathlib import Path
import sys

SCRIPTS_PARENT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_PARENT))

from utils.release_probe import RELEASE_PROBE_UID, is_release_probe_uid  # noqa: E402


def test_predicate_is_exact_equality() -> None:
    assert is_release_probe_uid('omi-release-probe')
    assert not is_release_probe_uid('omi-release-probeX')
    assert not is_release_probe_uid('omi-release-probe-2')
    assert not is_release_probe_uid('OMI-RELEASE-PROBE')
    assert not is_release_probe_uid(' omi-release-probe')
    assert not is_release_probe_uid('omi-release-probe ')
    assert not is_release_probe_uid('')
    assert not is_release_probe_uid(None)
    assert not is_release_probe_uid(12345)
    assert not is_release_probe_uid(b'omi-release-probe')


def test_constant_matches_the_documented_uid() -> None:
    assert RELEASE_PROBE_UID == 'omi-release-probe'


def test_discard_gates_exempt_only_the_probe_uid() -> None:
    """The discard gates must consult the shared predicate (no local literal,
    no reinvented matching). Static contract: the guard module is the single
    source of truth."""
    conversations = Path(__file__).resolve().parents[2] / 'utils' / 'conversations'
    process_source = (conversations / 'process_conversation.py').read_text(encoding='utf-8')
    assert "from utils.release_probe import is_release_probe_uid" in process_source
    assert "'omi-release-probe'" not in process_source
    # The discard verdict is a desktop post-processing gate: the probe
    # lane's terminal contract completes only through a kept conversation, so
    # both of its verdicts (the LLM discard decision and the empty-title
    # fallback) must skip for the probe uid (run 35583992730).
    assert 'exempt=is_release_probe_uid(uid),' in process_source
    assert "structured.title == '' and not is_release_probe_uid(uid)" in process_source

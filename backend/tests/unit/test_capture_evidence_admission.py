"""CAPTURE_EVIDENCE_V1_DARK_WRITE (S1) admission.

S1 is admitted on every host that receives or consumes capture evidence
(listen receipts, sync upload claims, sync workers). Mobile release builds opt
in with a dart-define; code stays default off. Keeps this file import-light so
the fast-unit duration guard stays honest.
"""

from __future__ import annotations



from config.capture_evidence import capture_evidence_dark_write_enabled

FLAG = 'CAPTURE_EVIDENCE_V1_DARK_WRITE'

def test_code_default_stays_off(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert capture_evidence_dark_write_enabled() is False

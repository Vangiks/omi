from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from utils.memory import knowledge_ledger_drain as ledger_drain


def _load_job():
    path = Path(__file__).resolve().parents[2] / "modal" / "knowledge_ledger_drain_job.py"
    spec = importlib.util.spec_from_file_location("_knowledge_ledger_drain_job_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Executing the job module pulls the whole drain dependency graph (firebase_admin and
# utils.memory.*), which costs ~1.5s of CPU on a cold interpreter and starts gRPC's
# background threads. Loading it at import time keeps that out of every phase the
# fast-unit duration guard measures; as a module-scoped fixture the cost was charged to
# whichever test happened to request it first.
JOB = _load_job()


def test_entrypoint_executes_independent_drain(monkeypatch):
    job = JOB
    called = []

    async def run(**kwargs):
        assert kwargs["uid_allowlist"] == {"uid-owner"}
        called.append(True)
        return SimpleNamespace(errors=[])

    monkeypatch.setenv(ledger_drain.LEDGER_DRAIN_ENABLED_ENV, "true")
    monkeypatch.setenv(ledger_drain.LEDGER_DRAIN_UID_ALLOWLIST_ENV, "uid-owner")
    monkeypatch.setattr(job, "_init_firebase", lambda: None)
    monkeypatch.setattr(job, "run_knowledge_ledger_drain", run)

    job.main()

    assert called == [True]


def test_entrypoint_fails_when_a_page_reports_errors(monkeypatch):
    job = JOB

    async def run(**_kwargs):
        return SimpleNamespace(errors=["uid=redacted:migration:RuntimeError"])

    monkeypatch.setenv(ledger_drain.LEDGER_DRAIN_ENABLED_ENV, "true")
    monkeypatch.setenv(ledger_drain.LEDGER_DRAIN_UID_ALLOWLIST_ENV, "uid-owner")
    monkeypatch.setattr(job, "_init_firebase", lambda: None)
    monkeypatch.setattr(job, "run_knowledge_ledger_drain", run)

    with pytest.raises(RuntimeError, match=r"completed with 1 error\(s\)"):
        job.main()


def test_entrypoint_default_off_skips_firebase_and_inventory(monkeypatch):
    job = JOB
    called = []

    monkeypatch.delenv(ledger_drain.LEDGER_DRAIN_ENABLED_ENV, raising=False)
    monkeypatch.setattr(job, "_init_firebase", lambda: called.append("firebase"))
    monkeypatch.setattr(job, "run_knowledge_ledger_drain", lambda **_kwargs: called.append("drain"))

    job.main()

    assert called == []


def test_adc_firebase_initialization_pins_auth_audience(monkeypatch):
    observed = {}
    monkeypatch.delenv("SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setattr(JOB, "firebase_admin_options", lambda: {"projectId": "based-hardware"})
    monkeypatch.setattr(JOB.firebase_admin, "initialize_app", lambda **kwargs: observed.update(kwargs))

    JOB._init_firebase()

    assert observed == {"options": {"projectId": "based-hardware"}}


def test_entrypoint_enabled_without_allowlist_fails_before_firebase(monkeypatch):
    job = JOB
    called = []

    monkeypatch.setenv(ledger_drain.LEDGER_DRAIN_ENABLED_ENV, "true")
    monkeypatch.delenv(ledger_drain.LEDGER_DRAIN_UID_ALLOWLIST_ENV, raising=False)
    monkeypatch.setattr(job, "_init_firebase", lambda: called.append("firebase"))

    with pytest.raises(RuntimeError, match="requires an explicit UID allowlist"):
        job.main()

    assert called == []

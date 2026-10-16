"""Backend runtime leg of the shared additive JIT client contract matrix."""

from __future__ import annotations

import json
from pathlib import Path

from models.chat import ChatEvidenceEnvelope
from models.memories import MemoryDB

FIXTURE = Path(__file__).resolve().parents[3] / 'contracts' / 'parity' / 'jit_runtime_contract_matrix.json'


def _matrix() -> dict:
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def test_backend_models_accept_mixed_client_versions_without_losing_text():
    matrix = _matrix()
    rows = [MemoryDB.model_validate(row) for row in matrix['memory_rows']]

    assert [row.id for row in rows] == matrix['expected']['memory_ids']
    assert {row.id: row.content for row in rows} == matrix['expected']['readable_text_by_id']
    assert [row.id for row in rows if row.ledger_schema_version == 'knowledge_ledger.v1'] == matrix['expected'][
        'authoritative_ledger_ids'
    ]


def test_backend_evidence_model_keeps_legacy_optional_and_quarantines_future_semantics():
    matrix = _matrix()
    records = matrix['chat_records']

    assert 'evidence' not in records['legacy']
    current = ChatEvidenceEnvelope.model_validate(records['v1']['evidence'])
    future = ChatEvidenceEnvelope.model_validate(records['future']['evidence'])

    assert current.references[0].kind == matrix['expected']['v1_evidence_kind']
    assert future.references[0].kind == matrix['expected']['future_evidence_kind']
    assert future.references[0].state == matrix['expected']['future_evidence_state']
    assert records['legacy']['text'] and records['v1']['text'] and records['future']['text']



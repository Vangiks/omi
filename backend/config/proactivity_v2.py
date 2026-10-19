"""Small server-owned producer registry and integer budget policy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Same for every user: the former architect cap, 19900 cents * 1000 // 30 days.
DAILY_CAP_MICRO_USD = 663333


class ProactivityDenied(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class Producer(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    name: str = Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')
    version: int = Field(ge=1)
    enabled: bool
    paid_only: bool
    signal: str
    trigger: str
    dedupe_scope: str
    max_calls_per_user_utc_day: int = Field(ge=1, le=200)
    max_calls_per_item: int = Field(ge=1, le=8)
    gateway_lane: str
    max_request_bytes: int = Field(ge=1, le=32768)
    max_output_tokens: int = Field(ge=1, le=2048)
    expected_micro_usd_per_delivery: int = Field(ge=0)
    measurement_status: Literal['provisional', 'measured']
    measurement_reference: str = Field(min_length=1)
    min_acted_24h_rate: float = Field(gt=0, le=1)
    max_micro_usd_per_acted_item: int = Field(gt=0)
    kill_min_deliveries: int = Field(ge=200)
    evaluation_window_days: Literal[7]
    push_earned: bool
    push_evidence_reference: str

    @model_validator(mode='after')
    def evidence_for_push(self):
        if self.push_earned and not self.push_evidence_reference:
            raise ValueError('earned push requires evidence')
        return self


@lru_cache(maxsize=1)
def producers() -> dict[str, Producer]:
    rows = json.loads(Path(__file__).with_name('proactivity_v2_producers.json').read_text())
    result = {row['name']: Producer.model_validate(row) for row in rows}
    if len(rows) != len(result):
        raise ValueError('duplicate producer')
    return result


def producer_for(name: str) -> Producer:
    try:
        producer = producers()[name]
    except KeyError as exc:
        raise ProactivityDenied('producer_disabled') from exc
    if not producer.enabled:
        raise ProactivityDenied('producer_disabled')
    return producer


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AttemptEnvelope:
    provider: str
    model: str
    rate_card_id: str
    worst_case_micro_usd: int
    fingerprint: str
    step: str


@dataclass(frozen=True)
class Reservation:
    uid: str
    item_id: str
    producer: str
    call_id: str
    day: str
    token: str
    reserved_micro_usd: int
    account_generation: str

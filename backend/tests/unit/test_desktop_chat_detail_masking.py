"""Unit tests for desktop_chat router exception detail masking.

Verifies that ValueError and RuntimeError raised in the desktop_chat
endpoint handlers are sanitized and do not leak internal details.
"""

from unittest.mock import AsyncMock

import pytest
import routers.desktop_chat as dc_routes
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_preparation_runtime_error_is_masked(monkeypatch):
    """RuntimeError in the request preparation path must return static 503 without internal details."""
    leak_text = "upstream redis cluster connection refused host=prod-cache-01:6379"

    monkeypatch.setattr(dc_routes, "llm_stub_enabled", lambda: False)
    monkeypatch.setattr(
        dc_routes,
        "_meter_server_request",
        AsyncMock(side_effect=RuntimeError(leak_text)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await dc_routes._chat_completions_unobserved(
            body={
                "model": "omi-sonnet",
                "messages": [{"role": "user", "content": "hello"}],
            },
            uid="test-user-002",
            x_omi_chat_contract_version="1",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Service temporarily unavailable. Please try again."
    assert "prod-cache-01" not in exc_info.value.detail
    assert "6379" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_preparation_value_error_is_masked(monkeypatch):
    """ValueError in the request preparation path must return static 400 without internal details."""
    leak_text = "internal metering calc failed for user_id=secret-123"

    monkeypatch.setattr(dc_routes, "llm_stub_enabled", lambda: False)
    monkeypatch.setattr(
        dc_routes,
        "_meter_server_request",
        AsyncMock(side_effect=ValueError(leak_text)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await dc_routes._chat_completions_unobserved(
            body={
                "model": "omi-sonnet",
                "messages": [{"role": "user", "content": "hello"}],
            },
            uid="test-user-003",
            x_omi_chat_contract_version="1",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid request parameters."
    assert "secret-123" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_request_validation_error_passes_through():
    """Client validation errors from _request must be preserved for callers."""
    with pytest.raises(HTTPException) as exc_info:
        await dc_routes._chat_completions_unobserved(
            body={
                "model": "invalid-model",
                "messages": [{"role": "user", "content": "hello"}],
            },
            uid="test-user-004",
            x_omi_chat_contract_version="1",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "unsupported model"

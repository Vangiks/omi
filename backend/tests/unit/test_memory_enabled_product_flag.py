"""One product flag: MEMORY_ENABLED=on|off.

Keeps this file import-light so the fast-unit duration guard stays honest.
MemoryService intake/list behavior is covered in test_universal_memory_service
and test_memories_pagination_clamp.
"""

from __future__ import annotations


from config.memory_rollout import (
    memory_enabled_env_value,
    rollout_mode_env_value,
)

def test_memory_enabled_on_maps_to_write_not_gate3_read():
    env = {"MEMORY_ENABLED": "on"}
    assert memory_enabled_env_value(env) is True
    assert rollout_mode_env_value(env) == "write"


def test_memory_enabled_off_pauses_writes_and_fail_closed_unset():
    assert memory_enabled_env_value({"MEMORY_ENABLED": "off"}) is False
    assert rollout_mode_env_value({"MEMORY_ENABLED": "off"}) == "off"
    assert memory_enabled_env_value({}) is False
    assert rollout_mode_env_value({}) == "off"


def test_retired_aliases_do_not_enable_memory():
    env = {"MEMORY_MODE": "write", "MEMORY_V3_GET_ENABLED": "true"}
    assert memory_enabled_env_value(env) is False
    assert rollout_mode_env_value(env) == "off"

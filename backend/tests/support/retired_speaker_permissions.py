"""Stand-in for the retired plan check that historical sources still import.

Some tests exec an older `speaker_resolution.py` verbatim from Git as a baseline.
Those sources import `utils.speaker_permissions`, which no longer exists: every
user has named speakers. Exec them inside this context so the import resolves to
an always-allowed check, matching the current behavior.
"""

import sys
import types
from contextlib import contextmanager
from typing import Iterator

import pytest

_NAME = 'utils.speaker_permissions'


@contextmanager
def retired_speaker_permissions() -> Iterator[None]:
    module = types.ModuleType(_NAME)
    setattr(module, 'named_speaker_prompts_allowed', lambda uid: True)
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(sys.modules, _NAME, module)
        yield

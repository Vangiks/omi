"""The fork's backend has no plan catalog and no plan identity (#55).

Source-level checks: the catalog files are gone and no other backend module names the
removed symbols.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

REMOVED_FILES = (
    'config/plan_catalog.json',
    'config/plan_catalog.py',
    'config/plan_catalog_generated.py',
    'scripts/generate_plan_catalog.py',
    'scripts/entitlement_catalog_validation.py',
    'utils/plan_wire_capabilities.py',
    'database/firestore_tier_context.py',
)

REMOVED_NAMES = re.compile(r'\bPlanType\b|plan_catalog|plan_wire_capabilities|firestore_tier_context')


def test_plan_catalog_files_are_gone():
    assert [path for path in REMOVED_FILES if (BACKEND / path).exists()] == []


def test_no_backend_module_names_the_plan_catalog():
    offenders = []
    for path in BACKEND.rglob('*.py'):
        relative = path.relative_to(BACKEND)
        # Skip this file and local virtualenvs (.venv, .openapi-venv, ...).
        if path == Path(__file__).resolve() or relative.parts[0].startswith('.'):
            continue
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if REMOVED_NAMES.search(line):
                offenders.append(f'{relative}:{number}: {line.strip()}')
    assert offenders == []

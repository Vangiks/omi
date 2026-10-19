"""The fork's backend does not talk to Stripe (#45).

Source-level checks: no backend module mentions Stripe and the `stripe` package is gone
from the dependency files.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

# models/trend.py names Stripe as a company.
ALLOWED = {
    'models/trend.py',
}

STRIPE = re.compile(r'\bstripe\b', re.IGNORECASE)


def test_no_stripe_code_left_in_backend():
    offenders = []
    for path in BACKEND.rglob('*.py'):
        relative = path.relative_to(BACKEND)
        # Skip tests and local virtualenvs (.venv, .openapi-venv, ...).
        if relative.parts[0] == 'tests' or relative.parts[0].startswith('.') or relative.as_posix() in ALLOWED:
            continue
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if STRIPE.search(line):
                offenders.append(f'{relative}:{number}: {line.strip()}')
    assert not offenders, '\n'.join(offenders)


def test_stripe_package_is_not_a_dependency():
    files = [
        'requirements.txt',
        'openapi-requirements.txt',
        'pusher/requirements.txt',
        'pusher/pylock.toml',
        *(p.name for p in BACKEND.glob('pylock*.toml')),
    ]
    offenders = [
        f'{name}:{number}'
        for name in files
        for number, line in enumerate((BACKEND / name).read_text(encoding='utf-8').splitlines(), 1)
        if re.match(r'\s*(name\s*=\s*"stripe"|stripe\s*[=<>~]=)', line)
    ]
    assert not offenders, offenders

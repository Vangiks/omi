"""Static checks of what the backend service images install and run."""

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _requirement_pin(requirements_text: str, package: str) -> str:
    prefix = f'{package}=='
    for line in requirements_text.splitlines():
        if line.startswith(prefix):
            return line
    raise AssertionError(f'{package} pin missing from requirements')


@pytest.mark.parametrize('dockerfile_name', ['Dockerfile', 'Dockerfile.nim'])
def test_parakeet_pod_runs_one_uvicorn_process_for_its_gpu(dockerfile_name):
    dockerfile = (BACKEND_DIR / 'parakeet' / dockerfile_name).read_text(encoding='utf-8')

    command = next(line for line in dockerfile.splitlines() if line.startswith('CMD ["uvicorn"'))
    assert '--workers' not in command


def test_desktop_runtime_image_installs_ffmpeg_for_mp3_contract():
    dockerfile = (BACKEND_DIR / 'Dockerfile.desktop_backend').read_text(encoding='utf-8')
    assert 'install --no-install-recommends ffmpeg' in dockerfile


def test_pusher_runtime_uses_a_non_root_user_with_writable_working_directories() -> None:
    dockerfile = (BACKEND_DIR / 'pusher' / 'Dockerfile').read_text(encoding='utf-8')
    assert 'mkdir -p _temp _samples _segments _speech_profiles' in dockerfile
    assert 'chown -R 10001:10001 _temp _samples _segments _speech_profiles' in dockerfile
    assert 'USER 10001:10001' in dockerfile


def test_structured_model_fallback_imports_without_plugin_sdk(tmp_path):
    models_root = tmp_path / 'models'
    models_root.mkdir()
    shutil.copy(BACKEND_DIR / 'models' / '__init__.py', models_root / '__init__.py')
    shutil.copy(BACKEND_DIR / 'models' / 'conversation_enums.py', models_root / 'conversation_enums.py')
    shutil.copy(BACKEND_DIR / 'models' / 'structured.py', models_root / 'structured.py')

    probe = '''
import builtins

real_import = builtins.__import__

def block_optional_sdk(name, *args, **kwargs):
    if name == "omi_plugin_sdk" or name.startswith("omi_plugin_sdk."):
        raise ModuleNotFoundError(name)
    return real_import(name, *args, **kwargs)

builtins.__import__ = block_optional_sdk
from models import structured

assert structured.ActionItem.__module__ == "models.structured"
assert structured.Event.__module__ == "models.structured"
assert structured.Section.__module__ == "models.structured"
assert structured.Structured(title="fallback").title == "fallback"
'''
    environment = dict(os.environ)
    environment['PYTHONPATH'] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, '-c', probe],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, (
        'SDK-absent fallback import failed; ' f'stdout={result.stdout[-2000:]!r} stderr={result.stderr[-2000:]!r}'
    )


def test_pusher_installs_typesense_because_finalization_indexes_conversations():
    """process_conversation → lifecycle → typesense_index is reachable in the pusher image.

    Auto-deploy smoke failed from 2026-09-01 onward with
    missing installed dependency modules: typesense / typesense.exceptions.ObjectNotFound
    because the module was on backend/requirements.txt but not the pusher subset.
    """
    pusher = (BACKEND_DIR / 'pusher' / 'requirements.txt').read_text(encoding='utf-8')
    backend = (BACKEND_DIR / 'requirements.txt').read_text(encoding='utf-8')
    assert _requirement_pin(pusher, 'typesense') == _requirement_pin(backend, 'typesense')
    pylock = (BACKEND_DIR / 'pusher' / 'pylock.toml').read_text(encoding='utf-8')
    assert 'name = "typesense"' in pylock


def test_pusher_posthog_pin_matches_backend_cohort_flag_client():
    """PR #20533 enabled cohort dispatch, but pusher lacked the lazy PostHog SDK."""
    pusher = (BACKEND_DIR / 'pusher' / 'requirements.txt').read_text(encoding='utf-8')
    backend = (BACKEND_DIR / 'requirements.txt').read_text(encoding='utf-8')
    pin = _requirement_pin(backend, 'posthog')
    assert _requirement_pin(pusher, 'posthog') == pin
    lock = tomllib.loads((BACKEND_DIR / 'pusher' / 'pylock.toml').read_text(encoding='utf-8'))
    packages = {package['name']: package['version'] for package in lock['packages']}
    assert packages['posthog'] == pin.split('==', 1)[1]


def test_pusher_lock_covers_mentor_v2_lazy_imports():
    """Packages audited in the pusher-only venv, including function-local imports.

    PR #20533's cohort dispatch exposed a missing lazy PostHog import that the
    static entrypoint smoke did not see. Keep this audited package contract
    independent of the full backend environment, where PostHog was installed.
    Jev dedupe/usefulness use gateway_client's httpx transport, not another SDK.
    """
    module_distributions = {
        'anthropic': 'anthropic',
        'cachetools': 'cachetools',
        'cryptography': 'cryptography',
        'fastapi': 'fastapi',
        'firebase_admin': 'firebase-admin',
        'google.api_core': 'google-api-core',
        'google.auth': 'google-auth',
        'google.oauth2': 'google-auth',
        'google.protobuf': 'protobuf',
        'google.cloud.exceptions': 'google-cloud-core',
        'google.cloud.firestore': 'google-cloud-firestore',
        'google.cloud.firestore_v1': 'google-cloud-firestore',
        'google.cloud.storage': 'google-cloud-storage',
        'google.cloud.tasks_v2': 'google-cloud-tasks',
        'httpx': 'httpx',
        'jsonschema': 'jsonschema',
        'langchain_anthropic': 'langchain-anthropic',
        'langchain_core': 'langchain-core',
        'langchain_google_genai': 'langchain-google-genai',
        'langchain_openai': 'langchain-openai',
        'numpy': 'numpy',
        'openai': 'openai',
        'opuslib': 'opuslib',
        'pinecone': 'pinecone',
        'posthog': 'posthog',
        'prometheus_client': 'prometheus-client',
        'pycountry': 'pycountry',
        'pydantic': 'pydantic',
        'pytz': 'pytz',
        'redis': 'redis',
        'starlette': 'starlette',
        'tiktoken': 'tiktoken',
        'typesense': 'typesense',
        'ulid': 'python-ulid',
    }
    lock = tomllib.loads((BACKEND_DIR / 'pusher' / 'pylock.toml').read_text(encoding='utf-8'))
    installed_packages = {package['name'] for package in lock['packages']}
    missing = {module: package for module, package in module_distributions.items() if package not in installed_packages}
    assert not missing, f'Mentor v2 modules missing from pusher lock: {missing}'

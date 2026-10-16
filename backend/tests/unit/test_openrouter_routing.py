"""Unit tests for the OpenRouter route rule and model-id mapping."""

import ast
import itertools
from pathlib import Path

import pytest
import yaml

from utils.llm.model_config import _PINNED_FEATURES, MODEL_QOS_PROFILES
from utils.llm.openrouter import openrouter_model_id, provider_route

BACKEND_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_CONFIG_DIR = BACKEND_ROOT / 'llm_gateway' / 'config'

_DIRECT_KEY_ENV = {
    'openai': 'OPENAI_API_KEY',
    'anthropic': 'ANTHROPIC_API_KEY',
    'perplexity': 'PERPLEXITY_API_KEY',
}
_ALL_KEY_ENVS = ('OPENROUTER_API_KEY', *_DIRECT_KEY_ENV.values())


def _set_keys(monkeypatch, values: dict) -> None:
    for env in _ALL_KEY_ENVS:
        monkeypatch.delenv(env, raising=False)
    for env, value in values.items():
        monkeypatch.setenv(env, value)


# Key states: missing, empty string (treated as missing), whitespace (treated as missing), set.
_KEY_STATES = (None, '', '  ', 'key')


@pytest.mark.parametrize('provider', sorted(_DIRECT_KEY_ENV))
@pytest.mark.parametrize('openrouter_key,direct_key', list(itertools.product(_KEY_STATES, _KEY_STATES)))
def test_provider_route_follows_spec_table(monkeypatch, provider, openrouter_key, direct_key):
    values = {}
    if openrouter_key is not None:
        values['OPENROUTER_API_KEY'] = openrouter_key
    if direct_key is not None:
        values[_DIRECT_KEY_ENV[provider]] = direct_key
    _set_keys(monkeypatch, values)

    if (openrouter_key or '').strip():
        expected = 'openrouter'
    elif (direct_key or '').strip():
        expected = 'direct'
    else:
        expected = 'none'
    assert provider_route(provider) == expected


def test_provider_route_ignores_other_providers_direct_keys(monkeypatch):
    _set_keys(monkeypatch, {'OPENAI_API_KEY': 'key', 'PERPLEXITY_API_KEY': 'key'})

    assert provider_route('anthropic') == 'none'


def test_provider_route_reads_environment_on_every_call(monkeypatch):
    _set_keys(monkeypatch, {'OPENAI_API_KEY': 'key'})
    assert provider_route('openai') == 'direct'

    monkeypatch.setenv('OPENROUTER_API_KEY', 'key')
    assert provider_route('openai') == 'openrouter'


def test_provider_route_rejects_providers_outside_openrouter_scope(monkeypatch):
    _set_keys(monkeypatch, {'OPENROUTER_API_KEY': 'key'})

    with pytest.raises(ValueError):
        provider_route('gemini')


@pytest.mark.parametrize(
    'provider,model,expected',
    [
        ('openai', 'gpt-6-luna', 'openai/gpt-6-luna'),
        ('openai', 'text-embedding-3-large', 'openai/text-embedding-3-large'),
        ('perplexity', 'sonar-pro', 'perplexity/sonar-pro'),
        ('anthropic', 'claude-sonnet-4-6', 'anthropic/claude-sonnet-4.6'),
        ('anthropic', 'claude-haiku-4-5-20251001', 'anthropic/claude-haiku-4.5'),
        ('anthropic', 'claude-opus-4-20250514', 'anthropic/claude-opus-4'),
        ('gemini', 'gemini-3.5-flash-lite', 'google/gemini-3.5-flash-lite'),
        ('openrouter', 'gemini-3-flash-preview', 'google/gemini-3-flash-preview'),
        ('openai', 'openai/gpt-5-nano', 'openai/gpt-5-nano'),
        ('anthropic', 'anthropic/claude-sonnet-4.6', 'anthropic/claude-sonnet-4.6'),
    ],
)
def test_openrouter_model_id(provider, model, expected):
    assert openrouter_model_id(provider, model) == expected


def _yaml_provider_models(node):
    if isinstance(node, dict):
        if isinstance(node.get('provider'), str) and isinstance(node.get('model'), str):
            yield node['provider'], node['model']
        for value in node.values():
            yield from _yaml_provider_models(value)
    elif isinstance(node, list):
        for item in node:
            yield from _yaml_provider_models(item)


def _desktop_chat_anthropic_models() -> set:
    # Parsed rather than imported: routers.desktop_chat pulls in Firestore and auth at import time.
    tree = ast.parse((BACKEND_ROOT / 'routers' / 'desktop_chat.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == '_MODEL_ROUTES' for target in node.targets
        ):
            routes = ast.literal_eval(node.value)
            return {name for name in (*routes.keys(), *routes.values()) if name.startswith('claude-')}
    raise AssertionError('_MODEL_ROUTES not found in routers/desktop_chat.py')


def _configured_provider_models() -> set:
    # model_config stores (model, provider); everything collected here is (provider, model).
    pairs = set()
    for routes in (*MODEL_QOS_PROFILES.values(), _PINNED_FEATURES):
        pairs.update((provider, model) for model, provider in routes.values())
    for name in ('route_artifacts.yaml', 'generated_route_overrides.yaml'):
        data = yaml.safe_load((GATEWAY_CONFIG_DIR / name).read_text(encoding='utf-8'))
        pairs.update(_yaml_provider_models(data))
    pairs.update(('anthropic', model) for model in _desktop_chat_anthropic_models())
    return pairs


def test_configuration_sources_are_not_empty():
    providers = {provider for provider, _model in _configured_provider_models()}

    assert {'openai', 'anthropic', 'perplexity'} <= providers


@pytest.mark.parametrize('provider,model', sorted(_configured_provider_models()))
def test_every_configured_model_maps_to_an_openrouter_slug(provider, model):
    slug = openrouter_model_id(provider, model)

    vendor, _, name = slug.partition('/')
    assert vendor and name and '/' not in name
    if provider == 'anthropic':
        assert not name[-8:].isdigit(), slug

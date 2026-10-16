"""OpenRouter route selection and model-id mapping for platform LLM calls.

When ``OPENROUTER_API_KEY`` is set, every provider OpenRouter can serve goes
through it with the same model, even if the provider's direct key is also set.
Direct keys stay the path when OpenRouter is not configured. Both the gateway
providers and the backend's direct clients ask this module, so the rule lives in
one place. BYOK clients never consult it: those keys belong to the user.
"""

import os
import re
from typing import Literal

OPENROUTER_API_KEY_ENV = 'OPENROUTER_API_KEY'
OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'

# Providers whose platform traffic OpenRouter serves, with their direct-key env.
_DIRECT_KEY_ENV = {
    'openai': 'OPENAI_API_KEY',
    'anthropic': 'ANTHROPIC_API_KEY',
    'perplexity': 'PERPLEXITY_API_KEY',
}

_OPENROUTER_VENDOR = {'openai': 'openai', 'anthropic': 'anthropic', 'gemini': 'google', 'perplexity': 'perplexity'}

ProviderRoute = Literal['openrouter', 'direct', 'none']


def _env_key(name: str) -> str:
    return os.environ.get(name, '').strip()


def openrouter_api_key() -> str:
    """Return the platform OpenRouter key, or an empty string when unset."""

    return _env_key(OPENROUTER_API_KEY_ENV)


def provider_route(provider: str) -> ProviderRoute:
    """Decide where a platform call for ``provider`` goes.

    Read from the environment on every call rather than cached per process, so
    key rotation and test monkeypatching take effect without a restart.
    """

    if provider not in _DIRECT_KEY_ENV:
        raise ValueError(f"Provider '{provider}' is not routed through OpenRouter")
    if openrouter_api_key():
        return 'openrouter'
    if _env_key(_DIRECT_KEY_ENV[provider]):
        return 'direct'
    return 'none'


def openrouter_model_id(provider: str, model: str) -> str:
    """Map a provider-native model id to its OpenRouter slug.

    OpenRouter names Anthropic versions with a dot and no date suffix:
    claude-haiku-4-5-20251001 -> anthropic/claude-haiku-4.5.
    """

    if '/' in model:
        return model
    if provider == 'openrouter':
        # Models configured for the openrouter provider are already OpenRouter
        # names, except Gemini ids, which the config keeps vendor-native.
        return f'google/{model}' if model.startswith('gemini') else model
    if provider == 'anthropic':
        model = re.sub(r'-\d{8}$', '', model)
        model = re.sub(r'-(\d+)-(\d+)$', r'-\1.\2', model)
    return f'{_OPENROUTER_VENDOR[provider]}/{model}'

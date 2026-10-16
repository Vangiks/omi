"""Regression coverage for the single source of truth governing STT serving."""

from pathlib import Path

import pytest

from config.stt_provider_policy import DEEPGRAM_CLOUD_PROVIDER, DEEPGRAM_SELF_HOSTED_PROVIDER, MODULATE_PROVIDER, PARAKEET_PROVIDER, STTServingSurface, canonical_model_config, deepgram_provider_for_runtime, model_is_enabled, modulate_supports_language, parakeet_supports_language, provider_for_model_token, provider_is_enabled, supports_live_multilingual_mode

def test_hosted_deepgram_serves_streaming_only():
    assert provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.STREAMING)
    # PTT dispatches only Parakeet and Modulate and raises on anything else;
    # batch is carried by Parakeet/Velma.
    assert not provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.PTT)
    assert not provider_is_enabled(DEEPGRAM_CLOUD_PROVIDER, STTServingSurface.PRERECORDED)


def test_self_hosted_deepgram_is_explicitly_limited_to_streaming():
    assert provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.STREAMING)
    assert not provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.PRERECORDED)
    assert not provider_is_enabled(DEEPGRAM_SELF_HOSTED_PROVIDER, STTServingSurface.PTT)


def test_policy_owns_the_safe_model_order_for_every_serving_surface():
    expected = {
        STTServingSurface.STREAMING: 'modulate-velma-2,soniox,dg-nova-3,parakeet',
        STTServingSurface.PRERECORDED: 'parakeet,modulate-velma-2',
        STTServingSurface.PTT: 'modulate-velma-2,parakeet',
    }
    for surface, model_order in expected.items():
        assert canonical_model_config(surface) == model_order
        assert provider_is_enabled(PARAKEET_PROVIDER, surface)
        assert provider_is_enabled(MODULATE_PROVIDER, surface)


def test_deepgram_model_tokens_report_the_hosted_deployment_by_default():
    assert provider_for_model_token('dg-nova-3') == DEEPGRAM_CLOUD_PROVIDER
    assert deepgram_provider_for_runtime(False) == DEEPGRAM_CLOUD_PROVIDER
    assert deepgram_provider_for_runtime(True) == DEEPGRAM_SELF_HOSTED_PROVIDER


def test_deepgram_token_is_admissible_while_either_deployment_serves_the_surface():
    assert model_is_enabled('dg-nova-3', STTServingSurface.STREAMING)
    assert not model_is_enabled('dg-nova-3', STTServingSurface.PRERECORDED)


def test_parakeet_capability_tracks_the_model_selected_for_each_surface():
    assert parakeet_supports_language(STTServingSurface.STREAMING, 'en')
    assert not parakeet_supports_language(STTServingSurface.STREAMING, 'es')
    assert parakeet_supports_language(STTServingSurface.PTT, 'en')
    assert not parakeet_supports_language(STTServingSurface.PTT, 'multi')
    assert parakeet_supports_language(STTServingSurface.PRERECORDED, 'es')
    assert parakeet_supports_language(STTServingSurface.PRERECORDED, 'multi')


def test_live_multilingual_policy_normalizes_supported_locales_and_rejects_unknown_languages():
    assert supports_live_multilingual_mode('zh-TW')
    assert supports_live_multilingual_mode('ar')
    assert modulate_supports_language('es-419')
    assert not supports_live_multilingual_mode('xx-unsupported')


# ---------------------------------------------------------------------------
# #10022: user language preference gate must follow the live policy
# ---------------------------------------------------------------------------


def test_user_language_route_gates_multilingual_mode_by_live_policy():
    """Static tripwire (source order, not behavior): the PATCH /v1/users/language
    preference gate derives single_language_mode from the live STT capability
    policy, and the retired Deepgram Nova-3 multi-language list no longer
    appears in the route module (#10022)."""
    users_py = (Path(__file__).resolve().parents[2] / 'routers' / 'users.py').read_text(encoding='utf-8')
    assert 'single_language_mode = not supports_live_multilingual_mode(language)' in users_py
    assert 'deepgram_nova3_multi_languages' not in users_py


@pytest.mark.parametrize('language', ['vi', 'vi-VN', 'ko', 'tr', 'ar', 'th', 'pt-BR', 'en'])
def test_live_policy_admits_languages_beyond_the_retired_deepgram_list(language):
    """vi/ko/tr/ar/th were wrongly locked into single-language mode by the old
    19-locale Deepgram list; en/pt-BR keep their existing eligibility."""
    assert supports_live_multilingual_mode(language) is True


@pytest.mark.parametrize('language', ['my', 'am', 'lo'])
def test_live_policy_rejects_languages_outside_modulate_auto_detection(language):
    assert supports_live_multilingual_mode(language) is False

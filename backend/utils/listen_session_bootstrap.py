"""Listen WebSocket connect bootstrap — offload sync Firestore reads off the event loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import database.users as user_db
from utils.executors import db_executor, run_blocking
from utils.transcribe_decisions import (
    normalize_language,
    select_translation_language,
    should_force_single_language,
)
from utils.transcribe_store import get_user_transcription_preferences


@dataclass(frozen=True)
class ListenConnectBase:
    user_exists: bool
    transcription_prefs: Dict[str, Any]


@dataclass(frozen=True)
class ListenConnectContext:
    user_exists: bool
    transcription_prefs: Dict[str, Any]
    single_language_mode: bool
    vocabulary: List[str]
    user_language_preference: str
    language: str
    translation_language: Optional[str]


def project_listen_connect_decisions(
    *,
    language: str,
    onboarding_mode: bool,
    transcription_prefs: Dict[str, Any],
    stt_language: str,
) -> tuple[bool, List[str], str, Optional[str]]:
    single_language_mode = transcription_prefs.get('single_language_mode', False)
    vocabulary = list(transcription_prefs.get('vocabulary', []))
    user_language_preference = transcription_prefs.get('language', '')

    single_language_mode = should_force_single_language(onboarding_mode, single_language_mode)
    # Order-preserving dedup: "Omi" must stay first, and user terms retain
    # their priority order (downstream STT only uses vocabulary[:100]).
    vocabulary = list(dict.fromkeys(['Omi'] + vocabulary))
    normalized_language = normalize_language(language)
    translation_language = select_translation_language(
        single_language_mode=single_language_mode,
        stt_language=stt_language,
        language=normalized_language,
        user_language_preference=user_language_preference,
    )
    return single_language_mode, vocabulary, normalized_language, translation_language


async def load_listen_connect_base(uid: str) -> ListenConnectBase:
    """Load connect-time Firestore state off the event loop."""
    user_exists = await run_blocking(db_executor, user_db.is_exists_user, uid)
    transcription_prefs = await run_blocking(db_executor, get_user_transcription_preferences, uid)

    return ListenConnectBase(
        user_exists=user_exists,
        transcription_prefs=transcription_prefs,
    )


def finalize_listen_connect_context(
    base: ListenConnectBase,
    *,
    language: str,
    onboarding_mode: bool,
    stt_language: str,
) -> ListenConnectContext:
    single_language_mode, vocabulary, normalized_language, translation_language = project_listen_connect_decisions(
        language=language,
        onboarding_mode=onboarding_mode,
        transcription_prefs=base.transcription_prefs,
        stt_language=stt_language,
    )
    return ListenConnectContext(
        user_exists=base.user_exists,
        transcription_prefs=base.transcription_prefs,
        single_language_mode=single_language_mode,
        vocabulary=vocabulary,
        user_language_preference=base.transcription_prefs.get('language', ''),
        language=normalized_language,
        translation_language=translation_language,
    )


async def load_listen_connect_context(
    uid: str,
    *,
    language: str,
    onboarding_mode: bool,
    stt_language: str,
) -> ListenConnectContext:
    base = await load_listen_connect_base(uid)
    return finalize_listen_connect_context(
        base,
        language=language,
        onboarding_mode=onboarding_mode,
        stt_language=stt_language,
    )

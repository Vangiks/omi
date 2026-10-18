import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import database.users as users_db
import database.user_usage as user_usage_db
from database.announcements import compare_versions
from config.plan_catalog import (
    DESKTOP_ENTITLED_PLAN_TYPES,
    MOBILE_PLAN_TYPES,
    FULL_ACCESS_PLAN,
    PAID_PLAN_TYPES,
    PLAN_DISPLAY_NAMES,
    PRIMARY_BILLING_ENV_VARS,
    allocation_limit,
    full_access_subscription,
    get_plan_allocation,
    resolve_stripe_price_plan,
)
from models.users import PlanType, Subscription, PlanLimits, TrialMetadata
from utils.byok import get_byok_key, get_byok_uid, get_cached_byok_state, has_validated_byok_keys
from utils.plan_wire_capabilities import understands_plan_identity
import logging

logger = logging.getLogger(__name__)


# Effective desktop tiers are used for Desktop-specific admission decisions.
# Never use DESKTOP_ENTITLED_PLAN_TYPES as a zero-access check: it represents
# full Desktop entitlement, while ``desktop_free`` is a valid usable floor.
DESKTOP_ACCESS_TIER_FREE = "desktop_free"
DESKTOP_ACCESS_TIER_FULL = "desktop_full"
DESKTOP_ACCESS_TIER_ARCHITECT = "desktop_architect"

# Grandfather: Neo subscriptions whose current billing period started before
# this cutoff retain desktop access until that period ends. At their next
# renewal, current_period_start advances past the cutoff and they fall under
# the new policy. Default is the merge timestamp of #7496 — the PR that first
# removed Neo from DESKTOP_ENTITLED_PLAN_TYPES — so users who bought Neo when
# desktop was de facto included aren't pulled mid-cycle. Env-overridable so
# the cutoff can shift if the policy date changes.
NEO_DESKTOP_GRANDFATHER_CUTOFF = int(os.getenv('NEO_DESKTOP_GRANDFATHER_CUTOFF', '1779748479'))


def plan_grants_desktop(plan: PlanType, subscription: Optional[Subscription] = None) -> bool:
    """True iff this plan unlocks the desktop (macOS) app for this subscriber.

    Operator and Architect always grant desktop. Neo grants desktop only under
    the legacy grandfather: when the subscription's current_period_start is
    before NEO_DESKTOP_GRANDFATHER_CUTOFF (or is None — existing pre-deploy
    subs without the field set are treated as legacy until their next webhook
    populates the field).
    """
    if plan in DESKTOP_ENTITLED_PLAN_TYPES:
        return True
    if plan == PlanType.unlimited and subscription is not None:
        cps = subscription.current_period_start
        if cps is None or cps < NEO_DESKTOP_GRANDFATHER_CUTOFF:
            return True
    return False


def effective_desktop_access_tier(plan: PlanType, subscription: Optional[Subscription] = None) -> str:
    """Return the usable Desktop tier for a subscription.

    Free is the minimum Desktop tier. A Neo (``unlimited``) subscriber who is
    not in the full-Desktop grandfather period therefore receives
    ``desktop_free`` rather than no Desktop access. Operator and grandfathered
    Neo receive ``desktop_full``; Architect receives its separate premium tier.
    """
    if plan == PlanType.architect:
        return DESKTOP_ACCESS_TIER_ARCHITECT
    if plan_grants_desktop(plan, subscription):
        return DESKTOP_ACCESS_TIER_FULL
    return DESKTOP_ACCESS_TIER_FREE


def neo_grandfather_until(subscription: Optional[Subscription]) -> Optional[int]:
    """If the subscriber is currently grandfathered onto Neo desktop, return
    the unix-seconds timestamp when that access ends (their current period end).
    Otherwise None. Used by the API response so the desktop client can render a
    "Neo desktop access ends on <date>" notice.
    """
    if subscription is None or subscription.plan != PlanType.unlimited:
        return None
    if not plan_grants_desktop(subscription.plan, subscription):
        return None
    return subscription.current_period_end


# Length of the former desktop trial. `/v1/users/me/trial` still reports it until
# the subscription endpoints go; the fork has no trial, so it never expires.
TRIAL_LENGTH_SECONDS = 3 * 24 * 60 * 60  # 3 days

# X-App-Platform header values that identify a desktop client. macOS and Windows
# are the two desktop OSes; both get the desktop plan catalog and desktop
# entitlement treatment. This is the single source of truth
# for "is this a desktop platform" — every desktop-vs-mobile gate below reads
# from here so a new desktop OS is wired in one place.
DESKTOP_PLATFORMS = {'macos', 'windows'}

# Desktop typed chat consumes Anthropic BYOK, not an arbitrary enrolled LLM
# key. Reporting and enforcement must project the same provider capability.
DESKTOP_CHAT_BYOK_PROVIDER = 'anthropic'


def request_has_llm_byok_key() -> bool:
    """True when request carries validated LLM BYOK keys matching active enrollment."""
    uid = get_byok_uid()
    if not uid or not has_validated_byok_keys():
        return False
    try:
        fingerprints = get_cached_byok_state(uid).get('fingerprints', {})
    except Exception:
        return any(get_byok_key(provider) for provider in ('openrouter', 'openai', 'anthropic', 'gemini'))
    return any(
        provider in fingerprints and bool(get_byok_key(provider))
        for provider in ('openrouter', 'openai', 'anthropic', 'gemini')
    )


def request_has_byok_provider(provider: str) -> bool:
    """Whether the request carries a validated key for this exact provider."""
    return has_validated_byok_keys() and bool(get_byok_key(provider))


def get_trial_metadata(uid: str) -> TrialMetadata:
    """Trial metadata for `/v1/users/me/trial`. The fork has no trial: it never expires."""
    return TrialMetadata(
        trial_expired=False,
        trial_duration_seconds=TRIAL_LENGTH_SECONDS,
        trial_features=TRIAL_FEATURES,
        plan_after_trial=get_plan_display_name(PlanType.basic),
    )


def is_paid_plan(plan: PlanType) -> bool:
    return plan in PAID_PLAN_TYPES


def _configured_plan_price_id(plan: PlanType, interval: str) -> Optional[str]:
    return os.getenv(PRIMARY_BILLING_ENV_VARS[plan][interval])


def get_paid_plan_definitions() -> List[Dict[str, Any]]:
    """All plan definitions.

    Unlimited is kept as legacy so existing subscribers keep their access
    and their stored plans still resolve, but it's filtered out of the "new user"
    purchase catalog via `filter_plans_for_user`.
    """
    return [
        {
            "plan_type": PlanType.unlimited,
            "plan_id": "unlimited",
            "title": "Neo",
            "subtitle": f"{_chat_allowance_text(PlanType.unlimited)}",
            "description": f"{_chat_allowance_text(PlanType.unlimited)}. Shared with mobile and web.",
            "eyebrow": "Starter",
            "monthly_price_id": _configured_plan_price_id(PlanType.unlimited, 'month'),
            "annual_price_id": _configured_plan_price_id(PlanType.unlimited, 'year'),
            "annual_description": "Save ~17% with annual billing.",
            "legacy": False,
        },
        {
            "plan_type": PlanType.operator,
            "plan_id": "operator",
            "title": "Operator",  # Released macOS title parsers infer price ownership from this.
            "subtitle": f"{_chat_allowance_text(PlanType.operator)}",
            "description": f"{_chat_allowance_text(PlanType.operator)}. Shared with mobile and web.",
            "eyebrow": "Most popular",
            "monthly_price_id": _configured_plan_price_id(PlanType.operator, 'month'),
            "annual_price_id": _configured_plan_price_id(PlanType.operator, 'year'),
            "annual_description": "Save ~17% with annual billing.",
            "legacy": False,
        },
        {
            "plan_type": PlanType.architect,
            "plan_id": "architect",
            "title": "Architect",
            "subtitle": "Power-user AI — thousands of chats + agentic automations",
            "description": "Power-user AI for heavy agentic workflows and vibe coding.",
            "eyebrow": "Automation + coding",
            "monthly_price_id": _configured_plan_price_id(PlanType.architect, 'month'),
            "annual_price_id": _configured_plan_price_id(PlanType.architect, 'year'),
            "annual_description": "Save with annual billing.",
            "legacy": False,
        },
        {
            "plan_type": PlanType.plus,
            "plan_id": "plus",
            "title": "Plus",
            "subtitle": f"{_transcription_allowance_text(PlanType.plus)}",
            "description": f"{_transcription_allowance_text(PlanType.plus)}.",
            "eyebrow": "For everyday use",
            "monthly_price_id": _configured_plan_price_id(PlanType.plus, 'month'),
            "annual_price_id": _configured_plan_price_id(PlanType.plus, 'year'),
            "annual_description": "Save with annual billing.",
            "legacy": False,
        },
        {
            "plan_type": PlanType.unlimited_v2,
            "plan_id": "unlimited_v2",
            "title": "Unlimited",
            "subtitle": "Unlimited transcription",
            "description": "Unlimited transcription — record all day.",
            "eyebrow": "Most popular",
            "monthly_price_id": _configured_plan_price_id(PlanType.unlimited_v2, 'month'),
            "annual_price_id": _configured_plan_price_id(PlanType.unlimited_v2, 'year'),
            "annual_description": "Save with annual billing.",
            "legacy": False,
        },
    ]


# Platform identifiers for the two mobile clients (X-App-Platform header).
_MOBILE_PLATFORM_TOKENS = {'ios', 'android'}

# The web storefront (X-App-Platform: web). It's an always-latest client that
# renders the full new catalog (Plus + Unlimited + Operator + Architect) and is
# the primary checkout surface; only deprecated Neo is hidden there.
WEB_PLATFORMS = {'web'}


def _platform_hidden_plans(platform: Optional[str]) -> Set[PlanType]:
    """Plans hidden from the purchase catalog per platform.

    Mobile sells Plus + Unlimited; desktop sells Operator + Architect; web sells
    all four. Neo is deprecated everywhere and hidden on every platform. A
    subscriber on a hidden plan still sees it via `filter_plans_for_user`'s
    current-plan escape (Neo) or the mobile manage-only fast path (Operator /
    Architect). See .github/agent-docs/plan-catalog.md.
    """
    p = (platform or '').lower()
    if p in _MOBILE_PLATFORM_TOKENS:
        return {PlanType.unlimited, PlanType.operator, PlanType.architect}
    if p in DESKTOP_PLATFORMS:
        return {PlanType.unlimited, PlanType.plus, PlanType.unlimited_v2}
    if p in WEB_PLATFORMS:
        return {PlanType.unlimited}
    return set()


def desktop_to_consumer_plan_change_error(current_plan: PlanType, target_plan: PlanType) -> Optional[str]:
    """Error text if a desktop-entitled plan would be swapped onto a consumer tier.

    Operator and Architect are manage-only from mobile: cancel or wait out the
    period. Immediate proration onto Plus / Unlimited / Neo strips desktop.
    Same-family desktop changes (Operator ↔ Architect) stay allowed for the
    desktop and web storefronts. Do not add a "user confirmed in the app"
    exception — confirmation is not this boundary. See .github/agent-docs/plan-catalog.md.
    """
    if current_plan in DESKTOP_ENTITLED_PLAN_TYPES and target_plan not in DESKTOP_ENTITLED_PLAN_TYPES:
        return (
            "This plan is managed from desktop. Switching to a mobile plan is not "
            "available here. Cancel at period end or contact support."
        )
    return None


def filter_plans_for_user(
    definitions: List[Dict[str, Any]],
    current_plan: PlanType,
    platform: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Drop legacy / platform-hidden plans from the purchase catalog.

    Locked audience rules (.github/agent-docs/plan-catalog.md) — do not re-widen:

    1. Neo (`unlimited`) is shown only when `current_plan` is already Neo
       (active or cancel-at-period-end). Never gate it on "has ever paid".
    2. On mobile, Operator / Architect are manage-only: return *only* the
       current desktop plan so cheaper mobile tiers cannot be purchased
       from the phone. Desktop and web keep selling both.
    3. Fully churned ex-Neo users are `basic` and receive Plus + Unlimited,
       the replacement catalog, not the deprecated Neo SKU.

    The current-plan escape still applies on desktop/web so a Neo subscriber
    opening those surfaces can manage/cancel.
    """
    is_mobile = (platform or '').lower() in _MOBILE_PLATFORM_TOKENS
    if is_mobile and current_plan in DESKTOP_ENTITLED_PLAN_TYPES:
        return [d for d in definitions if d.get('plan_type') == current_plan]

    hidden = _platform_hidden_plans(platform)
    out: List[Dict[str, Any]] = []
    for d in definitions:
        plan_type = d.get('plan_type')
        if d.get('legacy') and plan_type != current_plan:
            continue
        if plan_type in hidden and plan_type != current_plan:
            continue
        out.append(d)
    return out


# Minimum macOS desktop build that ships with the new plan catalog + quota UI.
NEW_PLANS_MIN_DESKTOP_VERSION = os.getenv('NEW_PLANS_MIN_DESKTOP_VERSION', '0.11.324')

# Minimum Windows desktop build that ships the new plan catalog. Windows is
# pre-release and versions independently of macOS, so this defaults permissive
# ('0.0.0' → every Windows build qualifies); set a floor once Windows ships a
# build that must be gated out.
NEW_PLANS_MIN_WINDOWS_VERSION = os.getenv('NEW_PLANS_MIN_WINDOWS_VERSION', '0.0.0')

# Minimum mobile build that ships with the `operator` enum value and new plan UI.
# Mobile builds below this version get the legacy catalog with operator→unlimited mapping.
NEW_PLANS_MIN_MOBILE_VERSION = os.getenv('NEW_PLANS_MIN_MOBILE_VERSION', '1.0.530')

# Per-desktop-platform minimum client version that understands the Operator +
# Architect plan shape. Desktop platforms fail *open* (a missing/unparseable
# version still gets the new catalog); mobile fails *closed* (old builds crash
# on the operator enum).
_NEW_PLANS_MIN_DESKTOP_VERSION_BY_PLATFORM = {
    'macos': NEW_PLANS_MIN_DESKTOP_VERSION,
    'windows': NEW_PLANS_MIN_WINDOWS_VERSION,
}


def should_show_new_plans(platform: Optional[str], app_version: Optional[str]) -> bool:
    """True iff this caller's client understands the Operator + Architect plan shape.

    Desktop (macOS / Windows): any build at or above the platform's minimum
    qualifies; a missing or unparseable version defaults to the new catalog
    (macOS shipped it long ago, Windows is pre-release).
    Mobile (android/ios): any build at or above NEW_PLANS_MIN_MOBILE_VERSION
    qualifies; a missing or unparseable version defaults to the legacy catalog
    (old mobile builds crash on the operator enum).
    Web: always the new catalog (it's an always-latest client, version-agnostic).
    Unknown platform: legacy catalog.
    """
    if not platform:
        return False

    platform_lower = platform.lower()

    if platform_lower in WEB_PLATFORMS:
        return True

    if platform_lower in DESKTOP_PLATFORMS:
        if not app_version:
            return True
        try:
            return compare_versions(app_version, _NEW_PLANS_MIN_DESKTOP_VERSION_BY_PLATFORM[platform_lower]) >= 0
        except Exception:
            return True

    if platform_lower in _MOBILE_PLATFORM_TOKENS:
        if not app_version:
            return False
        try:
            return compare_versions(app_version, NEW_PLANS_MIN_MOBILE_VERSION) >= 0
        except Exception:
            return False

    return False


def wire_plan_for_client(
    plan: PlanType, platform: Optional[str], app_version: Optional[str], plan_identity_version: Optional[str] = None
) -> PlanType:
    """Remap labels for old decoders; entitlement/limits use the true plan."""
    if plan in MOBILE_PLAN_TYPES and not understands_plan_identity(
        platform, app_version, plan_identity_version, compare_versions
    ):
        return PlanType.unlimited
    return plan


def adapt_plans_for_legacy_client(definitions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Transform the new-shape plan catalog back into the pre-v0.11.324 shape
    so older clients (mobile, stable desktop) keep showing the old plan titles
    and don't see desktop-only plans.

    Hides Operator and Architect (pro) entirely — both are desktop-only.
    Drops the legacy suffix + flag from Unlimited so pre-rollout clients
    still see it as "Omi Unlimited".
    """
    out: List[Dict[str, Any]] = []
    for d in definitions:
        if d['plan_id'] in ('operator', 'pro'):
            continue
        adapted = dict(d)
        if d['plan_id'] == 'architect':
            adapted['title'] = 'Omi Pro'
        elif d['plan_id'] == 'unlimited':
            adapted['title'] = 'Unlimited Plan'
            adapted['legacy'] = False
        out.append(adapted)
    return out


def legacy_plan_features(plan: PlanType) -> List[str]:
    """Feature strings matching the pre-v0.11.324 plan catalog.

    Mirrors what `get_plan_features` used to return before the Operator /
    Architect rename so older clients' UI doesn't change under them.
    """
    if plan == PlanType.architect:
        return [
            "Automations",
            "Vibe coding",
            "Unlimited actions",
            "Priority desktop AI features",
        ]
    if plan in (PlanType.unlimited, PlanType.operator):
        return [
            "Unlimited listening time",
            "Unlimited words transcribed",
            "Unlimited insights",
            "Unlimited memories",
        ]
    return get_plan_features(plan)


def get_plan_type_from_price_id(price_id: str) -> PlanType:
    """Resolve retained and configured plan prices through the catalog."""

    return resolve_stripe_price_plan(price_id)


_basic_tier_seconds_raw = allocation_limit(PlanType.basic, 'transcription')
if _basic_tier_seconds_raw is None:
    # allocation_limit returns None for an unlimited allocation. Free is metered by
    # design, so an unlimited basic transcription allowance is a catalog authoring
    # mistake, not a configuration choice. Fail with a sentence that says what is
    # wrong rather than letting `None // 60` raise TypeError at import time.
    raise ValueError(
        'basic.transcription must declare a finite allowance; an unlimited free tier '
        'would make transcription spend unbounded per user'
    )

# Narrowed above, so the rest of the module (and pyright) can treat it as a plain int.
_BASIC_TIER_SECONDS_DEFAULT: int = _basic_tier_seconds_raw


def _legacy_overlay(env_name: str) -> Tuple[bool, Optional[int]]:
    """Read a pre-catalog quota overlay, honoring the sentinel it was written under.

    These env vars predate the catalog and were authored when ``0`` meant
    *unlimited* -- production sets BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH and
    BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH to exactly ``0`` on that meaning.
    The catalog retires the sentinel, but retiring it must not silently
    *reinterpret configuration that is already deployed*: reading those zeros as a
    finite zero would hand every Free user a zero words/insights allowance and
    advertise "0 words transcribed per month".

    So the sentinel is honored where the legacy value is read, and only there. The
    catalog's own values use the typed representation and are untouched. D2 deletes
    these overlays, and this bridge goes with them.

    Returns ``(present, value)``; ``value`` is ``None`` for a legacy unlimited zero.
    """
    raw = os.getenv(env_name)
    if raw is None:
        return False, None
    parsed = int(raw)
    return True, (None if parsed == 0 else parsed)


def _basic_transcription_overlay() -> Tuple[int, Optional[int]]:
    """Resolve ``(minutes, seconds)`` for Free transcription.

    ``seconds`` is ``None`` when the allowance is unlimited. Charts currently set
    300, so the legacy-zero branch is latent -- but reading a deployed ``0`` as a
    finite zero would show every Free user a zero allowance, the same inversion as
    words/insights.
    """
    present, value = _legacy_overlay('BASIC_TIER_MINUTES_LIMIT_PER_MONTH')
    if not present:
        return _BASIC_TIER_SECONDS_DEFAULT // 60, _BASIC_TIER_SECONDS_DEFAULT
    if value is None:
        return 0, None
    return value, value * 60


BASIC_TIER_MINUTES_LIMIT_PER_MONTH, BASIC_TIER_MONTHLY_SECONDS_LIMIT = _basic_transcription_overlay()


def _catalog_or_legacy_basic_limit(allocation: str) -> Optional[int]:
    """Return a catalog limit, preserving the temporary Basic env overlays.

    D2 removes these per-service plan quota overlays. Until then, the catalog
    remains the default and a configured overlay remains effective at runtime.
    ``None`` is the only unlimited representation; zero is a finite zero.
    """
    catalog_value = allocation_limit(PlanType.basic, allocation)
    legacy_env_names = {
        'words_transcribed': 'BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH',
        'insights_gained': 'BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH',
    }
    env_name = legacy_env_names.get(allocation)
    if env_name is None:
        return catalog_value
    present, overlay = _legacy_overlay(env_name)
    return overlay if present else catalog_value


BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH = _catalog_or_legacy_basic_limit('words_transcribed')
BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH = _catalog_or_legacy_basic_limit('insights_gained')

# Fixed non-human UID the desktop-backend release probe signs in as
# (`PROBE_UID` in backend/scripts/firebase_release_probe_token.py). Its chat turns
# are deploy-gate traffic, not a user's questions, so they must never be metered
# against a plan cap — otherwise the gate blocks itself once the probe's own turns
# exhaust the Free allowance and every desktop-backend deploy fails with 402.
RELEASE_PROBE_UID = 'omi-release-probe'


def _effective_plan_limit(plan: PlanType, allocation: str) -> Optional[int]:
    """Resolve a typed allocation from the catalog plus temporary legacy overlays."""
    catalog_value = allocation_limit(plan, allocation)
    if plan == PlanType.basic:
        if allocation == 'transcription':
            return BASIC_TIER_MONTHLY_SECONDS_LIMIT
        return _catalog_or_legacy_basic_limit(allocation)
    if plan == PlanType.plus and allocation == 'transcription':
        raw_minutes = os.getenv('PLUS_TIER_MINUTES_LIMIT_PER_MONTH')
        return int(raw_minutes) * 60 if raw_minutes is not None else catalog_value
    return catalog_value


def _legacy_chat_env_name(plan: PlanType, unit: str) -> str:
    """Return the historical chat overlay name for a catalog plan/unit."""
    prefix = {'basic': 'FREE', 'unlimited': 'NEO'}.get(plan.value, plan.value.upper())
    if unit == 'question':
        return f'{prefix}_CHAT_QUESTIONS_PER_MONTH'
    if unit == 'usd_cent':
        return 'ARCHITECT_CHAT_COST_USD_PER_MONTH'
    raise ValueError(f'{plan.value}.chat has unsupported catalog unit {unit!r}')


def _effective_chat_limit(plan: PlanType) -> Optional[int]:
    """Return the catalog chat limit in its declared unit.

    Chat env overlays are retained only as a migration bridge until D2 removes
    plan quota values from service configuration. Reporting and admission both
    call this helper, so an overlay cannot recreate the old B3 disagreement.
    """
    allocation = get_plan_allocation(plan, 'chat')
    unit = allocation['unit']
    catalog_value = allocation_limit(plan, 'chat')
    env_name = _legacy_chat_env_name(plan, unit)
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return catalog_value
    if unit == 'question':
        return int(raw_value)
    if unit == 'usd_cent':
        return int(round(float(raw_value) * 100))
    raise ValueError(f'{plan.value}.chat has unsupported catalog unit {unit!r}')


def _chat_allowance_text(plan: PlanType) -> str:
    allocation = get_plan_allocation(plan, 'chat')
    limit = _effective_chat_limit(plan)
    if allocation['unit'] == 'question':
        if limit is None:
            return 'Unlimited chat questions per month'
        # Keep the word "chat": the pre-catalog copy was
        # "{N} chat questions per month. Shared with mobile and web." and this is
        # user-visible storefront text. A consolidation must not quietly reword the
        # product; changing it is a copy decision, not a refactor.
        return f'{limit} chat questions per month'
    if allocation['unit'] == 'usd_cent':
        if limit is None:
            return 'Unlimited AI compute per month'
        return f'~${limit / 100:g} of monthly AI compute included'
    raise ValueError(f'{plan.value}.chat has unsupported catalog unit {allocation["unit"]!r}')


def _transcription_allowance_text(plan: PlanType) -> str:
    limit = _effective_plan_limit(plan, 'transcription')
    if limit is None:
        return 'Unlimited transcription'
    return f'{limit // 60:,} minutes of transcription per month'


# Compatibility names for callers and fixtures still importing the old
# projections. These are derived values, not plan policy sources; all runtime
# decisions below resolve the catalog allocation through the helpers above.
FREE_CHAT_QUESTIONS_PER_MONTH = _effective_chat_limit(PlanType.basic)
NEO_CHAT_QUESTIONS_PER_MONTH = _effective_chat_limit(PlanType.unlimited)
OPERATOR_CHAT_QUESTIONS_PER_MONTH = _effective_chat_limit(PlanType.operator)
_architect_chat_cents = _effective_chat_limit(PlanType.architect)
ARCHITECT_CHAT_COST_USD_PER_MONTH = None if _architect_chat_cents is None else _architect_chat_cents / 100.0
PLUS_TIER_MONTHLY_SECONDS_LIMIT = _effective_plan_limit(PlanType.plus, 'transcription')
PLUS_TIER_MINUTES_LIMIT_PER_MONTH = (
    None if PLUS_TIER_MONTHLY_SECONDS_LIMIT is None else PLUS_TIER_MONTHLY_SECONDS_LIMIT // 60
)
PLUS_CHAT_QUESTIONS_PER_MONTH = _effective_chat_limit(PlanType.plus)
UNLIMITED_V2_CHAT_QUESTIONS_PER_MONTH = _effective_chat_limit(PlanType.unlimited_v2)


# Features available during the 3-day desktop trial (matches paid-plan behavior).
TRIAL_FEATURES = [
    'unlimited_listening',
    'unlimited_transcription',
    'unlimited_memories',
    'unlimited_insights',
    f'{_effective_chat_limit(PlanType.basic)}_chat_questions_per_month',
]


def get_plan_display_name(plan: PlanType) -> str:
    return PLAN_DISPLAY_NAMES.get(plan, plan.value.capitalize())


def get_chat_quota_snapshot(
    uid: str,
    platform: Optional[str] = None,
    *,
    firestore_client: Any | None = None,
    provision: bool = True,
    required_llm_provider: str | None = None,
) -> Dict[str, Any]:
    """Cheap computation of `is_allowed / used / limit / unit / plan` for the
    `/v1/users/me/usage-quota` endpoint."""
    subscription = users_db.get_user_valid_subscription(uid, firestore_client=firestore_client, provision=provision)
    plan = subscription.plan if subscription else PlanType.basic
    limits = get_plan_limits(plan)
    usage = user_usage_db.get_monthly_chat_usage(uid, firestore_client=firestore_client)

    chat_unit = get_plan_allocation(plan, 'chat')['unit']
    if chat_unit == 'usd_cent':
        unit = 'cost_usd'
        used = float(usage['cost_usd'])
        limit_value = None if limits.chat_cost_usd_per_month is None else float(limits.chat_cost_usd_per_month)
    elif chat_unit == 'question':
        unit = 'questions'
        used = float(usage['questions'])
        limit_value = float(limits.chat_questions_per_month) if limits.chat_questions_per_month is not None else None
    else:
        raise ValueError(f'{plan.value}.chat has unsupported catalog unit {chat_unit!r}')

    allowed = True
    if limit_value is not None:
        allowed = used < limit_value

    return {
        'plan': plan,
        'unit': unit,
        'used': used,
        'limit': limit_value,
        'allowed': allowed,
        'reset_at': usage['reset_at'],
    }


def get_basic_plan_limits() -> PlanLimits:
    """Returns the PlanLimits object for the basic (Free) tier."""
    return get_plan_limits(PlanType.basic)


def get_default_basic_subscription() -> Subscription:
    """Returns a default Subscription object for the basic plan."""
    return Subscription(limits=get_basic_plan_limits())


def get_full_access_subscription() -> Subscription:
    """The subscription every user has in the fork (#3)."""
    return Subscription(**full_access_subscription(), limits=get_plan_limits(FULL_ACCESS_PLAN))


def get_plan_limits(plan: PlanType) -> PlanLimits:
    """Return typed limits projected from the catalog allocation row.

    ``None`` means the catalog explicitly declared ``kind=unlimited``. A
    finite zero remains zero and is therefore enforced as exhausted.
    """
    plan = PlanType(plan)
    chat_allocation = get_plan_allocation(plan, 'chat')
    chat_limit = _effective_chat_limit(plan)
    chat_questions: Optional[int] = None
    chat_cost_usd: Optional[float] = None
    if chat_allocation['unit'] == 'question':
        chat_questions = chat_limit
    elif chat_allocation['unit'] == 'usd_cent':
        chat_cost_usd = None if chat_limit is None else chat_limit / 100.0
    else:
        raise ValueError(f'{plan.value}.chat has unsupported catalog unit {chat_allocation["unit"]!r}')

    return PlanLimits(
        transcription_seconds=_effective_plan_limit(plan, 'transcription'),
        words_transcribed=_effective_plan_limit(plan, 'words_transcribed'),
        insights_gained=_effective_plan_limit(plan, 'insights_gained'),
        chat_questions_per_month=chat_questions,
        chat_cost_usd_per_month=chat_cost_usd,
    )


def get_plan_features(plan: PlanType, simplified: bool = False) -> List[str]:
    """Returns the list of feature strings for the given plan.

    Args:
        plan: The plan type.
        simplified: If True, returns only plan-differentiating features (for mobile),
                    omitting items already shown in the top-level highlights section.
                    If False, returns the full feature list (for desktop).
    """
    chat_feature = _chat_allowance_text(plan)
    transcription_feature = _transcription_allowance_text(plan)
    definition = get_plan_allocation(plan, 'transcription')

    if get_plan_allocation(plan, 'chat')['unit'] == 'usd_cent':
        if simplified:
            return [
                "Automations and vibe coding",
                "Priority desktop AI features",
                chat_feature,
            ]
        return [
            "Automations and vibe coding",
            "Unlimited listening, memories, and insights",
            "Priority desktop AI features",
            chat_feature,
        ]

    if plan in (PlanType.operator, PlanType.unlimited):
        if simplified:
            return [chat_feature]
        return [
            chat_feature,
            "Unlimited listening and transcription",
            "Unlimited memories and insights",
            (
                "Available on Mac, mobile, and web"
                if plan == PlanType.operator
                else "Desktop capture with Free-tier allowance"
            ),
        ]

    if plan == PlanType.basic:
        limits = get_plan_limits(plan)
        transcription_limit = limits.transcription_seconds
        words_limit = limits.words_transcribed
        insights_limit = limits.insights_gained
        return [
            (
                f'{transcription_limit // 60:,} minutes of listening per month'
                if transcription_limit is not None
                else 'Unlimited listening'
            ),
            (
                f'{words_limit:,} words transcribed per month'
                if words_limit is not None
                else 'Unlimited words transcribed'
            ),
            (f'{insights_limit:,} insights per month' if insights_limit is not None else 'Unlimited insights'),
            'Unlimited memories',
        ]

    if definition['limit']['kind'] == 'finite':
        if simplified:
            return [
                transcription_feature,
                chat_feature,
            ]
        return [
            transcription_feature,
            chat_feature,
            "Unlimited memories and insights",
        ]

    if simplified:
        return [transcription_feature, chat_feature]
    return [transcription_feature, chat_feature, "Unlimited memories and insights"]


def get_monthly_usage_for_subscription(uid: str) -> Dict[str, Any]:
    """
    Gets the current monthly usage for subscription purposes, considering the launch date from env variables.
    The launch date format is expected to be YYYY-MM-DD.
    If the launch date is not set, not valid, or in the future, usage is considered zero.
    """
    subscription_launch_date_str = os.getenv('SUBSCRIPTION_LAUNCH_DATE')
    if not subscription_launch_date_str:
        # Subscription not launched, so no usage is counted against limits.
        return {}

    try:
        # Use strptime to enforce YYYY-MM-DD format
        launch_date = datetime.strptime(subscription_launch_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError:
        # Invalid date format, treat as not launched.
        return {}

    now = datetime.now(timezone.utc)
    if now < launch_date:
        # Launch date is in the future, so no usage is counted yet.
        return {}

    return user_usage_db.get_monthly_usage_stats_since(uid, now, launch_date)


def transcription_allowance_seconds(plan: PlanType) -> Optional[int]:
    """The plan's managed transcription allowance, from the catalog alone.

    ``None`` is unlimited. Deliberately not ``get_plan_limits``: that path lets
    the ``BASIC_TIER_MINUTES_LIMIT_PER_MONTH`` / ``PLUS_TIER_MINUTES_LIMIT_PER_MONTH``
    environment overlays outrank the catalog, and no plan quota may be read
    from the environment (NOW.md item 4). Production's overlay equals the
    catalog today (basic 300 min, plus 1,500 min), so this changes no served
    number there; only a divergent overlay (dev's) stops applying.
    """
    return allocation_limit(plan, 'transcription')

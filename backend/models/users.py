from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field


class WebhookType(str, Enum):
    audio_bytes = 'audio_bytes'
    audio_bytes_websocket = 'audio_bytes_websocket'
    realtime_transcript = 'realtime_transcript'
    memory_created = ('memory_created',)
    day_summary = 'day_summary'
    button_event = 'button_event'


def webhook_url_from_setting(wtype: WebhookType | str, value: Optional[str]) -> str:
    """The endpoint a stored webhook setting points at, or '' when none is configured.

    audio_bytes stores '<url>,<seconds>', so clearing only the URL leaves a ',5' setting
    that is not an empty string yet has nowhere to deliver to. Every caller deciding
    whether a webhook is configured must read the setting through here.
    """
    if not value:
        return ''
    # WebhookType is a str enum, so this holds for the raw wire value too.
    if wtype == WebhookType.audio_bytes:
        value = value.split(',')[0]
    return value.strip()


LOCATION_CONTEXT_PURPOSE = 'chat_city_context'
LOCATION_CONTEXT_DISCLOSED_PROVIDERS = ('Google Maps', 'the configured AI chat provider')


class LocationContextConsentStatus(str, Enum):
    granted = 'granted'
    revoked = 'revoked'


class LocationContextConsent(BaseModel):
    """Server-owned authorization for city-only context in interactive chat."""

    status: LocationContextConsentStatus
    purpose: str
    disclosed_providers: tuple[str, str]
    granted_at: datetime
    expires_at: datetime
    revoked_at: Optional[datetime] = None

    def is_active(self, now: Optional[datetime] = None) -> bool:
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None or self.granted_at.tzinfo is None or self.expires_at.tzinfo is None:
            return False
        return (
            self.status is LocationContextConsentStatus.granted
            and self.revoked_at is None
            and self.purpose == LOCATION_CONTEXT_PURPOSE
            and self.disclosed_providers == LOCATION_CONTEXT_DISCLOSED_PROVIDERS
            and self.granted_at <= current_time
            and self.expires_at > current_time
        )


class LocationContextConsentUpdate(BaseModel):
    enabled: bool
    disclosure_accepted: bool = Field(
        default=False,
        description=(
            'Required to enable city context: Google Maps reverse-geocodes the device location and the configured '
            'AI chat provider receives city, region, and country only.'
        ),
    )


class LocationContextConsentResponse(BaseModel):
    enabled: bool
    purpose: str = LOCATION_CONTEXT_PURPOSE
    disclosed_providers: tuple[str, str] = LOCATION_CONTEXT_DISCLOSED_PROVIDERS
    expires_at: Optional[datetime] = None


class AvailableLanguage(BaseModel):
    code: str
    name: str


class AvailableLanguagesResponse(BaseModel):
    languages: List[AvailableLanguage]

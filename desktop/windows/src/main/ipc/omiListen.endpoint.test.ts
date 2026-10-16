import { afterEach, describe, it, expect, vi } from 'vitest'
import WebSocket from 'ws'
import { buildListenEndpoint, shouldSendKeepalive, isSocketStale } from './omiListen'

describe('buildListenEndpoint', () => {
  it('conversation mode hits /v4/listen with the full pipeline params', () => {
    const url = buildListenEndpoint('conversation', 'en')
    expect(url).toContain('/v4/listen')
    expect(url).toContain('codec=pcm16')
    expect(url).toContain('include_speech_profile=true')
    expect(url).toContain('speaker_auto_assign=enabled')
    expect(url).toContain('source=desktop')
  })

  it('ptt mode hits the transcription-only endpoint (no conversation lifecycle)', () => {
    const url = buildListenEndpoint('ptt', 'en')
    expect(url).toContain('/v2/voice-message/transcribe-stream')
    // The bleed regression: PTT must NOT ride the /v4/listen conversation pipeline,
    // whose per-uid server-side conversation replayed a prior hold's segments into
    // the next capture.
    expect(url).not.toContain('/v4/listen')
    expect(url).not.toContain('include_speech_profile')
    expect(url).not.toContain('speaker_auto_assign')
  })

  it('ptt uses codec=linear16 — the transcribe-stream endpoint rejects pcm16 (1008)', () => {
    const url = buildListenEndpoint('ptt', 'en')
    expect(url).toContain('codec=linear16')
    expect(url).not.toContain('codec=pcm16')
  })

  it('carries the language through (defaulting to en) for both modes', () => {
    expect(buildListenEndpoint('ptt', 'es')).toContain('language=es')
    expect(buildListenEndpoint('conversation', 'es')).toContain('language=es')
    expect(buildListenEndpoint('ptt', '')).toContain('language=en')
  })

  it('transcribe mode (screen lanes) rides the same transcription-only endpoint as ptt', () => {
    // The coalescing race: two same-uid /v4/listen sockets split/bleed via a racy
    // user-global Redis pointer, so screen lanes must NEVER hit /v4/listen. They
    // stream transcription-only and the conversation is created client-side on
    // stop via POST /v1/conversations/from-segments.
    const url = buildListenEndpoint('transcribe', 'en')
    expect(url).toBe(buildListenEndpoint('ptt', 'en'))
    expect(url).toContain('/v2/voice-message/transcribe-stream')
    expect(url).toContain('codec=linear16')
    expect(url).not.toContain('/v4/listen')
  })

  it('resumes the same conversation by forwarding client_conversation_id (conversation mode)', () => {
    // The reconnect-resume contract: a dropped /v4/listen must reconnect with the
    // SAME id so the backend resumes the in-progress conversation instead of
    // stranding a half-recorded one (transcribe.py keys the conversation on it).
    const url = buildListenEndpoint('conversation', 'en', 'ab12cd34-0000-0000-0000-000000000000')
    expect(url).toContain('client_conversation_id=ab12cd34-0000-0000-0000-000000000000')
  })

  it('omits client_conversation_id when none is given, and never sends it on transcription-only endpoints', () => {
    expect(buildListenEndpoint('conversation', 'en')).not.toContain('client_conversation_id')
    // transcribe/ptt have no server-side conversation to key — the param is meaningless there.
    expect(buildListenEndpoint('ptt', 'en', 'ab12cd34-0000-0000-0000-000000000000')).not.toContain(
      'client_conversation_id'
    )
    expect(
      buildListenEndpoint('transcribe', 'en', 'ab12cd34-0000-0000-0000-000000000000')
    ).not.toContain('client_conversation_id')
  })
})

// The host follows VITE_OMI_API_BASE (https → wss, http → ws), so the
// local-backend profile records into the Docker stack instead of Omi's cloud.
describe('buildListenEndpoint — host from VITE_OMI_API_BASE', () => {
  const CLOUD_CONVERSATION =
    'wss://api.omi.me/v4/listen?language=en&sample_rate=16000&codec=pcm16&channels=1' +
    '&include_speech_profile=true&source=desktop&speaker_auto_assign=enabled'
  const CLOUD_PTT =
    'wss://api.omi.me/v2/voice-message/transcribe-stream?language=en&sample_rate=16000' +
    '&codec=linear16&channels=1'

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('keeps the exact cloud URLs for the stock profile', () => {
    vi.stubEnv('VITE_OMI_API_BASE', 'https://api.omi.me')
    expect(buildListenEndpoint('conversation', 'en')).toBe(CLOUD_CONVERSATION)
    expect(buildListenEndpoint('ptt', 'en')).toBe(CLOUD_PTT)
  })

  it('falls back to the cloud host when the base is unset', () => {
    vi.stubEnv('VITE_OMI_API_BASE', '')
    expect(buildListenEndpoint('conversation', 'en')).toBe(CLOUD_CONVERSATION)
  })

  it('uses plain ws for the local backend', () => {
    vi.stubEnv('VITE_OMI_API_BASE', 'http://127.0.0.1:8000')
    expect(buildListenEndpoint('conversation', 'en')).toBe(
      CLOUD_CONVERSATION.replace('wss://api.omi.me', 'ws://127.0.0.1:8000')
    )
    expect(buildListenEndpoint('transcribe', 'en')).toBe(
      CLOUD_PTT.replace('wss://api.omi.me', 'ws://127.0.0.1:8000')
    )
  })

  it('tolerates a trailing slash on the base', () => {
    vi.stubEnv('VITE_OMI_API_BASE', 'http://127.0.0.1:8000/')
    expect(buildListenEndpoint('conversation', 'en')).toMatch(
      /^ws:\/\/127\.0\.0\.1:8000\/v4\/listen\?/
    )
  })
})

describe('shouldSendKeepalive (silence keepalive — C1 socket starvation)', () => {
  const OPEN = WebSocket.OPEN
  const CONNECTING = WebSocket.CONNECTING

  it('sends when a conversation socket is OPEN and has been idle past the threshold', () => {
    // The regression: without keepalives, a >90s silent stretch let the backend
    // close /v4/listen (1001) and silently killed live transcription.
    expect(shouldSendKeepalive('conversation', OPEN, 30_000)).toBe(true)
    expect(shouldSendKeepalive('conversation', OPEN, 120_000)).toBe(true)
  })

  it('does NOT send before the idle threshold (real audio is flowing)', () => {
    expect(shouldSendKeepalive('conversation', OPEN, 0)).toBe(false)
    expect(shouldSendKeepalive('conversation', OPEN, 29_999)).toBe(false)
  })

  it('does NOT send while still connecting (buffered pre-OPEN, not starving)', () => {
    expect(shouldSendKeepalive('conversation', CONNECTING, 120_000)).toBe(false)
  })

  it('only the long-lived conversation socket keepalives — never ptt/transcribe', () => {
    // PTT/transcribe are short and explicitly finalized; injecting silence frames
    // would corrupt their trailing-segment flush and wall-clock timestamps.
    expect(shouldSendKeepalive('ptt', OPEN, 120_000)).toBe(false)
    expect(shouldSendKeepalive('transcribe', OPEN, 120_000)).toBe(false)
  })
})

describe('isSocketStale (watchdog — half-open socket detection)', () => {
  const OPEN = WebSocket.OPEN
  const CONNECTING = WebSocket.CONNECTING

  it('flags a conversation socket that received nothing (not even a ping) for 60s+', () => {
    // A half-open socket TCP never reset stops delivering the ~10s ping; that
    // staleness is the only signal it is dead, so the watchdog force-reconnects.
    expect(isSocketStale('conversation', OPEN, 60_000)).toBe(true)
    expect(isSocketStale('conversation', OPEN, 200_000)).toBe(true)
  })

  it('does NOT flag a socket still receiving pings (< 60s since last message)', () => {
    expect(isSocketStale('conversation', OPEN, 0)).toBe(false)
    expect(isSocketStale('conversation', OPEN, 59_999)).toBe(false)
  })

  it('only watches OPEN conversation sockets', () => {
    expect(isSocketStale('conversation', CONNECTING, 120_000)).toBe(false)
    expect(isSocketStale('ptt', OPEN, 120_000)).toBe(false)
    expect(isSocketStale('transcribe', OPEN, 120_000)).toBe(false)
  })
})

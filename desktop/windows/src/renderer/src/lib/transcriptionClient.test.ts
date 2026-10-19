import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  auth: { currentUser: null as null | { uid: string } },
  startOmiListen: vi.fn()
}))

vi.mock('./firebase', () => ({ auth: h.auth }))
vi.mock('./omiListenClient', () => ({ startOmiListen: h.startOmiListen }))

import {
  isServerRefusalMessage,
  startTranscription,
  type TranscriptionCallbacks
} from './transcriptionClient'

function callbacks(): TranscriptionCallbacks {
  return {
    onLine: vi.fn(),
    onInterim: vi.fn(),
    onBackend: vi.fn(),
    onError: vi.fn()
  }
}

beforeEach(() => {
  h.auth.currentUser = null
  h.startOmiListen.mockReset()
})

describe('startTranscription startup contract', () => {
  it('rejects instead of returning an empty handle when the user is not signed in', async () => {
    const cb = callbacks()

    await expect(startTranscription('system', cb, 'transcribe')).rejects.toThrow(
      'Omi transcription unavailable (not signed in)'
    )
    expect(cb.onError).toHaveBeenCalledOnce()
    expect(h.startOmiListen).not.toHaveBeenCalled()
  })

  it('rejects when the source or transport fails before readiness', async () => {
    h.auth.currentUser = { uid: 'user-1' }
    const stop = vi.fn()
    h.startOmiListen.mockImplementation(
      async (_source: string, listener: { onError: (error: Error, fatal: boolean) => void }) => {
        const error = new Error('loopback unavailable')
        error.name = 'NotAllowedError'
        setTimeout(() => listener.onError(error, true), 0)
        return { stop, finalize: vi.fn() }
      }
    )
    const cb = callbacks()

    await expect(startTranscription('system', cb, 'transcribe')).rejects.toMatchObject({
      name: 'NotAllowedError',
      message: 'loopback unavailable'
    })
    expect(cb.onError).toHaveBeenCalledOnce()
    expect(stop).toHaveBeenCalledOnce()
  })

  it('aborts and tears down an in-flight startup immediately', async () => {
    h.auth.currentUser = { uid: 'user-1' }
    const stop = vi.fn()
    h.startOmiListen.mockResolvedValue({ stop, finalize: vi.fn() })
    const cb = callbacks()
    const controller = new AbortController()

    const startup = startTranscription('system', cb, 'transcribe', undefined, controller.signal)
    await Promise.resolve()
    controller.abort()

    await expect(startup).rejects.toMatchObject({ name: 'AbortError' })
    expect(stop).toHaveBeenCalledOnce()
    expect(cb.onError).toHaveBeenCalledOnce()
  })
})

type ListenListener = {
  onConnected: () => void
  onClosed: (code: number, reason: string) => void
  onEvent: (event: { type: string; raw: Record<string, unknown> }) => void
}

async function connectedSession(): Promise<{
  cb: TranscriptionCallbacks
  listener: ListenListener
}> {
  h.auth.currentUser = { uid: 'user-1' }
  let listener: ListenListener | null = null
  h.startOmiListen.mockImplementation(async (_source: string, l: ListenListener) => {
    listener = l
    setTimeout(() => l.onConnected(), 0)
    return { stop: vi.fn(), finalize: vi.fn() }
  })
  const cb = callbacks()
  await startTranscription('system', cb, 'transcribe')
  return { cb, listener: listener! }
}

function lastErrorMessage(cb: TranscriptionCallbacks): string {
  const calls = vi.mocked(cb.onError).mock.calls
  return calls[calls.length - 1][0].message
}

describe('server close after connect', () => {
  it('reports a 1008 close as a server refusal without mentioning a subscription', async () => {
    const { cb, listener } = await connectedSession()

    listener.onClosed(1008, '')

    const message = lastErrorMessage(cb)
    expect(message).not.toMatch(/subscription|free quota/i)
    expect(isServerRefusalMessage(message)).toBe(true)
  })

  it('reports a close whose reason names trial_expired as a server refusal', async () => {
    const { cb, listener } = await connectedSession()

    listener.onClosed(4000, 'trial_expired')

    expect(isServerRefusalMessage(lastErrorMessage(cb))).toBe(true)
  })

  it('ends the session on a depleted freemium event without mentioning a quota', async () => {
    const { cb, listener } = await connectedSession()

    listener.onEvent({ type: 'freemium_threshold_reached', raw: { remaining_seconds: 0 } })

    const message = lastErrorMessage(cb)
    expect(message).not.toMatch(/subscription|free quota/i)
    expect(isServerRefusalMessage(message)).toBe(true)
  })

  it('reports a network drop as a plain close, not a refusal', async () => {
    const { cb, listener } = await connectedSession()

    listener.onClosed(1006, '')

    const message = lastErrorMessage(cb)
    expect(message).toBe('Omi transcription stopped: Omi /v4/listen closed (1006)')
    expect(isServerRefusalMessage(message)).toBe(false)
  })
})

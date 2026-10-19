// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { beginClaudeSignIn, __resetClaudeSignIn, CLAUDE_SIGN_IN_FAILED } from './claudeSignIn'
import type { CodingAgentStartAuthResult } from '../../../shared/types'

const codingAgentStartAuth = vi.fn<() => Promise<CodingAgentStartAuthResult>>()

function deferred<T>(): {
  promise: Promise<T>
  resolve: (v: T) => void
  reject: (e: unknown) => void
} {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  codingAgentStartAuth.mockReset()
  ;(globalThis as unknown as { window: { omi: unknown } }).window.omi = { codingAgentStartAuth }
  __resetClaudeSignIn()
})

afterEach(() => __resetClaudeSignIn())

// beginClaudeSignIn is the MID-TURN auth_required entry point. The Settings
// sign-in button calls codingAgentStartAuth directly (see AgentsTab.test).
describe('beginClaudeSignIn (mid-turn auth_required)', () => {
  it('launches the OAuth', () => {
    codingAgentStartAuth.mockReturnValue(deferred<CodingAgentStartAuthResult>().promise)
    beginClaudeSignIn()
    expect(codingAgentStartAuth).toHaveBeenCalledTimes(1)
  })

  it('is idempotent — a second trigger joins the in-flight flow (one browser launch)', () => {
    codingAgentStartAuth.mockReturnValue(deferred<CodingAgentStartAuthResult>().promise)
    beginClaudeSignIn()
    beginClaudeSignIn()
    expect(codingAgentStartAuth).toHaveBeenCalledTimes(1)
  })

  it('reports the result when the OAuth completes', async () => {
    const d = deferred<CodingAgentStartAuthResult>()
    codingAgentStartAuth.mockReturnValue(d.promise)
    const onResult = vi.fn()
    beginClaudeSignIn(onResult)

    d.resolve({ ok: true, status: { connected: true, expiresAt: 123 } })
    await d.promise

    expect(onResult).toHaveBeenCalledWith({ ok: true, status: { connected: true, expiresAt: 123 } })
  })

  it('fail-closed: reports the error when the flow fails', async () => {
    const d = deferred<CodingAgentStartAuthResult>()
    codingAgentStartAuth.mockReturnValue(d.promise)
    const onResult = vi.fn()
    beginClaudeSignIn(onResult)

    const failure: CodingAgentStartAuthResult = {
      ok: false,
      error: 'Could not start Claude sign-in (invalid authorization URL).',
      status: { connected: false, expiresAt: null }
    }
    d.resolve(failure)
    await d.promise

    expect(onResult).toHaveBeenCalledWith(failure)
  })

  it('reports a generic failure when the IPC itself rejects', async () => {
    codingAgentStartAuth.mockRejectedValue(new Error('ipc down'))
    const onResult = vi.fn()
    beginClaudeSignIn(onResult)
    // Let the rejection microtask settle.
    await Promise.resolve()
    await Promise.resolve()
    expect(onResult).toHaveBeenCalledWith(
      expect.objectContaining({ ok: false, error: CLAUDE_SIGN_IN_FAILED })
    )
  })

  it('launches a new flow once the previous one has finished', async () => {
    const d = deferred<CodingAgentStartAuthResult>()
    codingAgentStartAuth.mockReturnValueOnce(d.promise)
    beginClaudeSignIn()
    d.resolve({ ok: false, error: 'timeout', status: { connected: false, expiresAt: null } })
    // Let the then/catch/finally chain release the in-flight flag.
    await new Promise((r) => setTimeout(r, 0))

    codingAgentStartAuth.mockReturnValueOnce(deferred<CodingAgentStartAuthResult>().promise)
    beginClaudeSignIn()
    expect(codingAgentStartAuth).toHaveBeenCalledTimes(2)
  })
})

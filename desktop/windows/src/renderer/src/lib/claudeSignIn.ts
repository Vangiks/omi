// Mid-turn Claude Code sign-in. When the coding-agent bridge emits
// `auth_required` during a chat turn (Claude Code's token was rejected),
// useChat calls beginClaudeSignIn(), which launches the real Claude OAuth in the
// browser: main's codingAgentStartAuth builds + validates the
// claude.com/cai/oauth/authorize URL, opens it, and awaits the loopback callback.
//
// The Settings → Agents "Sign in to Claude" button calls
// window.omi.codingAgentStartAuth() directly and does not come through here.
//
// Fail-closed: if the flow fails (main rejects an invalid authorize URL, or the
// callback times out), the caller gets a generic "Unable to start Claude
// sign-in. Try again." error (mirrors macOS ChatProvider.startClaudeAuth).

import type { CodingAgentStartAuthResult } from '../../../shared/types'

/** Shown when the sign-in flow can't start or complete (macOS parity copy). */
export const CLAUDE_SIGN_IN_FAILED = 'Unable to start Claude sign-in. Try again.'

// True once a flow is launched, until it resolves — a second auth_required
// event joins the in-flight flow instead of launching a second browser tab.
let inFlight = false

/**
 * Launch the Claude OAuth for a mid-turn `auth_required` event. `onResult`
 * fires once the flow resolves; a call that joins an in-flight flow gets none.
 */
export function beginClaudeSignIn(onResult?: (result: CodingAgentStartAuthResult) => void): void {
  if (inFlight) return
  inFlight = true
  void window.omi
    .codingAgentStartAuth()
    .then((result) => onResult?.(result))
    .catch(() => {
      onResult?.({
        ok: false,
        error: CLAUDE_SIGN_IN_FAILED,
        status: { connected: false, expiresAt: null }
      })
    })
    .finally(() => {
      inFlight = false
    })
}

/** Test-only: reset module state between cases. */
export function __resetClaudeSignIn(): void {
  inFlight = false
}

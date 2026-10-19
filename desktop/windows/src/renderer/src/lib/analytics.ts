// Mirrors the macOS desktop app's PostHogManager: best-effort analytics sent to
// the same PostHog project via its HTTP ingestion API (no SDK needed). The project
// key comes only from VITE_POSTHOG_KEY (.env.example carries Omi's publishable
// key); without it analytics is off and nothing leaves the machine, which is what
// the local-backend profile relies on. Every call is fire-and-forget and never
// blocks or surfaces errors.
import { auth } from './firebase'

// Host is intentionally fixed to the CSP connect-src allowlist in renderer HTML.
// A VITE_POSTHOG_HOST override would silently fail under Chromium if it diverged.
const POSTHOG_HOST = 'https://us.i.posthog.com'
export function trackEvent(event: string, properties: Record<string, unknown> = {}): void {
  const key = ((import.meta.env.VITE_POSTHOG_KEY as string | undefined) ?? '').trim()
  if (!key) return
  const distinctId = auth.currentUser?.uid ?? 'anonymous'
  void fetch(`${POSTHOG_HOST}/i/v0/e/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      api_key: key,
      event,
      distinct_id: distinctId,
      properties: {
        ...properties,
        $lib: 'omi-windows',
        $os: 'Windows',
        platform: 'windows'
      }
    })
  }).catch(() => {
    // Analytics is best-effort — swallow network/auth failures silently.
  })
}

// Same event name + property shape the desktop app's AnalyticsManager sends.
export function trackHowDidYouHear(source: string): void {
  trackEvent('Onboarding How Did You Hear', { source, is_referral: source === 'Friend' })
}

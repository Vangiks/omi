/** Public share-link base URL for self-hosting (#4339). Matches backend OMI_SHARE_BASE_URL. */

const DEFAULT_SHARE_BASE = 'https://h.omi.me'

export function shareBaseUrl(
  raw: string | undefined = import.meta.env.VITE_OMI_SHARE_BASE_URL as string | undefined
): string {
  let value = (raw ?? '').trim()
  if (!value) value = DEFAULT_SHARE_BASE
  if (!value.includes('://')) value = `https://${value}`
  try {
    const parsed = new URL(value)
    if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname)
      return DEFAULT_SHARE_BASE
  } catch {
    return DEFAULT_SHARE_BASE
  }
  return value.replace(/\/+$/, '')
}

/** False in the local-backend profile (Auth emulator) unless a share host is set
 *  explicitly: the default h.omi.me would publish a link to Omi's web viewer for
 *  a conversation that lives only on this machine. */
export function shareLinksAvailable(
  env: { VITE_FIREBASE_AUTH_EMULATOR_HOST?: string; VITE_OMI_SHARE_BASE_URL?: string } = {
    VITE_FIREBASE_AUTH_EMULATOR_HOST: import.meta.env.VITE_FIREBASE_AUTH_EMULATOR_HOST,
    VITE_OMI_SHARE_BASE_URL: import.meta.env.VITE_OMI_SHARE_BASE_URL
  }
): boolean {
  if (!env.VITE_FIREBASE_AUTH_EMULATOR_HOST?.trim()) return true
  return Boolean(env.VITE_OMI_SHARE_BASE_URL?.trim())
}

export function conversationShareUrl(
  id: string,
  raw?: string | undefined,
  sid: string = newShareId()
): string {
  const url = new URL(`${shareBaseUrl(raw)}/conversations/${id}`)
  url.searchParams.set('sid', sid)
  // The same Electron code also ships on Linux; avoid claiming those shares came from Windows.
  if (typeof navigator === 'undefined' || !/linux/i.test(navigator.userAgent)) {
    url.searchParams.set('s', 'win')
  }
  return url.toString()
}

/** Ephemeral link ID, independent of the sender and conversation. */
export function newShareId(): string {
  return crypto.randomUUID().replaceAll('-', '')
}

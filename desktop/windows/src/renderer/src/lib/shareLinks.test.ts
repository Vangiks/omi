import { describe, expect, it } from 'vitest'
import { conversationShareUrl, shareBaseUrl, shareLinksAvailable } from './shareLinks'

describe('shareLinks (#4339)', () => {
  it('defaults to production h.omi.me', () => {
    expect(shareBaseUrl('')).toBe('https://h.omi.me')
    expect(shareBaseUrl(undefined)).toBe('https://h.omi.me')
    expect(conversationShareUrl('abc', '', 'sid12345')).toBe(
      'https://h.omi.me/conversations/abc?sid=sid12345&s=win'
    )
  })

  it('honors VITE_OMI_SHARE_BASE_URL overrides', () => {
    expect(shareBaseUrl('https://share.example.com/')).toBe('https://share.example.com')
    expect(shareBaseUrl('share.example.com')).toBe('https://share.example.com')
    expect(conversationShareUrl('abc', 'https://share.example.com', 'sid12345')).toBe(
      'https://share.example.com/conversations/abc?sid=sid12345&s=win'
    )
  })

  it('falls back for malformed or unsupported overrides', () => {
    expect(shareBaseUrl('ftp://share.example.com')).toBe('https://h.omi.me')
    expect(shareBaseUrl('not a url')).toBe('https://h.omi.me')
  })

  it('mints a random share id per link', () => {
    const first = new URL(conversationShareUrl('abc')).searchParams.get('sid')
    const second = new URL(conversationShareUrl('abc')).searchParams.get('sid')
    expect(first).toMatch(/^[0-9a-f]{32}$/)
    expect(first).not.toBe(second)
  })
})

// Local-backend profile (Auth emulator): there is no public share host, so links
// would point at Omi's h.omi.me for a conversation that lives only on this machine.
describe('shareLinksAvailable', () => {
  it('is on for the stock profile', () => {
    expect(shareLinksAvailable({})).toBe(true)
  })

  it('is off for the local-backend profile without an explicit share host', () => {
    expect(shareLinksAvailable({ VITE_FIREBASE_AUTH_EMULATOR_HOST: '127.0.0.1:9099' })).toBe(false)
  })

  it('is on for the local-backend profile with an explicit share host', () => {
    expect(
      shareLinksAvailable({
        VITE_FIREBASE_AUTH_EMULATOR_HOST: '127.0.0.1:9099',
        VITE_OMI_SHARE_BASE_URL: 'https://share.example.com'
      })
    ).toBe(true)
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'

const handlers = vi.hoisted(() => new Map<string, (...args: unknown[]) => unknown>())
const openExternal = vi.hoisted(() => vi.fn())
vi.mock('electron', () => ({
  ipcMain: {
    handle: (channel: string, fn: (...args: unknown[]) => unknown) => handlers.set(channel, fn)
  },
  shell: { openExternal }
}))

import { isAllowedExternalScheme, registerExternalUrlIpc } from './externalUrl'

describe('isAllowedExternalScheme', () => {
  it('allows a scheme in the allow-list', () => {
    expect(isAllowedExternalScheme('https://omi.me', ['http', 'https'])).toBe(true)
    expect(isAllowedExternalScheme('http://omi.me', ['http', 'https'])).toBe(true)
    expect(isAllowedExternalScheme('mailto:hi@omi.me', ['http', 'https', 'mailto'])).toBe(true)
  })

  it('blocks a scheme not in the allow-list', () => {
    expect(isAllowedExternalScheme('mailto:hi@omi.me', ['http', 'https'])).toBe(false)
    expect(isAllowedExternalScheme('file:///etc/passwd', ['http', 'https'])).toBe(false)
    // UNC / custom-protocol handler abuse vectors.
    expect(isAllowedExternalScheme('\\\\evil\\share', ['http', 'https'])).toBe(false)
    expect(isAllowedExternalScheme('omi-agent://run', ['http', 'https'])).toBe(false)
  })

  it('blocks an unparseable URL', () => {
    expect(isAllowedExternalScheme('not a url', ['http', 'https'])).toBe(false)
    expect(isAllowedExternalScheme('', ['http', 'https'])).toBe(false)
  })
})

describe('shell:openExternal', () => {
  beforeEach(() => {
    handlers.clear()
    openExternal.mockReset().mockResolvedValue(undefined)
    registerExternalUrlIpc()
  })

  const invoke = (url: unknown): unknown => handlers.get('shell:openExternal')!({}, url)

  it('opens a web URL in the system browser', () => {
    expect(invoke('https://calendar.google.com/x')).toBe(true)
    expect(openExternal).toHaveBeenCalledWith('https://calendar.google.com/x')
  })

  it('refuses a non-web URL from the renderer', () => {
    for (const url of [
      'file:///etc/passwd',
      'mailto:hi@omi.me',
      'omi-agent://run',
      'javascript:alert(1)',
      42
    ]) {
      expect(invoke(url)).toBe(false)
    }
    expect(openExternal).not.toHaveBeenCalled()
  })
})

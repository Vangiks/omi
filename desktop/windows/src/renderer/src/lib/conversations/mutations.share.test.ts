import { afterEach, describe, expect, it, vi } from 'vitest'

const patch = vi.hoisted(() => vi.fn())
vi.mock('../apiClient', () => ({ omiApi: { patch } }))
vi.mock('../analytics', () => ({ trackEvent: vi.fn() }))

import { getConversationShareLink } from './mutations'

afterEach(() => {
  vi.unstubAllEnvs()
  patch.mockReset()
})

describe('getConversationShareLink', () => {
  it('refuses in the local-backend profile before making the conversation public', async () => {
    vi.stubEnv('VITE_FIREBASE_AUTH_EMULATOR_HOST', '127.0.0.1:9099')
    vi.stubEnv('VITE_OMI_SHARE_BASE_URL', '')

    await expect(getConversationShareLink('conv-1')).rejects.toThrow(/share/i)
    expect(patch).not.toHaveBeenCalled()
  })

  it('shares as before in the stock profile', async () => {
    vi.stubEnv('VITE_FIREBASE_AUTH_EMULATOR_HOST', '')
    vi.stubEnv('VITE_OMI_SHARE_BASE_URL', '')
    patch.mockResolvedValue(undefined)

    const url = await getConversationShareLink('conv-1')

    expect(patch).toHaveBeenCalledWith('/v1/conversations/conv-1/visibility', null, {
      params: { value: 'shared' }
    })
    expect(url).toMatch(/^https:\/\/h\.omi\.me\/conversations\/conv-1\?sid=/)
  })
})

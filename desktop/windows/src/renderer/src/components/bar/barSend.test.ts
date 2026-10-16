// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { sendFromBar } from './barSend'

// The bar's send path (typed submit AND PTT commit). The fork has no chat quota
// (#3): a send goes straight to the main window's chat engine, and the bar never
// asks the backend for /v1/users/me/usage-quota.

const { fetchChatQuota } = vi.hoisted(() => ({
  fetchChatQuota: vi.fn(async () => ({ allowed: false, limit: 30, used: 30 }))
}))
vi.mock('../../lib/billing', () => ({ fetchChatQuota }))

const sendChat = vi.fn()
const notifyAsked = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  ;(window as unknown as { omiBar: unknown }).omiBar = { sendChat }
  ;(window as unknown as { omiOverlay: unknown }).omiOverlay = { notifyAsked }
})

describe('bar send', () => {
  it('sends a typed message without checking the chat quota', () => {
    sendFromBar('are you there', false)

    expect(sendChat).toHaveBeenCalledWith('are you there', false)
    expect(notifyAsked).toHaveBeenCalledTimes(1)
    expect(fetchChatQuota).not.toHaveBeenCalled()
  })

  it('sends a PTT (voice) turn as a voice message', () => {
    sendFromBar('what is on my calendar', true)

    expect(sendChat).toHaveBeenCalledWith('what is on my calendar', true)
  })

  it('ignores an empty send', () => {
    sendFromBar('   ', false)

    expect(sendChat).not.toHaveBeenCalled()
    expect(notifyAsked).not.toHaveBeenCalled()
  })
})

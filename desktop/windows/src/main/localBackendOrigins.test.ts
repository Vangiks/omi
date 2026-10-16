import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  addCspConnectSources,
  localBackendCorsUrls,
  localBackendCspSources
} from './localBackendOrigins'

const cloud = {
  VITE_OMI_API_BASE: 'https://api.omi.me',
  VITE_OMI_DESKTOP_API_BASE: 'https://desktop-backend-hhibjajaja-uc.a.run.app'
}

const local = {
  VITE_OMI_API_BASE: 'http://127.0.0.1:8000',
  VITE_OMI_DESKTOP_API_BASE: 'http://127.0.0.1:10201',
  VITE_FIREBASE_AUTH_EMULATOR_HOST: '127.0.0.1:9099'
}

const htmlEntries = ['index', 'capture', 'glow', 'insight-toast'].map((name) =>
  resolve(__dirname, '../renderer', `${name}.html`)
)

describe('localBackendCspSources', () => {
  it('adds nothing for the cloud profile', () => {
    expect(localBackendCspSources(cloud)).toEqual([])
    expect(localBackendCspSources({})).toEqual([])
  })

  it('allows http and ws for the API, http for desktop-backend and the Auth emulator', () => {
    expect(localBackendCspSources(local)).toEqual([
      'http://127.0.0.1:8000',
      'ws://127.0.0.1:8000',
      'http://127.0.0.1:10201',
      'http://127.0.0.1:9099'
    ])
  })

  it('ignores values that are not URLs', () => {
    expect(
      localBackendCspSources({
        VITE_OMI_API_BASE: 'not a url',
        VITE_FIREBASE_AUTH_EMULATOR_HOST: ''
      })
    ).toEqual([])
  })
})

describe('localBackendCorsUrls', () => {
  it('adds nothing for the cloud profile', () => {
    expect(localBackendCorsUrls(cloud)).toEqual([])
  })

  it('covers both local backends', () => {
    expect(localBackendCorsUrls(local)).toEqual([
      'http://127.0.0.1:8000/*',
      'http://127.0.0.1:10201/*'
    ])
  })
})

describe('addCspConnectSources', () => {
  it.each(htmlEntries)('leaves %s unchanged without extra sources', (file) => {
    const html = readFileSync(file, 'utf8')
    expect(addCspConnectSources(html, [])).toBe(html)
  })

  it.each(htmlEntries)('adds the local sources to connect-src in %s', (file) => {
    const html = readFileSync(file, 'utf8')
    const out = addCspConnectSources(html, localBackendCspSources(local))
    const connectSrc = out.match(/connect-src([^;]*);/)?.[1] ?? ''
    expect(connectSrc).toContain("'self'")
    expect(connectSrc).toContain('ws://127.0.0.1:8000')
    expect(connectSrc).toContain('http://127.0.0.1:9099')
    expect(connectSrc).toContain('https://api.omi.me')
  })

  it('fails loudly when an entry has no connect-src to extend', () => {
    expect(() => addCspConnectSources('<html></html>', ['http://127.0.0.1:8000'])).toThrow()
  })
})

import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ensureLocalProfile, localDevEnv } from './dev-local.mjs'

describe('localDevEnv', () => {
  it('isolates the userData profile by default', () => {
    expect(localDevEnv({ PATH: '/bin' })).toEqual({ PATH: '/bin', OMI_SANDBOX: 'local' })
  })

  it('keeps an explicit OMI_SANDBOX', () => {
    expect(localDevEnv({ OMI_SANDBOX: 'other' }).OMI_SANDBOX).toBe('other')
  })
})

describe('ensureLocalProfile', () => {
  const dir = () => {
    const d = mkdtempSync(join(tmpdir(), 'omi-dev-local-'))
    writeFileSync(
      join(d, '.env.local-backend.example'),
      'VITE_OMI_API_BASE=http://127.0.0.1:8000\n'
    )
    return d
  }

  it('creates the profile from the example when missing', () => {
    const d = dir()
    expect(ensureLocalProfile(d)).toBe(true)
    expect(readFileSync(join(d, '.env.local-backend'), 'utf8')).toContain('127.0.0.1:8000')
  })

  it('never overwrites an existing profile', () => {
    const d = dir()
    writeFileSync(join(d, '.env.local-backend'), 'MINE=1\n')
    expect(ensureLocalProfile(d)).toBe(false)
    expect(readFileSync(join(d, '.env.local-backend'), 'utf8')).toBe('MINE=1\n')
    expect(existsSync(join(d, '.env.local-backend'))).toBe(true)
  })
})

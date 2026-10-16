import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Local-backend profile: with VITE_FIREBASE_AUTH_EMULATOR_HOST set, auth talks
// to the emulator and sign-in goes through the backend's local-dev custom token.
// Without it nothing changes: no emulator, no local sign-in.

const fb = vi.hoisted(() => ({
  connectAuthEmulator: vi.fn(),
  signInWithCustomToken: vi.fn()
}))

vi.mock('firebase/auth', () => ({
  initializeAuth: vi.fn(() => ({ name: 'auth' })),
  getAuth: vi.fn(() => ({ name: 'auth' })),
  connectAuthEmulator: fb.connectAuthEmulator,
  signInWithCustomToken: fb.signInWithCustomToken,
  signOut: vi.fn(),
  updateProfile: vi.fn(),
  onAuthStateChanged: vi.fn(),
  browserLocalPersistence: {}
}))

async function loadFirebase(): Promise<typeof import('./firebase')> {
  vi.resetModules()
  return import('./firebase')
}

beforeEach(() => {
  fb.connectAuthEmulator.mockReset()
  fb.signInWithCustomToken.mockReset().mockResolvedValue({ user: { uid: 'local-dev-user' } })
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('without the Auth emulator', () => {
  it('does not connect to an emulator or offer local sign-in', async () => {
    vi.stubEnv('VITE_FIREBASE_AUTH_EMULATOR_HOST', '')
    const mod = await loadFirebase()

    expect(fb.connectAuthEmulator).not.toHaveBeenCalled()
    expect(mod.isLocalSignInAvailable()).toBe(false)
    await expect(mod.signInLocally()).rejects.toThrow()
  })
})

describe('with the Auth emulator', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_FIREBASE_AUTH_EMULATOR_HOST', '127.0.0.1:9099')
    vi.stubEnv('VITE_OMI_API_BASE', 'http://127.0.0.1:8000')
  })

  it('connects auth to the emulator at import', async () => {
    const mod = await loadFirebase()

    expect(fb.connectAuthEmulator).toHaveBeenCalledWith(mod.auth, 'http://127.0.0.1:9099', {
      disableWarnings: true
    })
    expect(mod.isLocalSignInAvailable()).toBe(true)
  })

  it('signs in with the custom token the local backend mints', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ custom_token: 'tok-1', uid: 'local-dev-user' }), {
        status: 200
      })
    )
    vi.stubGlobal('fetch', fetchMock)
    const mod = await loadFirebase()

    const user = await mod.signInLocally()

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://127.0.0.1:8000/v1/auth/local-dev/custom-token')
    expect(init.method).toBe('POST')
    expect((init.body as FormData).get('uid')).toBe('local-dev-user')
    expect(fb.signInWithCustomToken).toHaveBeenCalledWith(mod.auth, 'tok-1')
    expect(user.uid).toBe('local-dev-user')
  })

  it('reports a backend failure instead of signing in', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('nope', { status: 404 })))
    const mod = await loadFirebase()

    await expect(mod.signInLocally()).rejects.toThrow(/404/)
    expect(fb.signInWithCustomToken).not.toHaveBeenCalled()
  })
})

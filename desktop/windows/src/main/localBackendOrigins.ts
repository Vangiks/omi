// Network access for the local-backend profile (`pnpm dev --mode local-backend`,
// see .env.local-backend.example and deploy/local/README.md at the repo root).
//
// The renderer CSP and the main-process CORS shim list the cloud hosts
// statically. A profile that points the backends at plain-http addresses (the
// Docker stack on 127.0.0.1) needs those origins added too. Only http bases are
// added: https bases are the cloud ones, already listed. With the stock
// profiles every function here returns an empty list, so the HTML and the CORS
// list stay exactly as they were.
//
// Pure and electron-free: electron.vite.config.ts imports it at build time to
// rewrite the HTML entries, src/main/index.ts at runtime for CORS.

export interface LocalBackendEnv {
  VITE_OMI_API_BASE?: string
  VITE_OMI_DESKTOP_API_BASE?: string
  /** `host:port` of the Firebase Auth emulator, the form connectAuthEmulator takes. */
  VITE_FIREBASE_AUTH_EMULATOR_HOST?: string
}

function httpOrigin(value: string | undefined): string | null {
  if (!value) return null
  try {
    const url = new URL(value)
    return url.protocol === 'http:' ? url.origin : null
  } catch {
    return null
  }
}

/** Extra `connect-src` sources: http and ws for the API (listen is a WebSocket),
 *  http for desktop-backend and the Auth emulator. */
export function localBackendCspSources(env: LocalBackendEnv): string[] {
  const sources: string[] = []
  const api = httpOrigin(env.VITE_OMI_API_BASE)
  if (api) sources.push(api, api.replace(/^http:/, 'ws:'))
  const desktop = httpOrigin(env.VITE_OMI_DESKTOP_API_BASE)
  if (desktop) sources.push(desktop)
  const emulator = env.VITE_FIREBASE_AUTH_EMULATOR_HOST
    ? httpOrigin(`http://${env.VITE_FIREBASE_AUTH_EMULATOR_HOST}`)
    : null
  if (emulator) sources.push(emulator)
  return [...new Set(sources)]
}

/** Extra webRequest URL patterns for the CORS shim in src/main/index.ts. */
export function localBackendCorsUrls(env: LocalBackendEnv): string[] {
  const origins = [httpOrigin(env.VITE_OMI_API_BASE), httpOrigin(env.VITE_OMI_DESKTOP_API_BASE)]
  return [...new Set(origins.filter((o): o is string => o !== null))].map((o) => `${o}/*`)
}

/** Appends `sources` to the CSP `connect-src` directive of an HTML entry. */
export function addCspConnectSources(html: string, sources: string[]): string {
  if (sources.length === 0) return html
  const marker = "connect-src 'self'"
  if (!html.includes(marker)) {
    throw new Error(`local-backend profile: no "${marker}" in an HTML entry to extend`)
  }
  return html.replace(marker, `${marker} ${sources.join(' ')}`)
}

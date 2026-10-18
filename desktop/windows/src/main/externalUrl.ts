import { ipcMain, shell } from 'electron'

// Shared scheme allow-list guard for handing a URL to the OS. A prompt-injected
// chat reply or a malformed link could otherwise carry a file://, UNC, or
// custom-protocol URL; passing those to shell.openExternal enables NTLM-hash
// leak / protocol-handler abuse. The main window's window-open handler
// (http/https/mailto) and the renderer's `shell:openExternal` channel
// (http/https) both route through this one parser instead of hand-rolling their own.

/** True iff `url` parses and its scheme is one of `allowed` (bare, no trailing colon). */
export function isAllowedExternalScheme(url: string, allowed: string[]): boolean {
  try {
    const scheme = new URL(url).protocol // e.g. "https:"
    return allowed.some((a) => scheme === `${a}:`)
  } catch {
    return false
  }
}

/**
 * Register `shell:openExternal`: the renderer hands a web link (calendar OAuth,
 * onboarding sources, app setup pages) to the system browser. The URL is
 * renderer-supplied, so only http/https get through. Call once during main setup.
 */
export function registerExternalUrlIpc(): void {
  ipcMain.handle('shell:openExternal', (_e, url: unknown) => {
    const target = String(url)
    if (isAllowedExternalScheme(target, ['http', 'https'])) {
      void shell.openExternal(target)
      return true
    }
    console.warn('[main] shell: blocked external open of non-web URL')
    return false
  })
}

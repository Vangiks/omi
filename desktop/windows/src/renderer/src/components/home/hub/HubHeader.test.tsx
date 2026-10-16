// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, cleanup, fireEvent, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

// The Hub gear goes straight to Settings. It used to open a dropdown with the
// upstream "Refer a Friend" and Discord links in front of Settings; the fork has
// no use for those, and a menu with one item is just an extra click (issue #5).

vi.mock('../../../lib/preferences', () => ({
  getPreferences: () => ({}),
  onPreferencesChange: () => () => {},
  setPreferences: () => {}
}))

import { HubHeader } from './HubHeader'

beforeEach(() => {
  ;(window as unknown as { omi: unknown }).omi = {
    rewindGetSettings: vi.fn(() => new Promise(() => {})),
    onRewindSettings: vi.fn(() => () => {}),
    openExternalUrl: vi.fn()
  }
})

afterEach(cleanup)

function Probe(): React.JSX.Element {
  return <div data-testid="path">{useLocation().pathname}</div>
}

function renderHeader(): void {
  render(
    <MemoryRouter initialEntries={['/home']}>
      <Probe />
      <Routes>
        <Route path="/home" element={<HubHeader />} />
        <Route path="/settings" element={null} />
      </Routes>
    </MemoryRouter>
  )
}

describe('HubHeader gear', () => {
  it('opens Settings on a single click, with no menu', () => {
    renderHeader()
    fireEvent.click(screen.getByRole('button', { name: 'Settings' }))
    expect(screen.getByTestId('path').textContent).toBe('/settings')
    expect(screen.queryByRole('menu')).toBeNull()
  })
})

// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'

const { signInWithProvider, signInLocally, isLocalSignInAvailable } = vi.hoisted(() => ({
  signInWithProvider: vi.fn(),
  signInLocally: vi.fn(),
  isLocalSignInAvailable: vi.fn()
}))

vi.mock('../lib/firebase', () => ({ signInWithProvider, signInLocally, isLocalSignInAvailable }))

import { Login } from './Login'

beforeEach(() => {
  signInWithProvider.mockReset().mockResolvedValue({ uid: 'test-user' })
  signInLocally.mockReset().mockResolvedValue({ uid: 'local-dev-user' })
  isLocalSignInAvailable.mockReset().mockReturnValue(false)
})

afterEach(() => {
  cleanup()
})

describe('Login page', () => {
  it('offers Apple before Google using the system-browser sign-in labels', () => {
    render(<Login />)

    const buttons = screen.getAllByRole('button')
    expect(buttons[0].textContent).toContain('Continue with Apple')
    expect(buttons[1].textContent).toContain('Continue with Google')
  })

  it('starts Apple sign-in through the shared provider bridge', async () => {
    render(<Login />)

    fireEvent.click(screen.getByRole('button', { name: 'Continue with Apple' }))

    await waitFor(() => expect(signInWithProvider).toHaveBeenCalledWith('apple'))
  })

  it('shows no local sign-in without the Auth emulator', () => {
    render(<Login />)

    expect(screen.queryByRole('button', { name: 'Sign in locally' })).toBeNull()
    expect(screen.getAllByRole('button')).toHaveLength(2)
  })

  it('signs in locally when the Auth emulator is configured', async () => {
    isLocalSignInAvailable.mockReturnValue(true)
    render(<Login />)

    fireEvent.click(screen.getByRole('button', { name: 'Sign in locally' }))

    await waitFor(() => expect(signInLocally).toHaveBeenCalledTimes(1))
    expect(signInWithProvider).not.toHaveBeenCalled()
  })

  it('shows the local sign-in error', async () => {
    isLocalSignInAvailable.mockReturnValue(true)
    signInLocally.mockRejectedValue(new Error('local backend answered 404'))
    render(<Login />)

    fireEvent.click(screen.getByRole('button', { name: 'Sign in locally' }))

    expect(await screen.findByText('local backend answered 404')).toBeTruthy()
  })
})

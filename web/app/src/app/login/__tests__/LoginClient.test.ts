import { createElement, type ReactNode } from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

let query = '';
let authUser: { uid: string } | null = null;
const routerHarness = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({ push: routerHarness.push }),
  useSearchParams: () => new URLSearchParams(query),
}));

vi.mock('@tschk/moonshine-next/image', () => ({
  default: (props: Record<string, unknown>) =>
    createElement('img', { src: props.src, alt: props.alt }),
}));

vi.mock('@tschk/moonshine-next/link', () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) =>
    createElement('a', { href }, children),
}));

vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({
    user: authUser,
    loading: false,
    signInWithApple: vi.fn(),
    signInWithGoogle: vi.fn(),
  }),
}));

vi.mock('@/lib/firebase', () => ({
  isFirebaseAuthConfigured: false,
}));

vi.mock('@/lib/analytics/posthog', () => ({
  PostHogManager: { pageView: vi.fn(), track: vi.fn() },
}));

import { LoginClient } from '@/app/login/LoginClient';

describe('LoginClient geometry', () => {
  beforeEach(() => {
    query = '';
    authUser = null;
  });

  afterEach(cleanup);

  it('renders fixed auth actions, an out-of-flow status lane, and desktop mark clearance', () => {
    const markup = renderToStaticMarkup(createElement(LoginClient));

    expect(markup.match(/\bh-12\b/g)).toHaveLength(2);
    expect(markup).toContain('role="status"');
    expect(markup).toContain('absolute inset-x-0 top-full mt-3 h-[72px] w-full');
    expect(markup).toContain(
      'aria-hidden="true" class="mb-16 hidden h-16 w-16 sm:block"',
    );
    expect(markup).not.toContain('min-h-[52px]');
  });
});

describe('LoginClient return path', () => {
  beforeEach(() => {
    routerHarness.push.mockReset();
    authUser = { uid: 'user-1' };
  });

  afterEach(() => {
    cleanup();
    authUser = null;
    query = '';
  });

  it('returns a signed-in reader to the page an item link asked for', async () => {
    query = 'next=%2Fconversations%3Fid%3Dabc';
    render(createElement(LoginClient));
    await waitFor(() =>
      expect(routerHarness.push).toHaveBeenCalledWith('/conversations?id=abc'),
    );
  });

  it('ignores a next that would leave the app', async () => {
    query = 'next=%2F%2Fevil.example';
    render(createElement(LoginClient));
    await waitFor(() => expect(routerHarness.push).toHaveBeenCalledWith('/home'));
  });

  it('ignores a next that normalizes into a protocol-relative URL', async () => {
    query = 'next=%2F.%2F%2Fevil.example';
    render(createElement(LoginClient));
    await waitFor(() => expect(routerHarness.push).toHaveBeenCalledWith('/home'));
  });

  it('signs in through an old referral link like any other login', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    query = 'referral=ref1.test.code&environment=prod';

    const view = render(createElement(LoginClient));

    await waitFor(() => expect(routerHarness.push).toHaveBeenCalledWith('/home'));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(view.queryByText('Referral unavailable')).toBeNull();
    vi.unstubAllGlobals();
  });
});

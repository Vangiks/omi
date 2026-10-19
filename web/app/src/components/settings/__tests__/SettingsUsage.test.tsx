import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams('section=account'),
}));
vi.mock('@tschk/moonshine-next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock('@tschk/moonshine-next/image', () => ({
  default: (props: Record<string, unknown>) => <img {...props} alt="" />,
}));
vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => ({
    user: { uid: 'user-1', email: 'user@example.com', displayName: 'User' },
    signOut: vi.fn(),
  }),
}));
// Only the calls the account section is meant to make; a call to anything
// else (a plan or billing endpoint) fails the section load.
vi.mock('@/lib/api', () => ({
  getUserLanguage: vi.fn(async () => 'en'),
  getCustomVocabulary: vi.fn(async () => []),
  getDailySummarySettings: vi.fn(async () => null),
  getAllUsageData: vi.fn(async () => ({
    today: null,
    monthly: null,
    yearly: null,
    all_time: {
      transcription_seconds: 7260,
      words_transcribed: 12500,
      insights_gained: 3,
      memories_created: 4,
    },
  })),
}));

import { SettingsPage } from '@/components/settings/SettingsPage';

describe('Settings > Account > Usage', () => {
  it('shows usage stats without a plan or billing', async () => {
    render(<SettingsPage />);

    expect(await screen.findByText('2h 1m')).toBeTruthy();
    expect(screen.getByText('12.5k')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Plan' })).toBeNull();
    expect(screen.queryByText(/See plans|Billing|Subscription/)).toBeNull();
    expect(screen.queryByRole('link', { name: /Plan & Usage/ })).toBeNull();
  });
});

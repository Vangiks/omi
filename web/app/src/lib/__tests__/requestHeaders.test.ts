import { afterEach, describe, expect, it, vi } from 'vitest';
import { version as webAppVersion } from '../../../package.json';

vi.mock('@/lib/firebase', () => ({
  getIdToken: vi.fn(async () => 'test-token'),
}));

vi.mock('@/lib/clientDevice', () => ({
  getWebDeviceIdHash: vi.fn(async () => 'test-device'),
}));

import { getUserLanguage } from '@/lib/api';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('fetchWithAuth request headers', () => {
  it('identifies the web client and sends no plan identity', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ language: 'en' }), {
            headers: { 'content-type': 'application/json' },
          }),
      ),
    );

    await getUserLanguage();

    const headers = new Headers(vi.mocked(fetch).mock.calls[0][1]?.headers);
    expect(headers.get('X-App-Platform')).toBe('web');
    expect(headers.get('X-App-Version')).toBe(webAppVersion);
    expect(headers.get('X-Device-Id-Hash')).toBe('test-device');
    expect(headers.has('X-Omi-Plan-Identity')).toBe(false);
  });
});

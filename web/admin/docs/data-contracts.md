# Web Admin Data Contracts

Detail for the two rules in `web/admin/AGENTS.md`.

## Networking

All fetches use `hooks/useAuthToken.ts`; never call `getIdToken()`, create auth headers, or read Firestore in the client.

- Reads: `useAuthToken()` + `authenticatedFetcher`; mutations: `useAuthFetch()` → `fetchWithAuth(url, init)`.
- Server routes call `verifyAdmin(request)` from `lib/auth.ts`.
- Parallel fetches use `Promise.allSettled`, returning `partial: true` on partial failure and 502 on total failure.
- SWR configuration belongs in `components/swr-provider.tsx`; keys are `token ? [url, token] : null`.
- Partial data shows an amber warning. On error, clear stale data and show N/A; never show stale data with an error flag.
- Do not add custom fetchers, `useEffect` token handling, manual-auth `fetch()`, `Promise.all` upstream calls, or zero metrics for upstream failures.

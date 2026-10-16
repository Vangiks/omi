# Omi fork agent guide

Fork of BasedHardware/omi (`upstream`) at Vangiks/omi (`origin`). Scope: the Electron desktop
app in `desktop/windows`, developed and run on Linux, and `web/`. The mobile app, firmware,
omiGlass and device SDKs were removed. `CLAUDE.md` points here.

## Routes

| Working on | Read |
|---|---|
| Desktop app (Electron, Windows/Linux) | `desktop/windows/AGENTS.md` |
| Web app / admin | `web/app/AGENTS.md` / `web/admin/AGENTS.md` |
| Backend (the Omi server the clients call) | `backend/AGENTS.md` |
| macOS desktop (Swift, kept for reference) | `desktop/macos/AGENTS.md` |
| Public documentation | `docs/AGENTS.md` |
| Product behavior | `PRODUCT.md`, `product/invariants/` |
| Behavior shared with the macOS app | `contracts/parity/README.md` |
| Current work: capability map, specs, plans | `CAPABILITY-MAP.md`, `SPEC-*.md`, `tasks/` |

## Repository conventions

- Git hooks come from `lefthook.yml` and install with `npx pnpm@10 install` in `desktop/windows`.
  Pre-push runs desktop typecheck, lint and the meeting tests. Keep Git identity in the user's
  configuration; temporary test identities use `git -c`.
- `desktop/windows/package.json` pins pnpm 10 through `packageManager`, so corepack's `pnpm`
  picks the right version; without corepack use `npx pnpm@10`. pnpm 11 ignores
  `node-linker=hoisted`. Never run `npm install` there.
- Ask before pushing to `origin` or opening a PR to `upstream`. Keep code meant for upstream free
  of fork-only changes so it can go out from a branch based on `upstream/main`.
- Upstream release and PR tooling is gone from this fork (most of `.github/`, Codemagic,
  `make preflight`, `scripts/pr-preflight`). Do not rely on it or restore it.
- Migrate in-tree callers together rather than preserving retired APIs with compatibility wrappers.

Keep this file a router. Add component facts to the owning guide.

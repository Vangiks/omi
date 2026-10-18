The `/dashboard` page embeds Grafana uid `omi-tv` (`/grafana/d/omi-tv/omi-tv`).
The checked-in copies are `dashboards/*.json` — three boards linked by the
All / macOS / Mobile switcher at the top of each:

| uid | scope |
|---|---|
| `omi-tv` | all platforms combined (source of truth, edit this one) |
| `omi-tv-macos` | the same board scoped to macOS (`platform=macos` on the PostHog routes) |
| `omi-tv-mobile` | the same board scoped to iOS/Android/iPadOS (`platform=mobile` on the PostHog routes). Mobile is fully instrumented in PostHog for usage metrics (iOS since 2025-03, Android since 2026-05) but emits no `Sign In Completed`, so its cohorts anchor on first-seen-any-event. Desktop-only surfaces (floating bar, crash telemetry, the desktop notifications toggle) are explicit placeholders. |

Account-level metrics with no platform dimension (mentor "Omi says" volumes,
the notifications-enabled gauge) live on the All board only — see
`ACCOUNT_LEVEL_TITLES` in the builder.

The viral metrics route uses one person key (`COALESCE(person_id, distinct_id)`)
for all user counts. `growthAccounting` and `stickinessTrend` contain complete
UTC calendar weeks only; the current trailing seven-day view is exposed
separately as top-level `rollingGrowth` (with current values mirrored under
`summary` for tile compatibility) and powers the explicitly labeled
"Last 7 days (rolling)" tile. Growth points expose positive `inactive`, its
`priorActive` denominator, `inactiveRate`, and `netActiveChange`; `inactiveLoss`
is the negative chart projection used by the stacked growth chart. The
`establishedRetention` series measures people active in both preceding complete
weeks and reports the current-week numerator, denominator, and rate.

The "Successful usage / capture output" panel keeps event families separate:
saved/reconciled `Memory Created` conversation creators, macOS transcribed
speech (`Desktop Recording Stopped` with positive `word_count`), and macOS
completed assistant users (`chat_agent_query_completed`). `Recording Started`
is intentionally not treated as successful usage; the mobile board shows only
the saved-conversation series because the other two events have no mobile
equivalent.

## Build

`omi-tv.json` is the only hand-edited board. After changing it, run

```bash
python3 web/admin/grafana/build_dashboards.py
```

which derives `omi-tv-macos.json` / `omi-tv-mobile.json` and re-applies the
shared contract to all three: timezone pinned to `America/New_York`, hourly
auto-refresh, switcher links, `platform=` pinned on every PostHog-backed
query (viral-metrics, dau-trends, retention, k-factor — behavioral coverage
in `web/admin/lib/__tests__/platform-scope-routes.test.ts`), and every daily/weekly/monthly date
column routed through the proxy's `_tzdates` rewrite (bare `YYYY-MM-DD`
strings parse as UTC midnight, which renders as 8 pm the previous NYC day and
hides the latest day). The builder is idempotent; commit all three outputs.
`test_build_dashboards.py` (manifest check `grafana-dashboard-build`) enforces
the contract.

## Activation panels

Activation sources differ by board:

| Board | Source | Definition |
|---|---|---|
| All, macOS | `/api/omi/stats/activation?days=60` (Firestore) | macOS signup activated iff a conversation exists in the first 7 days (`rate`, `weeks[]`) |
| Mobile | `viral-metrics?platform=mobile` (PostHog telemetry) | first-seen mobile user with `Memory Created` within 7 days (`activation[]`, `summary.activationRate`) |

PostHog coverage for the macOS telemetry path stays on viral-metrics as
`summary.activationTelemetryCoverage`; the Firestore compat overlay applies
only to the macOS scope.

## Apply dashboards

Grafana's database is the layout master — drag/resize edits made in the UI
persist there **and survive applies**: `apply_omi_tv_dashboard.py` fetches the
live board first and keeps its gridPos for every panel that already exists
(matched by id), so a dashboards-diff merge updates panel content without
reverting manual arrangement. Only brand-new panels land at their authored
position. It runs when a push changes `dashboards/*.json` (see the gated step
in `gcp_admin.yml`) or on `workflow_dispatch`. It no-ops when `GRAFANA_TOKEN` is
unset — do not invent a write token.

```bash
export GRAFANA_URL="https://admin.omi.me/grafana"   # optional
export GRAFANA_TOKEN="..."                         # Grafana service-account token
python3 web/admin/grafana/apply_omi_tv_dashboard.py
```

Note: large POSTs through the admin.omi.me rewrite get dropped — CI uses the
repo variable `GRAFANA_URL` pointing at the direct Cloud Run URL.

## Omi TV v2 — isolated Direction A board

`omi-tv-v2` is a separate UID. Its source is `build_wall_dashboard.py`, called
by `build_dashboards.py`; the three legacy board files retain their existing
contract. `apply_omi_tv_dashboard.py` accepts the new UID and still preserves
live layout on subsequent applies. This slice does not switch `/dashboard`.

The admin-authenticated `/api/omi/stats/wall` returns the 22 contract IDs plus
explicit capture-week-1 and plan-prepay-cash lines. Definitions, UTC cutoffs,
primary/entry attribution and qualification come from `lib/qualified-activity.ts`.
A bounded, coalesced 15-minute in-process cache preserves source refresh stamps
and expires at UTC midnight. PostHog carries its upstream `last_refresh`, or the
execution completion time of our live HogQL aggregate when the API omits it.
A cached upstream result without a refresh receipt stays unknown. Payload-cache
reads never advance source refresh timestamps.
It performs no Firestore cache writes and has no
stale-on-error fallback. Counts use primary qualified platform; cohort rates use
entry platform and include the full denominator. Rates do not add across splits:
the split numerators and denominators do. Missing sources remain null.

Each metric is one native **Canvas** panel, backed by Infinity as the only
external plugin. Canvas's SVG-icon element renders a data-only card through
Grafana's built-in SVG sanitizer. The card's background/border encloses the
label, scope chip, value, delta, platform splits, complete-period sparkline and
footnote. There are no floating subpanels, HTML overrides or custom JavaScript.
Responsive constraints keep the complete card inside narrow laptop columns.

Healthy live aggregates use full contrast. Stale, partial, explicitly material-gap
proxies and all synthetic fixtures are dimmed. A proxy label alone does not dim
an otherwise healthy audited aggregate. Fixture cards always say **FIXTURE**.
Cohort-rate deltas use percentage points; count and monetary deltas use relative
percent change. Scope chips say all or macOS; entry/primary attribution is in the
panel description and diagnostics. Money is compact at thousands, without cents
above $100. Full source reasons and versions remain in the diagnostics table.

MAU keeps two completed 30-day periods to stay within PostHog's query budget;
other usage/cohort trends retain six completed periods. Cohort anchors are still
first-seen proxies, with a bounded 180-day history check, not Firebase signups.
MCP, Windows/web foreground coverage and strict saved-state/source joins remain
incomplete and are disclosed. A bare MCP marker never qualifies.

Local verification (no production Firebase key, token minting or Grafana):

```bash
hostctl context
# Follow machine-config's local-container guide; the env command only selects its socket.
~/machine-config/scripts/container-runtime.zsh start
eval "$(~/machine-config/scripts/container-runtime.zsh env)"
source ~/.local/bin/gcp-agent-env.sh ro-prod
python3 web/admin/grafana/verify_wall_local.py serve  # keep foreground in one terminal
python3 web/admin/grafana/verify_wall_local.py provision  # another terminal, same Docker env
# Python environment with playwright + Chromium installed:
python3 web/admin/grafana/verify_wall_local.py screens
```

`serve` reads only the authorized PostHog key from the supplied local file, uses
the existing development admin bypass, binds localhost:3107, and disables
Firebase credentials. `--replay /absolute/aggregate.json`
replays a locally saved wall response without changing its source timestamps;
this requires non-production mode and `DEV_BYPASS_AUTH=1`. Production rejects
fixture mode. Local Grafana binds localhost:3207; the helper intentionally
fails if its container name exists rather than replacing an unrelated instance.
The provisioned board rewrites the proxy URL only in its local copy.

Run records and screenshots are written only to
`/Users/dazheng/workspace/omi/data/run-2026-10-14-omi-tv-metrics/`;
never commit that workspace run directory in the public repository. The local
verifier uses the `omi-tv-v2-rev1-1440.png` / `-1920.png` screenshot names.
Tracked UI-evidence copies belong under `.agent-artifacts/ui-evidence/`.

Deploy prerequisites and limits:

- Existing admin auth/proxy and Infinity datasource `omi-admin-api` must reach the
  new route. PostHog needs `POSTHOG_PERSONAL_API_KEY`, `POSTHOG_PROJECT_ID` and
  optionally `POSTHOG_HOST`. No production Firebase key is needed by the wall.
- Billing reuses `infra-costs` billing mode with aggregate-only reads, skipping
  Firestore/ledger diagnostics and the estimated fallback. Select ro-prod ADC
  locally; the runtime billing identity needs its existing BigQuery read/job
  permissions and provider invoice bindings. Missing provider/STT coverage is
  partial and dim. Cost/MAU uses the matching 30 days through D−2.
- Message ratings and trustworthy crash coverage need their missing aggregate
  sources. Zero crash events never produce 100%.

Validation: `npm test`, `npm run typecheck`, `npm run lint` in `web/admin`,
`python3 web/admin/grafana/test_build_dashboards.py`, and `make preflight`.
Opt-in live aggregate smoke checks: `OMI_TV_LIVE_CHECK=1 npm test --
lib/__tests__/wall-live.test.ts` with the authorized read-only source env loaded.

import {
  completeWeek,
  completeWindow,
  COVERAGE_REASON,
  DEFINITION_VERSION,
  freshness,
  isoDay,
  shiftDay,
  utcDay,
} from "./qualified-activity";
import {
  AggregateRows,
  activityQuery,
  cohortQuery,
  establishedQuery,
  Query,
  queryPosthog,
} from "./wall-posthog";

export const WALL_DEFINITIONS = [
  ["growth.wau", "WAU", "people", "Growth"],
  ["growth.true_new_7d", "Interim true-new", "people", "Growth"],
  ["activation.rate", "Activation · ≥2 days", "percent", "Activation"],
  ["retention.if_activated", "Retained if activated", "percent", "Retention"],
  ["retention.recovery", "Recovery", "percent", "Retention"],
  ["retention.day1_return", "Day-1 return", "percent", "Retention"],
  [
    "retention.established_week",
    "Established retention",
    "percent",
    "Retention",
  ],
  ["engagement.dau", "DAU", "people", "Growth"],
  ["engagement.mau", "MAU", "people", "Growth"],
  ["engagement.saved_creators", "Saved creators", "people", "Activation"],
  ["engagement.assistant_success", "Assistant success", "people", "Activation"],
  ["cost.net_day", "Settled net cost", "USD/day", "Health"],
  ["cost.per_mau_month", "Cost / MAU", "USD/person/30d", "Health"],
  ["health.crash_free", "Crash-free · macOS", "percent", "Health"],
  ["health.thumbs_positive", "Positive answers", "percent", "Health"],
  [
    "activation.capture_week1_share",
    "Capture in week 1",
    "percent",
    "Activation",
  ],
] as const;
export type MetricId = (typeof WALL_DEFINITIONS)[number][0];
export interface Split {
  macos: number | null;
  mobile: number | null;
  other: number | null;
}
export interface Metric {
  id: MetricId;
  label: string;
  column: string;
  value: number | null;
  prev: number | null;
  unit: string;
  split: Split;
  numerator: number | null;
  denominator: number | null;
  splitCounts: Record<
    keyof Split,
    { numerator: number; denominator: number }
  > | null;
  fixture?: boolean;
  materialGap?: boolean;
  status: "exact" | "proxy" | "null";
  reason: string | null;
  dataThrough: string | null;
  sourceRefreshedAt: string | null;
  definitionVersion: string;
  stale: boolean;
  partial: boolean;
  windowStart: string | null;
  windowEnd: string | null;
  trend: { date: string; value: number | null }[];
}
const emptySplit = (): Split => ({ macos: null, mobile: null, other: null });
const bucket = (p: unknown): keyof Split =>
  p === "macos" ? "macos" : p === "ios" || p === "android" ? "mobile" : "other";
export interface WallSources {
  query: Query;
  billing: () => Promise<{
    daily: { date: string; total: number }[];
    generatedAt: number;
    summary: { costSource?: string; partial: boolean; windowEnd?: string };
  } | null>;
}
export const defaultWallSources: WallSources = {
  query: queryPosthog,
  billing: async () => {
    const { computeBillingInfraCosts } = await import(
      "@/app/api/omi/stats/infra-costs/route"
    );
    return computeBillingInfraCosts(60, 0, true);
  },
};
const NULL_REASONS: Partial<Record<MetricId, string>> = {
  "health.crash_free":
    "Crash reporting coverage unverified; zero crash events cannot prove 100% crash-free",
  "health.thumbs_positive":
    "Message creation/vote aggregate source unavailable",
};
export async function computeWall(
  sources: WallSources = defaultWallSources,
  now = new Date()
) {
  const metrics = Object.fromEntries(
    WALL_DEFINITIONS.map(([id, label, unit, column]) => [
      id,
      {
        id,
        label,
        unit,
        column,
        value: null,
        prev: null,
        split: emptySplit(),
        numerator: null,
        denominator: null,
        splitCounts: null,
        status: "null",
        reason: NULL_REASONS[id] || "Source unavailable",
        dataThrough: null,
        sourceRefreshedAt: null,
        definitionVersion: DEFINITION_VERSION,
        stale: true,
        partial: false,
        windowStart: null,
        windowEnd: null,
        trend: [],
      } as Metric,
    ])
  ) as Record<MetricId, Metric>;
  const end = utcDay(now);
  function stamp(
    m: Metric,
    start: Date,
    stop: Date,
    reason = COVERAGE_REASON,
    refreshed: string | null = new Date().toISOString()
  ) {
    m.status = m.value == null ? "null" : "proxy";
    m.reason = reason;
    m.windowStart = start.toISOString();
    m.windowEnd = stop.toISOString();
    m.dataThrough = shiftDay(stop, -1).toISOString().slice(0, 10);
    m.sourceRefreshedAt = refreshed;
    m.stale = freshness(refreshed, m.dataThrough, "hourly", now).stale;
  }
  function fromCounts(
    id: MetricId,
    rows: AggregateRows,
    stop: Date,
    days: number,
    numeratorIndex = 2,
    denominatorIndex?: number
  ) {
    const m = metrics[id];
    for (let period = 5; period >= 0; period--) {
      const subset = rows.filter((r) => Number(r[0]) === period);
      const num = subset.reduce((a, r) => a + Number(r[numeratorIndex]), 0);
      const den =
        denominatorIndex == null
          ? null
          : subset.reduce((a, r) => a + Number(r[denominatorIndex]), 0);
      const value =
        subset.length === 0
          ? null
          : den == null
          ? num
          : den > 0
          ? (100 * num) / den
          : null;
      m.trend.push({ date: isoDay(shiftDay(stop, -days * period - 1)), value });
      if (period === 1) m.prev = value;
      if (period !== 0) continue;
      m.value = value;
      m.numerator = num;
      m.denominator = den;
      const counts = {
        macos: { numerator: 0, denominator: 0 },
        mobile: { numerator: 0, denominator: 0 },
        other: { numerator: 0, denominator: 0 },
      };
      for (const r of subset) {
        const b = counts[bucket(r[1])];
        b.numerator += Number(r[numeratorIndex]);
        b.denominator +=
          denominatorIndex == null ? 0 : Number(r[denominatorIndex]);
      }
      m.splitCounts = counts;
      for (const key of ["macos", "mobile", "other"] as const)
        m.split[key] =
          den == null
            ? counts[key].numerator
            : counts[key].denominator
            ? (100 * counts[key].numerator) / counts[key].denominator
            : null;
    }
    stamp(
      m,
      shiftDay(stop, -days),
      stop,
      COVERAGE_REASON +
        (rows.sourceRefreshedAt
          ? ""
          : " Source refresh watermark unavailable."),
      rows.sourceRefreshedAt ?? null
    );
    if (m.value == null)
      m.reason = "Zero cohort denominator; " + COVERAGE_REASON;
  }
  const jobs: (() => Promise<void>)[] = [];
  for (const [id, days, kind] of [
    ["growth.wau", 7, "active"],
    ["engagement.dau", 1, "active"],
    ["engagement.mau", 30, "active"],
    ["engagement.saved_creators", 1, "saved"],
    ["engagement.assistant_success", 1, "assistant"],
  ] as const)
    jobs.push(async () =>
      fromCounts(
        id,
        await sources.query(
          activityQuery(end, days, kind, days === 30 ? 2 : 6)
        ),
        end,
        days
      )
    );
  for (const maturity of [2, 7, 37] as const)
    jobs.push(async () => {
      const rows = await sources.query(cohortQuery(end, maturity));
      const stop = shiftDay(end, -maturity);
      if (maturity === 2)
        fromCounts("retention.day1_return", rows, stop, 7, 7, 2);
      if (maturity === 7) {
        fromCounts("activation.rate", rows, stop, 7, 3, 2);
        fromCounts("activation.capture_week1_share", rows, stop, 7, 8, 2);
      }
      if (maturity === 37) {
        fromCounts("retention.if_activated", rows, stop, 7, 4, 3);
        fromCounts("retention.recovery", rows, stop, 7, 6, 5);
      }
    });
  jobs.push(async () => {
    const rows = await sources.query(cohortQuery(end, 0)); // latest complete 7d; no future query bounds
    fromCounts("growth.true_new_7d", rows, end, 7, 2);
    metrics["growth.true_new_7d"].reason =
      "Interim first-seen proxy, bounded 180-day history; " + COVERAGE_REASON;
  });
  jobs.push(async () => {
    const stop = completeWeek(now).end;
    fromCounts(
      "retention.established_week",
      await sources.query(establishedQuery(stop)),
      stop,
      7,
      3,
      2
    );
  });
  // Bound PostHog concurrency to avoid flooding the query service.
  for (let i = 0; i < jobs.length; i += 2)
    await Promise.allSettled(jobs.slice(i, i + 2).map((job) => job()));
  // Cohort period labels describe the denominator; dataThrough describes the
  // fully observed outcome cutoff. Keep both rather than aging a mature cohort.
  const cohortIds: MetricId[] = [
    "activation.rate",
    "activation.capture_week1_share",
    "retention.if_activated",
    "retention.recovery",
    "retention.day1_return",
  ];
  for (const id of cohortIds) {
    const m = metrics[id];
    if (m.value != null) {
      m.dataThrough = isoDay(shiftDay(end, -1));
      m.reason = `First-seen cohort ${m.windowStart?.slice(
        0,
        10
      )} to ${m.windowEnd?.slice(0, 10)} (exclusive end); ${m.reason}`;
    }
  }
  await Promise.allSettled([
    (async () => {
      const bill = await sources.billing();
      if (!bill || bill.summary.costSource !== "billing") return;
      const cutoff = isoDay(shiftDay(end, -2));
      const daily = bill.daily
        .filter((d) => d.date <= cutoff)
        .sort((a, b) => a.date.localeCompare(b.date));
      const last = daily.find((d) => d.date === cutoff);
      if (!last) return;
      const m = metrics["cost.net_day"];
      m.value = last.total;
      m.prev =
        daily.find((d) => d.date === isoDay(shiftDay(end, -3)))?.total ?? null;
      m.partial = true;
      stamp(
        m,
        shiftDay(end, -2),
        shiftDay(end, -1),
        "Billing mode net credits; provider/STT coverage partial; allocation unavailable",
        new Date(bill.generatedAt).toISOString()
      );
      m.stale = freshness(
        m.sourceRefreshedAt,
        m.dataThrough,
        "settled",
        now
      ).stale;
      m.trend = daily.slice(-14).map((d) => ({ date: d.date, value: d.total }));
      const window = completeWindow(30, now, 1); // ends D-1 exclusive, D-2 inclusive
      const costs = daily.filter(
        (d) => d.date >= isoDay(window.start) && d.date < isoDay(window.end)
      );
      if (new Set(costs.map((d) => d.date)).size !== 30) return;
      const rows = await sources.query(
        activityQuery(window.end, 30, "active", 2)
      );
      const mau = rows
        .filter((r) => Number(r[0]) === 0)
        .reduce((s, r) => s + Number(r[2]), 0);
      const c = metrics["cost.per_mau_month"];
      if (!mau) {
        c.reason = "Zero same-window MAU denominator";
        return;
      }
      c.value = costs.reduce((s, d) => s + d.total, 0) / mau;
      c.denominator = mau;
      c.partial = true;
      stamp(
        c,
        window.start,
        window.end,
        "Same-window settled 30d billed cost / qualified MAU; provider/STT coverage partial; " +
          COVERAGE_REASON,
        new Date(bill.generatedAt).toISOString()
      );
      c.sourceRefreshedAt = rows.sourceRefreshedAt
        ? [
            new Date(bill.generatedAt).toISOString(),
            rows.sourceRefreshedAt,
          ].sort()[0]
        : null;
      c.stale = freshness(
        c.sourceRefreshedAt,
        c.dataThrough,
        "settled",
        now
      ).stale;
    })(),
  ]);
  const list = WALL_DEFINITIONS.map(([id]) => metrics[id]);
  return {
    definitionVersion: DEFINITION_VERSION,
    generatedAt: new Date().toISOString(),
    metrics: list,
    partial: list.some((m) => m.status === "null" || m.partial),
  };
}
export type WallPayload = Awaited<ReturnType<typeof computeWall>>;

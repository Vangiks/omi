import { beforeEach, describe, expect, it, vi } from "vitest";
import { computeWall, WALL_DEFINITIONS, WallSources } from "../wall-metrics";
import { resetWallCache, wallPayload } from "../wall-cache";
const now = new Date("2026-10-15T12:00Z");
const fail = async () => {
  throw new Error("unavailable");
};
const sources = (): WallSources => ({
  query: fail,
  billing: fail,
});

describe("wall source and payload contracts", () => {
  beforeEach(() => {
    resetWallCache();
    vi.useRealTimers();
  });
  it("returns every contract ID with null/reason for missing sources, never fabricated zero", async () => {
    const wall = await computeWall(sources(), now);
    expect(wall.metrics).toHaveLength(WALL_DEFINITIONS.length);
    expect(
      wall.metrics.every(
        (m) => m.value === null && m.status === "null" && m.reason
      )
    ).toBe(true);
  });
  it("conserves counts and computes rates from denominators including unqualified entry users", async () => {
    const s = sources();
    s.query = async (sql) =>
      sql.includes("denominator,countIf")
        ? [
            [0, "macos", 10, 4, 2, 6, 1, 3, 5],
            [0, "ios", 20, 2, 1, 18, 3, 4, 6],
            [0, "unknown", 30, 0, 0, 30, 1, 0, 0],
            [1, "macos", 10, 2, 1, 8, 1, 1, 2],
          ]
        : sql.includes("countIf(eligible)")
        ? [
            [0, "macos", 10, 7],
            [0, "ios", 20, 10],
          ]
        : [
            [0, "macos", 3],
            [0, "ios", 4],
            [0, "android", 2],
            [1, "macos", 2],
          ];
    const wall = await computeWall(s, now);
    const get = (id: string) => wall.metrics.find((m) => m.id === id)!;
    expect(get("growth.wau").value).toBe(9);
    expect(get("growth.wau").split).toEqual({ macos: 3, mobile: 6, other: 0 });
    expect(get("activation.rate").value).toBe(10);
    expect(get("activation.rate").denominator).toBe(60);
    expect(get("activation.rate").split.other).toBe(0);
    expect(get("retention.if_activated").value).toBe(50);
    expect(get("retention.established_week").value).toBeCloseTo(
      (100 * 17) / 30
    );
    expect(get("growth.wau").trend.at(-1)?.date).toBe("2026-10-14");
  });
  it("empty telemetry and zero denominators stay null", async () => {
    const s = sources();
    s.query = async () => [];
    expect(
      (await computeWall(s, now)).metrics.every((m) => m.value === null)
    ).toBe(true);
  });
  it("coalesces payload reads and invalidates at UTC midnight without restamping sources", async () => {
    const payload = await computeWall(sources(), now);
    const compute = vi.fn(async () => payload);
    const [a, b] = await Promise.all([
      wallPayload(now, compute),
      wallPayload(now, compute),
    ]);
    expect(a).toBe(b);
    expect(compute).toHaveBeenCalledTimes(1);
    expect(await wallPayload(new Date("2026-10-15T12:01Z"), compute)).toBe(a);
    await wallPayload(new Date("2026-10-16T00:00Z"), compute);
    expect(compute).toHaveBeenCalledTimes(2);
  });
});

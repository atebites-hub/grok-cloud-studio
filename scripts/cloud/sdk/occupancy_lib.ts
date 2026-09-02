/** Occupancy fan-out for Agent.list + listRuns.

Bounded concurrency, per-call timeout, fail-closed OccupancyError so capacity
beats do not hang. Existence ACTIVE/IDLE is not liveness.
*/
export const DEFAULT_CONCURRENCY = 8;
export const DEFAULT_TIMEOUT_MS = 15_000;
export const DEFAULT_DEADLINE_MS = 30_000;

export class OccupancyError extends Error {
  readonly reason: string;

  constructor(message: string, reason = "err") {
    super(message);
    this.name = "OccupancyError";
    this.reason = reason;
  }
}

export function envInt(name: string, fallback: number, lo: number, hi: number): number {
  const raw = (process.env[name] || "").trim();
  const n = raw ? Number(raw) : fallback;
  if (!Number.isFinite(n) || n <= 0) return fallback;
  return Math.min(Math.max(Math.floor(n), lo), hi);
}

export function envFloatSec(name: string, fallbackSec: number, hi: number): number {
  const raw = (process.env[name] || "").trim();
  const n = raw ? Number(raw) : fallbackSec;
  if (!Number.isFinite(n) || n <= 0) return fallbackSec;
  return Math.min(n, hi);
}

export async function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<T>((_, reject) => {
        timer = setTimeout(() => {
          reject(new OccupancyError(`${label} timeout`, "timeout"));
        }, Math.max(ms, 50));
      }),
    ]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

export async function mapWithConcurrency<T, R>(
  items: T[],
  concurrency: number,
  worker: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  if (!items.length) return [];
  const n = Math.max(1, Math.min(concurrency, items.length));
  const out: R[] = new Array(items.length);
  let next = 0;
  async function pump(): Promise<void> {
    while (true) {
      const i = next++;
      if (i >= items.length) return;
      out[i] = await worker(items[i], i);
    }
  }
  await Promise.all(Array.from({ length: n }, () => pump()));
  return out;
}

export type OccupancySummary = {
  running: number;
  leftoverActive: number;
  creating: number;
  listed: number;
};

export function normalizeRunStatus(raw: string | undefined): string {
  if (!raw) return "none";
  const upper = String(raw).trim().toUpperCase();
  return upper === "NONE" ? "none" : upper;
}

export function classifyRow(
  agentStatus: string,
  runStatus: string,
): "running" | "creating" | "leftover_active" | "other" {
  const run = normalizeRunStatus(runStatus);
  if (run === "RUNNING") return "running";
  if (run === "CREATING") return "creating";
  const membership = (agentStatus || "").trim().toUpperCase();
  if (membership === "ACTIVE" || membership === "IDLE" || membership === "") {
    return "leftover_active";
  }
  return "other";
}

export function pickLatestRun<T extends { createdAt?: number }>(items: T[]): T | undefined {
  if (!items.length) return undefined;
  return items.slice().sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0))[0];
}

export function summarizeOccupancy(
  rows: Array<{ agentStatus: string; runStatus: string }>,
): OccupancySummary {
  let running = 0;
  let leftoverActive = 0;
  let creating = 0;
  for (const row of rows) {
    const kind = classifyRow(row.agentStatus, row.runStatus);
    if (kind === "running") running += 1;
    else if (kind === "creating") creating += 1;
    else if (kind === "leftover_active") leftoverActive += 1;
  }
  return { running, leftoverActive, creating, listed: rows.length };
}

export function formatOccupancyLine(summary: OccupancySummary): string {
  return (
    `CLOUD_OCCUPANCY running=${summary.running} leftover_active=${summary.leftoverActive} ` +
    `creating=${summary.creating} listed=${summary.listed}`
  );
}

export function occupancyLimits(): {
  concurrency: number;
  timeoutMs: number;
  deadlineMs: number;
} {
  const timeoutSec = (process.env.CLOUD_LIST_RUNS_TIMEOUT_SEC || "").trim()
    ? Math.max(envFloatSec("CLOUD_LIST_RUNS_TIMEOUT_SEC", 15, 15), 0.05)
    : Math.max(Math.min(envFloatSec("CLOUD_CURL_MAX_TIME", 15, 15), 15), 0.05);
  const timeoutMs = Math.round(timeoutSec * 1000);
  const deadlineRaw = (process.env.CLOUD_OCCUPANCY_DEADLINE_SEC || "").trim();
  const deadlineSec = deadlineRaw
    ? Math.min(Math.max(Number(deadlineRaw) || 30, timeoutSec), 120)
    : Math.max(30, timeoutSec);
  return {
    concurrency: envInt("CLOUD_OCCUPANCY_CONCURRENCY", DEFAULT_CONCURRENCY, 1, 32),
    timeoutMs,
    deadlineMs: Math.round(deadlineSec * 1000),
  };
}

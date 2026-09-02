/** Latest Extra High run for wait-notify / FLEET_DONE.
 *
 * Leftover FINISHED is not terminal while a newer run is CREATING or RUNNING.
 * Distinct from occupancy #132 and paginated-catalog. Never Bot CloudAgent.
 */

export const IN_FLIGHT = new Set(["CREATING", "RUNNING"]);
export const TERMINAL = new Set(["FINISHED", "ERROR", "CANCELLED", "EXPIRED"]);

export type RunLike = {
  id?: string;
  status?: string;
  runStatus?: string;
  createdAt?: number | string;
  createdAtMs?: number;
  created_at?: number | string;
  created_at_ms?: number;
};

export function runStatus(run: RunLike | undefined): string {
  if (!run) return "";
  const raw = run.status || run.runStatus || "";
  return String(raw).trim().toUpperCase();
}

export function unwrapRuns(payload: unknown): RunLike[] {
  if (Array.isArray(payload)) {
    return payload.filter(isRunLike);
  }
  if (!payload || typeof payload !== "object") return [];
  const rec = payload as Record<string, unknown>;
  const nested = rec.items ?? rec.runs;
  if (Array.isArray(nested)) {
    return nested.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const row = item as Record<string, unknown>;
      if (row.run && typeof row.run === "object" && !Array.isArray(row.run) && !("id" in row)) {
        return isRunLike(row.run) ? [row.run as RunLike] : [];
      }
      return isRunLike(item) ? [item as RunLike] : [];
    });
  }
  if (isRunLike(payload)) return [payload];
  return [];
}

function isRunLike(value: unknown): value is RunLike {
  if (!value || typeof value !== "object") return false;
  const row = value as RunLike;
  return Boolean(row.id || row.status || row.runStatus);
}

export function createdAtMs(run: RunLike): number {
  const msKeys = [run.createdAtMs, run.created_at_ms];
  for (const val of msKeys) {
    if (typeof val === "number" && val > 0) return Math.trunc(val);
  }
  const raw = run.createdAt ?? run.created_at;
  if (typeof raw === "number" && Number.isFinite(raw)) {
    const num = Math.trunc(raw);
    return num > 1_000_000_000_000 ? num : num * 1000;
  }
  if (typeof raw === "string" && raw.trim()) {
    const ms = Date.parse(raw.trim());
    if (!Number.isNaN(ms)) return ms;
  }
  return 0;
}

export function pickLatestRun(runs: RunLike[]): RunLike | undefined {
  if (!runs.length) return undefined;
  let best = 0;
  for (let i = 1; i < runs.length; i += 1) {
    const a = createdAtMs(runs[best]);
    const b = createdAtMs(runs[i]);
    if (b > a || (b === a && i > best)) best = i;
  }
  return runs[best];
}

export function waiterObserve(runs: RunLike[], pinned?: RunLike): RunLike | undefined {
  const combined = [...runs];
  if (pinned) {
    const pid = String(pinned.id || "");
    if (pid && !combined.some((row) => String(row.id || "") === pid)) {
      combined.push(pinned);
    }
  }
  const inFlight = combined.filter((row) => IN_FLIGHT.has(runStatus(row)));
  if (inFlight.length) return pickLatestRun(inFlight);
  return pickLatestRun(combined);
}

export function mayFleetDone(run: RunLike | undefined): boolean {
  return Boolean(run) && TERMINAL.has(runStatus(run));
}

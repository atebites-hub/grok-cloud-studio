import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Agent, type Run } from "@cursor/sdk";
import { collectResult, type DirectorResult } from "./collect.ts";
import {
  boundRepoUrl,
  boundRepos,
  die,
  isRateLimitError,
  loadApiKey,
  mapRunStatus,
  rateLimitBackoffMs,
  retryAfterFromError,
  safeError,
} from "./common.ts";
import {
  mayFleetDone,
  unwrapRuns,
  waiterObserve,
  type RunLike,
} from "./latest_run.ts";
import { attachShipGate } from "./pr-checks.ts";
import { githubPrIsDraft } from "./pr-draft.ts";
import { githubPrMergeable, mapGitHubMergeable } from "./pr-mergeable.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..", "..");
const LEDGER = resolve(ROOT, "scripts", "cloud", "fleet_ledger.py");

function sleep(ms: number): Promise<void> {
  return new Promise((resolveSleep) => {
    setTimeout(resolveSleep, ms);
  });
}

function preferRest(): boolean {
  if ((process.env.CLOUD_FORCE_REST || "").trim() === "1") return true;
  if ((process.env.GCS_CLOUD_BACKEND || "").trim() === "rest") return true;
  if ((process.env.CURSOR_API_BASE || "").trim()) return true;
  return false;
}

function parseArgs(argv: string[]): { agentId: string; runId: string } {
  let agentId = "";
  let runId = "";
  const positional: string[] = [];
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--id" || arg === "--agent") {
      agentId = argv[i + 1] || "";
      i += 1;
      continue;
    }
    if (arg.startsWith("--id=")) {
      agentId = arg.slice("--id=".length);
      continue;
    }
    if (arg === "--run" || arg === "--run-id") {
      runId = argv[i + 1] || "";
      i += 1;
      continue;
    }
    if (arg.startsWith("--run=")) {
      runId = arg.slice("--run=".length);
      continue;
    }
    if (!arg.startsWith("-")) positional.push(arg);
  }
  if (!agentId) agentId = positional[0] || "";
  if (!runId) runId = positional[1] || "";
  return { agentId, runId };
}

function basicAuthHeader(apiKey: string): string {
  return `Basic ${Buffer.from(`${apiKey}:`, "utf8").toString("base64")}`;
}

type HttpErr = Error & { status?: number; retryAfter?: string | null };

function httpStatus(err: unknown): number {
  if (err && typeof err === "object" && "status" in err) {
    const raw = (err as HttpErr).status;
    const status = typeof raw === "number" ? raw : Number(raw);
    return Number.isFinite(status) ? status : 0;
  }
  return 0;
}

/** 401/403 fail closed. 429 is retried by the outer poll. Other misses stay collection gaps. */
function rethrowWaiterHttp(err: unknown): void {
  if (isRateLimitError(err)) throw err;
  const status = httpStatus(err);
  if (status === 401 || status === 403) throw err;
}

async function restGet(path: string, apiKey: string): Promise<Record<string, unknown>> {
  const base = (process.env.CURSOR_API_BASE || "https://api.cursor.com").replace(/\/$/, "");
  const res = await fetch(`${base}${path}`, {
    headers: {
      Accept: "application/json",
      Authorization: basicAuthHeader(apiKey),
    },
  });
  if (!res.ok) {
    const err: HttpErr = new Error(`REST ${res.status} ${path}`);
    err.status = res.status;
    err.retryAfter = res.headers.get("retry-after");
    throw err;
  }
  return (await res.json()) as Record<string, unknown>;
}

async function pauseForRateLimit(err: unknown, attempt: number, agentId: string): Promise<void> {
  const delay = rateLimitBackoffMs(attempt, retryAfterFromError(err));
  process.stdout.write(
    `CLOUD_WAITER_RETRY id=${agentId} status=429 backoffMs=${delay} attempt=${attempt}\n`,
  );
  await sleep(delay);
}

function unwrap(data: Record<string, unknown>, key: string): Record<string, unknown> {
  const inner = data[key];
  if (inner && typeof inner === "object" && !Array.isArray(inner) && !("id" in data)) {
    return inner as Record<string, unknown>;
  }
  return data;
}

async function restLatestRuns(agentId: string, apiKey: string): Promise<RunLike[]> {
  const listed = await restGet(`/v1/agents/${agentId}/runs`, apiKey);
  return unwrapRuns(listed);
}

async function restGetRun(
  agentId: string,
  runId: string,
  apiKey: string,
): Promise<RunLike | undefined> {
  const runRaw = unwrap(await restGet(`/v1/agents/${agentId}/runs/${runId}`, apiKey), "run");
  return runRaw as RunLike;
}

function directorResultFromRest(
  agentId: string,
  agentRaw: Record<string, unknown>,
  runRaw: Record<string, unknown>,
  runStatus: string,
): DirectorResult {
  const git = (runRaw.git || {}) as { branches?: Array<{ prUrl?: string; branch?: string }> };
  const withPr = (git.branches || []).find((b) => b.prUrl);
  const resultText = typeof runRaw.result === "string" ? runRaw.result : null;
  return {
    agentId: String(agentRaw.id || agentId),
    name: String(agentRaw.name || ""),
    url: String(agentRaw.url || `https://cursor.com/agents/${agentId}`),
    runId: String(runRaw.id || ""),
    status: runStatus,
    agentStatus: String(agentRaw.status || ""),
    runStatus,
    prUrl: withPr?.prUrl || null,
    branches: (git.branches || []).map((b) => b.branch).filter((b): b is string => Boolean(b)),
    branch: (git.branches || []).find((b) => b.branch)?.branch || null,
    summary: null,
    result: resultText,
    error: null,
    repoUrl: boundRepoUrl(agentRaw, runRaw),
    repos: boundRepos(agentRaw),
  };
}

async function restPoll(agentId: string, runId: string, apiKey: string): Promise<DirectorResult> {
  const pollSec = Math.max(5, Number(process.env.CLOUD_WATCH_INTERVAL || "15") || 15);
  const timeoutSec = Number(process.env.CLOUD_WATCH_TIMEOUT_SEC || "0") || 0;
  const started = Date.now();
  const deadline = timeoutSec > 0 ? started + timeoutSec * 1000 : Number.POSITIVE_INFINITY;
  let last = "unknown";
  let rateLimitAttempt = 0;
  // 429 must not abort the waiter. Resume until the run is terminal even if
  // the agent row is leftover ACTIVE (membership) with a FINISHED run.
  while (Date.now() < deadline) {
    try {
      const agentRaw = unwrap(await restGet(`/v1/agents/${agentId}`, apiKey), "agent");
      let collectionOk = false;
      let runs: RunLike[] = [];
      try {
        runs = await restLatestRuns(agentId, apiKey);
        collectionOk = true;
      } catch (err) {
        rethrowWaiterHttp(err);
        collectionOk = false;
      }
      let pinned: RunLike | undefined;
      if (runId) {
        try {
          pinned = await restGetRun(agentId, runId, apiKey);
        } catch (err) {
          rethrowWaiterHttp(err);
          pinned = undefined;
        }
      }
      const observed = waiterObserve(runs, pinned);
      const latestId = String(observed?.id || "");
      let runRaw: Record<string, unknown> = { ...((observed || {}) as Record<string, unknown>) };
      let runStatusMapped = mapRunStatus(String(observed?.status || ""));
      if (latestId) {
        try {
          runRaw = unwrap(await restGet(`/v1/agents/${agentId}/runs/${latestId}`, apiKey), "run");
          runStatusMapped = mapRunStatus(String(runRaw.status || observed?.status || ""));
        } catch (err) {
          rethrowWaiterHttp(err);
          runStatusMapped = mapRunStatus(String(observed?.status || ""));
        }
      }
      last = runStatusMapped || last;
      const refreshed: RunLike = { ...(runRaw as RunLike), id: latestId, status: runStatusMapped };
      const current = waiterObserve(
        runs.map((row) => (String(row.id || "") === latestId ? refreshed : row)),
        pinned,
      );
      const canFleetDone =
        collectionOk &&
        runs.length > 0 &&
        mayFleetDone(current) &&
        String(current?.id || "") === latestId;
      if (canFleetDone) {
        return directorResultFromRest(agentId, agentRaw, runRaw, runStatusMapped);
      }
      rateLimitAttempt = 0;
      process.stdout.write(
        `CLOUD_WAITER_POLL id=${agentId} run=${latestId || "none"} runStatus=${runStatusMapped || "none"}\n`,
      );
      const remaining = deadline - Date.now();
      if (remaining <= 0) break;
      await sleep(Math.min(pollSec * 1000, remaining));
    } catch (err) {
      if (!isRateLimitError(err)) throw err;
      await pauseForRateLimit(err, rateLimitAttempt, agentId);
      rateLimitAttempt += 1;
    }
  }
  throw new Error(`CLOUD_WAITER_TIMEOUT id=${agentId} lastStatus=${last}`);
}

async function latestRun(
  agentId: string,
  apiKey: string,
  runId?: string,
): Promise<{ run: Run | undefined; listed: number }> {
  const listed = await Agent.listRuns(agentId, { runtime: "cloud", apiKey, limit: 20 });
  const items = listed.items || [];
  let pinned: Run | undefined;
  if (runId) {
    try {
      pinned = await Agent.getRun(runId, { runtime: "cloud", agentId, apiKey });
    } catch (err) {
      rethrowWaiterHttp(err);
      pinned = undefined;
    }
  }
  const observed = waiterObserve(items as RunLike[], pinned as RunLike | undefined);
  if (!observed) return { run: undefined, listed: items.length };
  const oid = String(observed.id || "");
  const fromList = items.find((row) => row.id === oid);
  if (fromList) return { run: fromList, listed: items.length };
  if (pinned && pinned.id === oid) return { run: pinned, listed: items.length };
  return { run: undefined, listed: items.length };
}

async function sdkWait(agentId: string, runId: string, apiKey: string): Promise<DirectorResult> {
  const pollSec = Math.max(5, Number(process.env.CLOUD_WATCH_INTERVAL || "15") || 15);
  const timeoutSec = Number(process.env.CLOUD_WATCH_TIMEOUT_SEC || "0") || 0;
  const started = Date.now();
  const deadline = timeoutSec > 0 ? started + timeoutSec * 1000 : Number.POSITIVE_INFINITY;
  let last = "unknown";
  let rateLimitAttempt = 0;
  while (Date.now() < deadline) {
    try {
      const { run, listed } = await latestRun(agentId, apiKey, runId || undefined);
      const runStatus = mapRunStatus(run?.status);
      last = runStatus;
      if (run && listed > 0 && mayFleetDone({ id: run.id, status: runStatus })) {
        return collectResult(agentId, run.id);
      }
      rateLimitAttempt = 0;
      if (run && typeof run.supports === "function" && run.supports("wait")) {
        const remaining = deadline - Date.now();
        if (remaining <= 0) break;
        try {
          // timeout=0 => remaining is Infinity; sleep(Infinity) hung FLEET_DONE.
          const slice = Math.min(pollSec * 1000, Number.isFinite(remaining) ? remaining : pollSec * 1000);
          await Promise.race([
            run.wait(),
            sleep(slice).then(() => {
              throw new Error("wait-poll");
            }),
          ]);
          continue;
        } catch (err) {
          if (safeError(err).includes("wait-timeout")) break;
          if (isRateLimitError(err)) {
            await pauseForRateLimit(err, rateLimitAttempt, agentId);
            rateLimitAttempt += 1;
            continue;
          }
        }
      }
      const remaining = deadline - Date.now();
      if (remaining <= 0) break;
      await sleep(Math.min(pollSec * 1000, remaining));
    } catch (err) {
      if (!isRateLimitError(err)) throw err;
      await pauseForRateLimit(err, rateLimitAttempt, agentId);
      rateLimitAttempt += 1;
    }
  }
  throw new Error(`CLOUD_WAITER_TIMEOUT id=${agentId} lastStatus=${last}`);
}

type WaiterPayload = DirectorResult & {
  draft?: boolean;
  mergeable?: string;
  checkRuns?: number;
  emptyChecks?: boolean;
  shipGateOk?: boolean;
};

async function withDraftFlag<T extends DirectorResult>(
  payload: T,
): Promise<T & { draft?: boolean }> {
  // One-shot GitHub draft lookup. Do not reuse Extra High waiter 429 backoff (GCS #35).
  const draft = await githubPrIsDraft(payload.prUrl);
  if (draft === null) return payload;
  return { ...payload, draft };
}

async function withMergeableFlag(payload: DirectorResult): Promise<WaiterPayload> {
  // One-shot GitHub mergeable lookup. Do not reuse Extra High waiter 429 backoff (GCS #35).
  const current = payload as WaiterPayload;
  const known = typeof current.mergeable === "string" ? current.mergeable.trim().toUpperCase() : "";
  if (known === "CONFLICTING" || known === "MERGEABLE" || known === "UNKNOWN") {
    return { ...current, mergeable: known };
  }
  if (payload.mergeableState) {
    const mapped = mapGitHubMergeable({ mergeable_state: payload.mergeableState });
    if (mapped) return { ...payload, mergeable: mapped };
  }
  const mergeable = await githubPrMergeable(payload.prUrl);
  if (mergeable === null) return payload;
  return { ...payload, mergeable };
}

function ownerSeat(): string {
  return (process.env.GCS_DIRECTOR_SEAT || process.env.CLOUD_OWNER_SEAT || "").trim();
}

function ledgerNotify(agentId: string, payload: WaiterPayload): void {
  const seat = ownerSeat();
  const proc = spawnSync(
    "python3",
    [
      LEDGER,
      "notify",
      "--id",
      agentId,
      "--notified-by",
      "waiter",
      ...(seat ? ["--seat", seat] : []),
    ],
    {
      cwd: ROOT,
      input: JSON.stringify(payload),
      encoding: "utf8",
      env: process.env,
    },
  );
  if (proc.stdout) process.stdout.write(proc.stdout);
  if (proc.stderr) process.stderr.write(proc.stderr);
  if (proc.status !== 0) {
    throw new Error(`fleet ledger notify failed rc=${proc.status ?? "null"}`);
  }
}

async function main(): Promise<void> {
  const { agentId, runId } = parseArgs(process.argv.slice(2));
  if (!agentId) {
    die("usage: wait-notify.ts --id <bc-id> [--run run-id]", 2);
  }
  const apiKey = loadApiKey();
  process.stdout.write(`CLOUD_WAITER_START id=${agentId} run=${runId || "latest"}\n`);
  try {
    const payload = await withMergeableFlag(
      await withDraftFlag(
        await attachShipGate(
          preferRest() ? await restPoll(agentId, runId, apiKey) : await sdkWait(agentId, runId, apiKey),
        ),
      ),
    );
    ledgerNotify(agentId, payload);
    const draftTag =
      payload.draft === true ? " draft=true" : payload.draft === false ? " draft=false" : "";
    const checkTag =
      typeof payload.checkRuns === "number"
        ? ` check_runs=${payload.checkRuns}`
        : payload.emptyChecks === true
          ? " check_runs=0"
          : "";
    const gateTag =
      payload.shipGateOk === true ? " shipGate=ok" : payload.emptyChecks === true ? " shipGate=empty" : "";
    const mergeTag = payload.mergeable ? ` mergeable=${payload.mergeable}` : "";
    const ctx = (payload.result || payload.summary || "").replace(/\s+/g, " ").trim().slice(0, 240);
    process.stdout.write(
      `CLOUD_WAITER_DONE id=${agentId} run=${payload.runId || "none"} runStatus=${payload.runStatus || "unknown"} pr=${payload.prUrl || "none"} repo=${payload.repoUrl || "none"}${draftTag}${checkTag}${gateTag}${mergeTag}${ctx ? ` context=${ctx}` : ""}\n`,
    );
  } catch (err) {
    console.error(`CLOUD_WAITER_ERR id=${agentId} ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

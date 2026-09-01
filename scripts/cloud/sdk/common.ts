import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { resolve } from "node:path";
import type {
  CloudAgentOptions,
  ModelSelection,
  Run,
  RunError,
  SDKAgentInfo,
} from "@cursor/sdk";

export const DEFAULT_REF = "main";
export const AGENT_URL_PREFIX = "https://cursor.com/agents";

function envFirst(...names: string[]): string {
  for (const name of names) {
    const value = (process.env[name] || "").trim();
    if (value) return value;
  }
  return "";
}

export function extraHighModel(): ModelSelection {
  return {
    id: process.env.CURSOR_CLOUD_MODEL || "grok-4.6",
    params: [
      { id: "effort", value: process.env.CURSOR_CLOUD_EFFORT || "xhigh" },
      { id: "fast", value: "false" },
    ],
  };
}

/** Target git repo for Extra High creates. Fail closed if unset. */
export function cloudRepo(): string {
  const url = envFirst("GCS_CLOUD_REPO", "CLOUD_REPO_URL", "CURSOR_CLOUD_REPO");
  if (!url) {
    throw new Error(
      "CLOUD_BLOCKED: set GCS_CLOUD_REPO or CLOUD_REPO_URL (git URL Extra High should open PRs against)",
    );
  }
  return url;
}

export function cloudRef(): string {
  return envFirst("GCS_CLOUD_REF", "CLOUD_REPO_REF", "CURSOR_CLOUD_REF") || DEFAULT_REF;
}

/**
 * v1 agent metadata is off by default. Cursor Cloud API v1 currently returns
 * feature_unavailable ("API v1 agent metadata is not enabled.") when it is sent.
 * Opt in with CLOUD_SDK_METADATA=1 only after that flag is enabled.
 */
export function cloudMetadata(): Record<string, string> | undefined {
  const raw = (process.env.CLOUD_SDK_METADATA || "").trim().toLowerCase();
  if (raw === "1" || raw === "true" || raw === "yes") {
    return { gcs: "director-cloud", via: "sdk" };
  }
  return undefined;
}

export function cloudCreateOptions(): CloudAgentOptions {
  const metadata = cloudMetadata();
  return {
    repos: [{ url: cloudRepo(), startingRef: cloudRef() }],
    autoCreatePR: true,
    ...(metadata ? { metadata } : {}),
  };
}

function errorField(err: unknown, key: string): unknown {
  if (err && typeof err === "object" && key in err) {
    return (err as Record<string, unknown>)[key];
  }
  return undefined;
}

/**
 * Exit 75 so bash wrappers REST-fall-back. Only for create failures that look
 * retryable/unavailable (including v1 metadata feature_unavailable). Auth and
 * other client errors stay 1 so we do not double-create after a real reject.
 */
export function sdkCreateFailExitCode(err: unknown): number {
  const msg = safeError(err).toLowerCase();
  const code = String(errorField(err, "code") ?? "").toLowerCase();
  const statusRaw = errorField(err, "status");
  const status = typeof statusRaw === "number" ? statusRaw : Number.NaN;
  if (errorField(err, "isRetryable") === true) return 75;
  if (code === "feature_unavailable") return 75;
  if (msg.includes("feature_unavailable")) return 75;
  if (msg.includes("api v1 agent metadata is not enabled")) return 75;
  if (msg.includes("metadata is not enabled")) return 75;
  if (status === 429 || status === 502 || status === 503 || status === 504) return 75;
  if (
    msg.includes("econnreset") ||
    msg.includes("etimedout") ||
    msg.includes("enotfound") ||
    msg.includes("fetch failed")
  ) {
    return 75;
  }
  return 1;
}

export function agentUrl(agentId: string): string {
  return `${AGENT_URL_PREFIX}/${agentId}`;
}

/** Load CURSOR_API_KEY from the environment or ~/.config/cursor/agent.env. Never print it. */
export function loadApiKey(): string {
  const fromEnv = process.env.CURSOR_API_KEY?.trim();
  if (fromEnv) return fromEnv;
  const envFile =
    process.env.CURSOR_AGENT_ENV || resolve(homedir(), ".config/cursor/agent.env");
  if (!existsSync(envFile)) {
    throw new Error("CLOUD_BLOCKED: CURSOR_API_KEY missing (source ~/.config/cursor/agent.env)");
  }
  const text = readFileSync(envFile, "utf8");
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const match = line.match(/^(?:export\s+)?CURSOR_API_KEY\s*=\s*(.*)$/);
    if (!match) continue;
    let value = match[1].trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (value) {
      process.env.CURSOR_API_KEY = value;
      return value;
    }
  }
  throw new Error("CLOUD_BLOCKED: CURSOR_API_KEY missing (source ~/.config/cursor/agent.env)");
}

export function safeError(err: unknown): string {
  let message = err instanceof Error ? err.message : String(err);
  const key = process.env.CURSOR_API_KEY;
  if (key && message.includes(key)) {
    message = message.split(key).join("[redacted]");
  }
  return message.replace(/\s+/g, " ").trim();
}

export function die(message: string, code = 1): never {
  console.error(message);
  process.exit(code);
}

export function mapAgentStatus(status: SDKAgentInfo["status"] | string | undefined): string {
  switch (status) {
    case "running":
      return "ACTIVE";
    case "finished":
      return "FINISHED";
    case "error":
      return "ERROR";
    case undefined:
    case "":
      // SDK often omits status on cloud agents; REST used ACTIVE.
      return "ACTIVE";
    default:
      return String(status).toUpperCase();
  }
}

export function mapRunStatus(status: string | undefined): string {
  if (!status) return "none";
  return status.toUpperCase();
}

export function isoFromEpoch(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value) || value <= 0) return "";
  const ms = value < 1e12 ? value * 1000 : value;
  try {
    return new Date(ms).toISOString();
  } catch {
    return "";
  }
}

export type BoundRepo = { url: string; startingRef?: string };

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

/** Cursor run git.branches[].repoUrl omits the scheme; agent repos[].url keeps https://. */
export function normalizeRepoUrl(url: string): string {
  const trimmed = url.trim();
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed.replace(/^\/+/, "")}`;
}

/** Bound Extra High repos from GET /v1/agents (full record, not the list row). */
export function boundRepos(agent: unknown): BoundRepo[] {
  const rec = asRecord(agent);
  const raw = rec?.repos;
  if (!Array.isArray(raw)) return [];
  const out: BoundRepo[] = [];
  for (const item of raw) {
    const row = asRecord(item);
    const url = typeof row?.url === "string" ? row.url.trim() : "";
    if (!url) continue;
    const startingRef =
      typeof row.startingRef === "string" && row.startingRef.trim()
        ? row.startingRef.trim()
        : undefined;
    out.push(startingRef ? { url, startingRef } : { url });
  }
  return out;
}

/**
 * Directors need the bound git remote to tell game vs studio targeting.
 * Prefer agent.repos[0].url; fall back to the latest run's git.branches[].repoUrl.
 */
export function boundRepoUrl(agent: unknown, run?: unknown): string | null {
  const fromAgent = boundRepos(agent)[0]?.url;
  if (fromAgent) return normalizeRepoUrl(fromAgent);
  const git = asRecord(asRecord(run)?.git);
  const branches = git?.branches;
  if (!Array.isArray(branches)) return null;
  for (const item of branches) {
    const row = asRecord(item);
    const repoUrl = typeof row?.repoUrl === "string" ? row.repoUrl.trim() : "";
    if (repoUrl) return normalizeRepoUrl(repoUrl);
  }
  return null;
}

export function pickGit(run: Run | undefined): { prUrl: string; branch: string } {
  const branches = run?.git?.branches ?? [];
  const withPr = branches.find((b) => b.prUrl);
  const withBranch = branches.find((b) => b.branch);
  return {
    prUrl: withPr?.prUrl || "",
    branch: withBranch?.branch || withPr?.branch || "",
  };
}

export function runErrorPayload(err: RunError | undefined): {
  message: string;
  code?: string;
} | null {
  if (!err?.message) return null;
  return err.code ? { message: err.message, code: err.code } : { message: err.message };
}

export function requireArg(value: string | undefined, usage: string): string {
  if (!value) die(usage, 2);
  return value;
}

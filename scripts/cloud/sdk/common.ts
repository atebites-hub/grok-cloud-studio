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
export const EXTRA_HIGH_MODEL_ID = "grok-4.6";
const EXTRA_HIGH_MODEL_IDS = new Set(["grok-4.6", "cursor-grok-4.6-xhigh"]);

function envFirst(...names: string[]): string {
  for (const name of names) {
    const value = (process.env[name] || "").trim();
    if (value) return value;
  }
  return "";
}

export function requirePinnedCloudModelEnv(): void {
  const raw = (process.env.CURSOR_CLOUD_MODEL || "").trim();
  if (!raw) return;
  if (raw !== EXTRA_HIGH_MODEL_ID) {
    throw new Error(`CLOUD_BLOCKED: CURSOR_CLOUD_MODEL=${raw} is not grok-4.6`);
  }
}

export function extraHighModel(): ModelSelection {
  return {
    id: EXTRA_HIGH_MODEL_ID,
    params: [
      { id: "effort", value: "xhigh" },
      { id: "fast", value: "false" },
    ],
  };
}

export type PinnedSender = {
  send: (message: string, options: { model: ModelSelection }) => Promise<Run>;
};

/**
 * Pin Extra High on the first run and every follow-up. Unpinned send() lets
 * Auto pick Claude/Gemini. @cursor/sdk send is
 * `send(message, options?: SendOptions)` and is compiled as `send(e)` that
 * forwards `arguments` into `(e, t={})`, so Function.length is 1 even though
 * the model option is accepted. Always pass extraHighModel(); never omit it.
 */
export async function sendPinned(agent: PinnedSender, prompt: string): Promise<Run> {
  if (typeof agent.send !== "function") {
    throw new Error("CLOUD_BLOCKED: agent.send missing; refusing unpinned run");
  }
  requirePinnedCloudModelEnv();
  const model = extraHighModel();
  if (model.id !== EXTRA_HIGH_MODEL_ID) {
    throw new Error("CLOUD_BLOCKED: extraHighModel pin missing");
  }
  return agent.send(prompt, { model });
}

export function modelIdFrom(value: unknown): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "object" && "id" in value) {
    const id = (value as { id?: unknown }).id;
    if (typeof id === "string") return id.trim();
  }
  return "";
}

export function isExtraHighModelId(id: string | undefined): boolean {
  const text = (id || "").trim();
  if (!text) return true;
  return EXTRA_HIGH_MODEL_IDS.has(text);
}

/** Non-null when the API exposed a model that is not grok-4.6 Extra High. */
export function createModelRejected(...models: unknown[]): string | null {
  for (const model of models) {
    const id = modelIdFrom(model);
    if (id && !isExtraHighModelId(id)) return id;
  }
  return null;
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

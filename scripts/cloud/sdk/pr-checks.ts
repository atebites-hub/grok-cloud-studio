/**
 * GitHub check-run snapshot for Extra High waiter pings (LIV-94).
 *
 * Empty GitHub checks are not ship-gate evidence. MERGEABLE
 * (mergeable_state=clean) is not a substitute. GCS #92 SUCCESS is the
 * required pull_request pytest + secret_scan workflow.
 *
 * One-shot GET. Do not reuse Extra High waiter 429 backoff (GCS #35).
 * Never print GH_TOKEN / GITHUB_TOKEN / CURSOR_API_KEY.
 */

export type GitHubPullRef = { owner: string; repo: string; number: number };

export type ShipGateSnapshot = {
  emptyChecks: boolean;
  checkRuns: number;
  mergeableState: string | null;
  shipGateOk: boolean;
};

const GITHUB_PULL_RE =
  /^https?:\/\/(?:www\.)?github\.com\/([^/]+)\/([^/]+)\/pulls?\/(\d+)(?:[/?#].*)?$/i;

export function parseGitHubPullUrl(prUrl: string | null | undefined): GitHubPullRef | null {
  if (!prUrl) return null;
  const match = prUrl.trim().match(GITHUB_PULL_RE);
  if (!match) return null;
  return { owner: match[1], repo: match[2], number: Number(match[3]) };
}

function githubApiBase(): string {
  return (process.env.GITHUB_API_BASE || "https://api.github.com").replace(/\/$/, "");
}

function githubToken(): string {
  return (process.env.GH_TOKEN || process.env.GITHUB_TOKEN || "").trim();
}

function githubHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/vnd.github+json",
    "User-Agent": "grok-cloud-studio-waiter",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  const token = githubToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function githubGet(path: string): Promise<Record<string, unknown> | null> {
  const url = `${githubApiBase()}${path}`;
  try {
    const res = await fetch(url, { headers: githubHeaders(), signal: AbortSignal.timeout(8000) });
    if (!res.ok) return null;
    const body = (await res.json()) as unknown;
    if (!body || typeof body !== "object" || Array.isArray(body)) return null;
    return body as Record<string, unknown>;
  } catch {
    return null;
  }
}

function isShipGateCheck(run: Record<string, unknown>): boolean {
  const name = String(run.name || "").toLowerCase();
  const conclusion = String(run.conclusion || "").toLowerCase();
  if (conclusion !== "success") return false;
  return name.includes("pytest") && name.includes("secret_scan");
}

export async function githubPrShipGate(
  prUrl: string | null | undefined,
): Promise<ShipGateSnapshot | null> {
  const ref = parseGitHubPullUrl(prUrl);
  if (!ref) return null;
  const pull = await githubGet(`/repos/${ref.owner}/${ref.repo}/pulls/${ref.number}`);
  if (!pull) return null;
  const head = pull.head && typeof pull.head === "object" ? (pull.head as Record<string, unknown>) : {};
  const headSha = typeof head.sha === "string" && head.sha ? head.sha : "";
  const mergeableState = typeof pull.mergeable_state === "string" ? pull.mergeable_state : null;
  let checkRuns: Record<string, unknown>[] = [];
  let statusesTotal = 0;
  if (headSha) {
    const checks = await githubGet(`/repos/${ref.owner}/${ref.repo}/commits/${headSha}/check-runs`);
    const raw = checks?.check_runs;
    if (Array.isArray(raw)) {
      checkRuns = raw.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object");
    }
    const combined = await githubGet(`/repos/${ref.owner}/${ref.repo}/commits/${headSha}/status`);
    const total = combined?.total_count;
    if (typeof total === "number") statusesTotal = total;
    else if (typeof total === "string") statusesTotal = Number(total) || 0;
  }
  const emptyChecks = checkRuns.length === 0 && statusesTotal === 0;
  const shipGateOk = checkRuns.some(isShipGateCheck);
  return {
    emptyChecks,
    checkRuns: checkRuns.length,
    mergeableState,
    shipGateOk: emptyChecks ? false : shipGateOk,
  };
}

const EMPTY_GITHUB_PR: ShipGateSnapshot = {
  emptyChecks: true,
  checkRuns: 0,
  mergeableState: null,
  shipGateOk: false,
};

/** Fail closed for GitHub pulls: missing lookup is empty checks, not a pass. */
export async function attachShipGate<
  T extends {
    prUrl?: string | null;
    emptyChecks?: boolean;
    checkRuns?: number;
    shipGateOk?: boolean;
  },
>(payload: T): Promise<T & Partial<ShipGateSnapshot>> {
  if (
    payload.shipGateOk !== undefined ||
    payload.emptyChecks !== undefined ||
    payload.checkRuns !== undefined
  ) {
    return payload;
  }
  const snap = await githubPrShipGate(payload.prUrl);
  if (snap !== null) {
    return { ...payload, ...snap };
  }
  if (parseGitHubPullUrl(payload.prUrl) !== null) {
    return { ...payload, ...EMPTY_GITHUB_PR };
  }
  return payload;
}

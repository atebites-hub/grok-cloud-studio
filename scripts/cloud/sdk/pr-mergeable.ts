/**
 * GitHub mergeable detection for Extra High waiter pings.
 *
 * REST mergeable_state=dirty maps to GraphQL mergeable=CONFLICTING
 * (sibling product PRs #301/#304). QA HOLD squash on CONFLICTING.
 *
 * One-shot GET. Do not reuse Extra High waiter 429 backoff (GCS #35).
 * Do not remint draft-flag GCS #52.
 * Never print GH_TOKEN / GITHUB_TOKEN / CURSOR_API_KEY.
 */

export type GitHubPullRef = { owner: string; repo: string; number: number };
export type GitHubMergeable = "CONFLICTING" | "MERGEABLE" | "UNKNOWN";

const GITHUB_PULL_RE =
  /^https?:\/\/(?:www\.)?github\.com\/([^/]+)\/([^/]+)\/pulls?\/(\d+)(?:[/?#].*)?$/i;

const CONFLICTING_STATES = new Set(["dirty", "conflicting"]);
const MERGEABLE_STATES = new Set([
  "clean",
  "unstable",
  "blocked",
  "behind",
  "has_hooks",
  "draft",
]);

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

export function mapGitHubMergeable(body: {
  mergeable?: unknown;
  mergeable_state?: unknown;
}): GitHubMergeable | null {
  const raw = body.mergeable;
  if (typeof raw === "string") {
    const token = raw.trim().toUpperCase();
    if (token === "CONFLICTING" || token === "MERGEABLE" || token === "UNKNOWN") {
      return token;
    }
  }
  const state = String(body.mergeable_state || "").trim().toLowerCase();
  if (CONFLICTING_STATES.has(state)) return "CONFLICTING";
  if (raw === false) return "CONFLICTING";
  if (MERGEABLE_STATES.has(state) || raw === true) return "MERGEABLE";
  return "UNKNOWN";
}

export async function githubPrMergeable(
  prUrl: string | null | undefined,
): Promise<GitHubMergeable | null> {
  const ref = parseGitHubPullUrl(prUrl);
  if (!ref) return null;
  const url = `${githubApiBase()}/repos/${ref.owner}/${ref.repo}/pulls/${ref.number}`;
  const headers: Record<string, string> = {
    Accept: "application/vnd.github+json",
    "User-Agent": "grok-cloud-studio-waiter",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  const token = githubToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  try {
    const res = await fetch(url, { headers, signal: AbortSignal.timeout(8000) });
    if (!res.ok) return null;
    const body = (await res.json()) as {
      mergeable?: unknown;
      mergeable_state?: unknown;
    };
    return mapGitHubMergeable(body);
  } catch {
    return null;
  }
}

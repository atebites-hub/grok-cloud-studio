/**
 * GitHub draft detection for Extra High waiter pings.
 *
 * One-shot GET. Do not reuse Extra High waiter 429 backoff (GCS #35).
 * Never print GH_TOKEN / GITHUB_TOKEN / CURSOR_API_KEY.
 */

export type GitHubPullRef = { owner: string; repo: string; number: number };

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

export async function githubPrIsDraft(prUrl: string | null | undefined): Promise<boolean | null> {
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
    const body = (await res.json()) as { draft?: unknown };
    if (body.draft === true) return true;
    if (body.draft === false) return false;
    return null;
  } catch {
    return null;
  }
}

import { Agent, type Run } from "@cursor/sdk";
import {
  agentUrl,
  die,
  isoFromEpoch,
  loadApiKey,
  mapAgentStatus,
  mapRunStatus,
  safeError,
} from "./common.ts";

function repoKey(value: string): string {
  let text = value.trim();
  if (!text) return "";
  const ssh = "git@github.com:";
  if (text.toLowerCase().startsWith(ssh)) {
    text = text.slice(ssh.length);
  }
  text = text.replace(/^https?:\/\//i, "");
  text = text.replace(/^github\.com\//i, "");
  text = text.replace(/\/+$/, "");
  if (text.toLowerCase().endsWith(".git")) {
    text = text.slice(0, -4);
  }
  return text.toLowerCase();
}

function parseArgs(argv: string[]): { limit: number; repo: string } {
  let limit = 20;
  let repo = "";
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--limit") {
      const next = argv[i + 1];
      if (!next || !/^\d+$/.test(next)) {
        die("usage: list.ts [--limit N] [--repo org/name]", 2);
      }
      limit = Number(next);
      i += 1;
      continue;
    }
    if (arg.startsWith("--limit=")) {
      const raw = arg.slice("--limit=".length);
      if (!/^\d+$/.test(raw)) {
        die("usage: list.ts [--limit N] [--repo org/name]", 2);
      }
      limit = Number(raw);
      continue;
    }
    if (arg === "--repo") {
      const next = argv[i + 1];
      if (!next || next.startsWith("--")) {
        die("usage: list.ts [--limit N] [--repo org/name]", 2);
      }
      repo = next;
      i += 1;
      continue;
    }
    if (arg.startsWith("--repo=")) {
      repo = arg.slice("--repo=".length);
      continue;
    }
    if (/^\d+$/.test(arg)) {
      limit = Number(arg);
      continue;
    }
    die("usage: list.ts [--limit N] [--repo org/name]", 2);
  }
  return { limit, repo };
}

function urlsFromRepos(repos: unknown): string[] {
  if (!Array.isArray(repos)) return [];
  const out: string[] = [];
  for (const entry of repos) {
    if (typeof entry === "string" && entry.trim()) {
      out.push(entry.trim());
    } else if (entry && typeof entry === "object" && "url" in entry) {
      const url = (entry as { url?: unknown }).url;
      if (typeof url === "string" && url.trim()) out.push(url.trim());
    }
  }
  return out;
}

function urlsFromRun(run: Run | undefined): string[] {
  const branches = run?.git?.branches ?? [];
  const out: string[] = [];
  for (const branch of branches) {
    const rec = branch as { repoUrl?: string; url?: string };
    const found = (rec.repoUrl || rec.url || "").trim();
    if (found) out.push(found);
  }
  return out;
}

function matchesRepo(urls: string[], wanted: string): boolean {
  const key = repoKey(wanted);
  if (!key) return true;
  if (!urls.length) return false;
  return urls.some((url) => repoKey(url) === key);
}

async function latestRunMeta(
  agentId: string,
  apiKey: string,
): Promise<{ runStatus: string; runId: string; run: Run | undefined }> {
  try {
    const listed = await Agent.listRuns(agentId, { runtime: "cloud", apiKey, limit: 20 });
    if (!listed.items.length) {
      return { runStatus: "none", runId: "", run: undefined };
    }
    const run = listed.items
      .slice()
      .sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0))[0];
    return { runStatus: mapRunStatus(run?.status), runId: run?.id || "", run };
  } catch {
    return { runStatus: "none", runId: "", run: undefined };
  }
}

async function boundRepoUrls(
  agent: { agentId?: string; repos?: unknown },
  apiKey: string,
  wanted: string,
): Promise<string[]> {
  let urls = urlsFromRepos(agent.repos);
  if (wanted && !urls.length && agent.agentId) {
    try {
      const info = await Agent.get(agent.agentId, { apiKey });
      urls = urlsFromRepos("repos" in info ? info.repos : undefined);
    } catch {
      urls = [];
    }
  }
  return urls;
}

async function main(): Promise<void> {
  const { limit, repo } = parseArgs(process.argv.slice(2));
  const apiKey = loadApiKey();
  try {
    const { items } = await Agent.list({ runtime: "cloud", apiKey, limit });
    if (!items.length) {
      process.stdout.write("CLOUD_LIST empty\n");
      return;
    }
    let printed = 0;
    for (const agent of items) {
      const id = agent.agentId || "";
      const status = mapAgentStatus(agent.status);
      const name = agent.name || "";
      const url = agentUrl(id);
      const updated = isoFromEpoch(agent.lastModified);
      const { runStatus, runId, run } = id
        ? await latestRunMeta(id, apiKey)
        : { runStatus: "none", runId: "", run: undefined };
      const urls = [
        ...(await boundRepoUrls(agent, apiKey, repo)),
        ...urlsFromRun(run),
      ];
      if (repo && !matchesRepo(urls, repo)) {
        continue;
      }
      const repoUrl = urls[0] || "";
      const repoTok = repoUrl ? ` repo=${repoUrl}` : "";
      process.stdout.write(
        `id=${id} status=${status} runStatus=${runStatus} name=${name} url=${url} latestRunId=${runId} updated=${updated}${repoTok}\n`,
      );
      printed += 1;
    }
    if (!printed && repo) {
      process.stdout.write("CLOUD_LIST empty\n");
    }
  } catch (err) {
    console.error(`CLOUD_LIST_ERR ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

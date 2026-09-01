import { Agent, type Run } from "@cursor/sdk";
import {
  agentUrl,
  boundRepoUrl,
  boundRepos,
  loadApiKey,
  mapAgentStatus,
  mapRunStatus,
  pickGit,
  runErrorPayload,
  type BoundRepo,
} from "./common.ts";

export type DirectorResult = {
  agentId: string;
  name: string;
  url: string;
  runId: string | null;
  status: string | null;
  agentStatus: string | null;
  runStatus: string | null;
  prUrl: string | null;
  branches: string[];
  branch: string | null;
  summary: string | null;
  result: string | null;
  error: { message: string; code?: string } | null;
  repoUrl: string | null;
  repos: BoundRepo[];
};

async function latestRun(
  agentId: string,
  apiKey: string,
  runId?: string,
): Promise<Run | undefined> {
  if (runId) {
    return Agent.getRun(runId, { runtime: "cloud", agentId, apiKey });
  }
  const listed = await Agent.listRuns(agentId, { runtime: "cloud", apiKey, limit: 20 });
  if (!listed.items.length) return undefined;
  return listed.items
    .slice()
    .sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0))[0];
}

export async function collectResult(agentId: string, runId?: string): Promise<DirectorResult> {
  const apiKey = loadApiKey();
  const info = await Agent.get(agentId, { apiKey });
  const run = await latestRun(agentId, apiKey, runId);
  const git = pickGit(run);
  const branches = (run?.git?.branches ?? [])
    .map((b) => b.branch)
    .filter((b): b is string => Boolean(b));
  const runStatus = run ? mapRunStatus(run.status) : null;
  return {
    agentId: info.agentId || agentId,
    name: info.name || "",
    url: agentUrl(info.agentId || agentId),
    runId: run?.id ?? null,
    status: runStatus,
    agentStatus: mapAgentStatus(info.status),
    runStatus,
    prUrl: git.prUrl || null,
    branches,
    branch: git.branch || null,
    summary: info.summary || null,
    result: run?.result ?? null,
    error: runErrorPayload(run?.error),
    repoUrl: boundRepoUrl(info, run),
    repos: boundRepos(info),
  };
}

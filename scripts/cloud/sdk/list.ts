import { Agent, type Run } from "@cursor/sdk";
import {
  agentUrl,
  die,
  loadApiKey,
  mapAgentStatus,
  mapRunStatus,
  pickGit,
  safeError,
} from "./common.ts";

async function latestRun(agentId: string, apiKey: string): Promise<Run | undefined> {
  try {
    const listed = await Agent.listRuns(agentId, { runtime: "cloud", apiKey, limit: 20 });
    if (!listed.items.length) return undefined;
    return listed.items
      .slice()
      .sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0))[0];
  } catch {
    return undefined;
  }
}

function compactLine(
  id: string,
  status: string,
  name: string,
  url: string,
  run: Run | undefined,
): string {
  const git = pickGit(run);
  const runStatus = run ? mapRunStatus(run.status) : "none";
  const prUrl = git.prUrl || "none";
  const runId = run?.id || "";
  return `id=${id} status=${status} runStatus=${runStatus} prUrl=${prUrl} name=${name} url=${url} latestRunId=${runId}\n`;
}

async function main(): Promise<void> {
  const rawLimit = process.argv[2] || "20";
  if (!/^\d+$/.test(rawLimit)) {
    die("usage: list.ts [limit=20]", 2);
  }
  const limit = Number(rawLimit);
  const apiKey = loadApiKey();
  try {
    const { items } = await Agent.list({ runtime: "cloud", apiKey, limit });
    if (!items.length) {
      process.stdout.write("CLOUD_LIST empty\n");
      return;
    }
    const lines = await Promise.all(
      items.map(async (agent) => {
        const id = agent.agentId || "";
        const status = mapAgentStatus(agent.status);
        const name = agent.name || "";
        const url = agentUrl(id);
        const run = id ? await latestRun(id, apiKey) : undefined;
        return compactLine(id, status, name, url, run);
      }),
    );
    for (const line of lines) {
      process.stdout.write(line);
    }
  } catch (err) {
    console.error(`CLOUD_LIST_ERR ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

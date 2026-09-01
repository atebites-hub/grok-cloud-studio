import { Agent, type Run } from "@cursor/sdk";
import {
  agentUrl,
  die,
  isoFromEpoch,
  loadApiKey,
  mapAgentStatus,
  mapRunStatus,
  modelIdFrom,
  safeError,
} from "./common.ts";

async function latestRunMeta(
  agentId: string,
  apiKey: string,
): Promise<{ runStatus: string; runId: string; model: string }> {
  try {
    const listed = await Agent.listRuns(agentId, { runtime: "cloud", apiKey, limit: 20 });
    if (!listed.items.length) {
      return { runStatus: "none", runId: "", model: "none" };
    }
    const run: Run | undefined = listed.items
      .slice()
      .sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0))[0];
    const model = modelIdFrom(run?.model) || "none";
    return { runStatus: mapRunStatus(run?.status), runId: run?.id || "", model };
  } catch {
    return { runStatus: "none", runId: "", model: "none" };
  }
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
    for (const agent of items) {
      const id = agent.agentId || "";
      const status = mapAgentStatus(agent.status);
      const name = agent.name || "";
      const url = agentUrl(id);
      const updated = isoFromEpoch(agent.lastModified);
      const { runStatus, runId, model } = id
        ? await latestRunMeta(id, apiKey)
        : { runStatus: "none", runId: "", model: "none" };
      const repo =
        "repos" in agent && Array.isArray(agent.repos) && agent.repos[0]
          ? String(agent.repos[0])
          : "";
      const repoTok = repo ? ` repo=${repo}` : "";
      process.stdout.write(
        `id=${id} status=${status} runStatus=${runStatus} model=${model} name=${name} url=${url} latestRunId=${runId} updated=${updated}${repoTok}\n`,
      );
    }
  } catch (err) {
    console.error(`CLOUD_LIST_ERR ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

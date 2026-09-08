import { Agent } from "@cursor/sdk";
import {
  agentUrl,
  die,
  isoFromEpoch,
  loadApiKey,
  mapAgentStatus,
  mapRunStatus,
  safeError,
} from "./common.ts";
import { API_PAGE_MAX, listAllCloudAgents } from "./list_catalog.ts";

async function latestRunMeta(
  agentId: string,
  apiKey: string,
): Promise<{ runStatus: string; runId: string }> {
  try {
    const listed = await Agent.listRuns(agentId, { runtime: "cloud", apiKey, limit: 20 });
    if (!listed.items.length) {
      return { runStatus: "none", runId: "" };
    }
    const run = listed.items
      .slice()
      .sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0))[0];
    return { runStatus: mapRunStatus(run?.status), runId: run?.id || "" };
  } catch {
    return { runStatus: "none", runId: "" };
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
    const catalog = await listAllCloudAgents({
      apiKey,
      pageSize: Math.min(Math.max(limit, 1), API_PAGE_MAX),
      maxItems: limit,
    });
    const { items } = catalog;
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
        const updated = isoFromEpoch(agent.lastModified);
        const { runStatus, runId } = id
          ? await latestRunMeta(id, apiKey)
          : { runStatus: "none", runId: "" };
        return (
          `id=${id} status=${status} runStatus=${runStatus} name=${name} ` +
          `url=${url} latestRunId=${runId} updated=${updated}\n`
        );
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

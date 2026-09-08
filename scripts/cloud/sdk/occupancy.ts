import { Agent } from "@cursor/sdk";
import { loadApiKey, mapAgentStatus, mapRunStatus, safeError } from "./common.ts";
import { CatalogError, listAllCloudAgents } from "./list_catalog.ts";

type OccupancySummary = {
  running: number;
  leftoverActive: number;
  creating: number;
  listed: number;
  pages: number;
};

function classifyRow(
  agentStatus: string,
  runStatus: string,
): "running" | "creating" | "leftover_active" | "other" {
  const run = mapRunStatus(runStatus);
  if (run === "RUNNING") return "running";
  if (run === "CREATING") return "creating";
  const membership = (agentStatus || "").trim().toUpperCase();
  if (membership === "ACTIVE" || membership === "IDLE" || membership === "") {
    return "leftover_active";
  }
  return "other";
}

function formatOccupancyLine(summary: OccupancySummary): string {
  return (
    `CLOUD_OCCUPANCY running=${summary.running} leftover_active=${summary.leftoverActive} ` +
    `creating=${summary.creating} listed=${summary.listed} pages=${summary.pages}`
  );
}

async function latestRunStatus(agentId: string, apiKey: string): Promise<string> {
  const listed = await Agent.listRuns(agentId, { runtime: "cloud", apiKey, limit: 20 });
  if (!listed.items.length) return "none";
  const run = listed.items.slice().sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0))[0];
  return mapRunStatus(run?.status);
}

async function main(): Promise<void> {
  const apiKey = loadApiKey();
  const botId = (process.env.GCS_BOT_AGENT_ID || "").trim();
  try {
    const catalog = await listAllCloudAgents({ apiKey });
    let running = 0;
    let leftoverActive = 0;
    let creating = 0;
    let listed = 0;
    for (const agent of catalog.items) {
      const id = agent.agentId || "";
      if (!id) continue;
      if (botId && id === botId) continue;
      listed += 1;
      const runStatus = await latestRunStatus(id, apiKey);
      const kind = classifyRow(mapAgentStatus(agent.status), runStatus);
      if (kind === "running") running += 1;
      else if (kind === "creating") creating += 1;
      else if (kind === "leftover_active") leftoverActive += 1;
    }
    const summary: OccupancySummary = {
      running,
      leftoverActive,
      creating,
      listed,
      pages: catalog.pages,
    };
    process.stdout.write(`${formatOccupancyLine(summary)}\n`);
  } catch (err) {
    const reason = err instanceof CatalogError ? err.reason : "err";
    console.error(`CLOUD_OCCUPANCY_ERR reason=${reason} ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

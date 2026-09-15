import { Agent, type Run, type SDKAgentInfo } from "@cursor/sdk";
import {
  boundRepoUrl,
  loadApiKey,
  mapAgentStatus,
  mapRunStatus,
  safeError,
} from "./common.ts";
import { CatalogError, listAllCloudAgents } from "./list_catalog.ts";

type OccupancySummary = {
  running: number;
  leftoverActive: number;
  creating: number;
  listed: number;
  pages: number;
  palemon: number;
  gcs: number;
  cap: number;
  palemonMust: number;
  gcsMust: number;
};

type FloorKind = "palemon" | "gcs" | "other";

const DEFAULT_FLOOR = 8;
const STUDIO_REPO_NAME = "grok-cloud-studio";
const GAME_REPO_NAME = "pale" + "mon";

function floorCap(): number {
  const raw = (process.env.GCS_CLOUD_MIN_RUNNING || "").trim();
  if (!raw) return DEFAULT_FLOOR;
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : DEFAULT_FLOOR;
}

function floorKind(url: string): FloorKind {
  const text = url.trim().toLowerCase().replace(/\.git$/i, "").replace(/\/+$/, "");
  const name = text.split("/").pop() || "";
  if (name === STUDIO_REPO_NAME) return "gcs";
  if (name === GAME_REPO_NAME) return "palemon";
  return "other";
}

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
    `creating=${summary.creating} listed=${summary.listed} pages=${summary.pages} ` +
    `palemon=${summary.palemon} gcs=${summary.gcs} cap=${summary.cap} ` +
    `palemon_must=${summary.palemonMust} gcs_must=${summary.gcsMust}`
  );
}

async function latestOccupancy(
  agent: SDKAgentInfo,
  apiKey: string,
): Promise<{ runStatus: string; floor: FloorKind }> {
  const id = agent.agentId || "";
  if (!id) return { runStatus: "none", floor: "other" };
  const listed = await Agent.listRuns(id, { runtime: "cloud", apiKey, limit: 20 });
  if (!listed.items.length) {
    return { runStatus: "none", floor: floorKind(boundRepoUrl(agent) || "") };
  }
  const run = listed.items
    .slice()
    .sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0))[0] as Run | undefined;
  const url = boundRepoUrl(agent, run) || "";
  return { runStatus: mapRunStatus(run?.status), floor: floorKind(url) };
}

async function main(): Promise<void> {
  const apiKey = loadApiKey();
  const botId = (process.env.GCS_BOT_AGENT_ID || "").trim();
  const cap = floorCap();
  try {
    const catalog = await listAllCloudAgents({ apiKey });
    let running = 0;
    let leftoverActive = 0;
    let creating = 0;
    let listed = 0;
    let palemon = 0;
    let gcs = 0;
    for (const agent of catalog.items) {
      const id = agent.agentId || "";
      if (!id) continue;
      if (botId && id === botId) continue;
      listed += 1;
      const { runStatus, floor } = await latestOccupancy(agent, apiKey);
      const kind = classifyRow(mapAgentStatus(agent.status), runStatus);
      if (kind === "running" || kind === "creating") {
        running += 1;
        if (kind === "creating") creating += 1;
        if (floor === "palemon") palemon += 1;
        else if (floor === "gcs") gcs += 1;
      } else if (kind === "leftover_active") {
        leftoverActive += 1;
      }
    }
    const summary: OccupancySummary = {
      running,
      leftoverActive,
      creating,
      listed,
      pages: catalog.pages,
      palemon,
      gcs,
      cap,
      palemonMust: palemon < cap ? 1 : 0,
      gcsMust: gcs < cap ? 1 : 0,
    };
    process.stdout.write(`${formatOccupancyLine(summary)}\n`);
  } catch (err) {
    const reason = err instanceof CatalogError ? err.reason : "err";
    console.error(`CLOUD_OCCUPANCY_ERR reason=${reason} ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

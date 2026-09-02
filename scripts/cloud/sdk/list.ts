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

const OCCUPANCY = new Set(["RUNNING", "CREATING"]);

function isOccupancy(runStatus: string): boolean {
  return OCCUPANCY.has(runStatus);
}

function parseArgs(argv: string[]): { limit: number; occupancy: boolean } {
  let occupancy = false;
  let limit = 20;
  let sawLimit = false;
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--occupancy") {
      occupancy = true;
      continue;
    }
    if (arg === "--limit") {
      const next = argv[i + 1];
      if (!next || !/^\d+$/.test(next)) {
        die("usage: list.ts [--occupancy] [--limit N] [N]", 2);
      }
      limit = Number(next);
      sawLimit = true;
      i += 1;
      continue;
    }
    if (arg.startsWith("--limit=")) {
      const raw = arg.slice("--limit=".length);
      if (!/^\d+$/.test(raw)) {
        die("usage: list.ts [--occupancy] [--limit N] [N]", 2);
      }
      limit = Number(raw);
      sawLimit = true;
      continue;
    }
    if (/^\d+$/.test(arg) && !sawLimit) {
      limit = Number(arg);
      sawLimit = true;
      continue;
    }
    die("usage: list.ts [--occupancy] [--limit N] [N]", 2);
  }
  return { limit, occupancy };
}

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

function writeOccupancy(lines: string[]): void {
  process.stdout.write(`CLOUD_OCCUPANCY n=${lines.length}\n`);
  if (!lines.length) {
    process.stdout.write("CLOUD_LIST empty\n");
    return;
  }
  for (const line of lines) {
    process.stdout.write(line.endsWith("\n") ? line : `${line}\n`);
  }
}

async function main(): Promise<void> {
  const { limit, occupancy } = parseArgs(process.argv.slice(2));
  const apiKey = loadApiKey();
  try {
    const { items } = await Agent.list({ runtime: "cloud", apiKey, limit });
    if (!items.length) {
      if (occupancy) {
        writeOccupancy([]);
        return;
      }
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
    if (occupancy) {
      const kept = lines.filter((line) => {
        const match = /(?:^|\s)runStatus=(\S+)/.exec(line);
        return match ? isOccupancy(match[1]) : false;
      });
      writeOccupancy(kept);
      return;
    }
    for (const line of lines) {
      process.stdout.write(line);
    }
  } catch (err) {
    console.error(`CLOUD_LIST_ERR ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

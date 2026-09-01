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

type ListRow = {
  id: string;
  status: string;
  runStatus: string;
  name: string;
  url: string;
  runId: string;
  updated: string;
};

function parseListArgs(argv: string[]): { limit: number; runningOnly: boolean } {
  let runningOnly = false;
  let rawLimit = "20";
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--running") {
      runningOnly = true;
      continue;
    }
    if (arg === "--limit") {
      const next = argv[i + 1];
      if (!next || !/^\d+$/.test(next)) {
        die("usage: list.ts [--running] [--limit N]", 2);
      }
      rawLimit = next;
      i += 1;
      continue;
    }
    if (arg.startsWith("--limit=")) {
      rawLimit = arg.slice("--limit=".length);
      continue;
    }
    if (/^\d+$/.test(arg)) {
      rawLimit = arg;
      continue;
    }
    die("usage: list.ts [--running] [--limit N]", 2);
  }
  if (!/^\d+$/.test(rawLimit)) {
    die("usage: list.ts [--running] [--limit N]", 2);
  }
  return { limit: Number(rawLimit), runningOnly };
}

function formatListRow(row: ListRow): string {
  return (
    `id=${row.id} status=${row.status} runStatus=${row.runStatus} name=${row.name} ` +
    `url=${row.url} latestRunId=${row.runId} updated=${row.updated}\n`
  );
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

async function main(): Promise<void> {
  const { limit, runningOnly } = parseListArgs(process.argv.slice(2));
  const apiKey = loadApiKey();
  try {
    const { items } = await Agent.list({ runtime: "cloud", apiKey, limit });
    if (!items.length) {
      process.stdout.write("CLOUD_LIST empty\n");
      return;
    }
    const rows = await Promise.all(
      items.map(async (agent): Promise<ListRow> => {
        const id = agent.agentId || "";
        const status = mapAgentStatus(agent.status);
        const name = agent.name || "";
        const url = agentUrl(id);
        const updated = isoFromEpoch(agent.lastModified);
        const { runStatus, runId } = id
          ? await latestRunMeta(id, apiKey)
          : { runStatus: "none", runId: "" };
        return { id, status, runStatus, name, url, runId, updated };
      }),
    );
    const kept = runningOnly ? rows.filter((row) => row.runStatus === "RUNNING") : rows;
    if (runningOnly && !kept.length) {
      process.stdout.write("CLOUD_LIST empty\n");
      return;
    }
    for (const row of kept) {
      process.stdout.write(formatListRow(row));
    }
  } catch (err) {
    console.error(`CLOUD_LIST_ERR ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

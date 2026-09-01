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
import {
  OccupancyError,
  mapWithConcurrency,
  occupancyLimits,
  pickLatestRun,
  withTimeout,
} from "./occupancy_lib.ts";

async function latestRunMeta(
  agentId: string,
  apiKey: string,
  timeoutMs: number,
): Promise<{ runStatus: string; runId: string }> {
  const listed = await withTimeout(
    Agent.listRuns(agentId, { runtime: "cloud", apiKey, limit: 20 }),
    timeoutMs,
    "listRuns",
  );
  if (!listed.items.length) {
    return { runStatus: "none", runId: "" };
  }
  const run = pickLatestRun(listed.items);
  return { runStatus: mapRunStatus(run?.status), runId: run?.id || "" };
}

async function main(): Promise<void> {
  const rawLimit = process.argv[2] || "20";
  if (!/^\d+$/.test(rawLimit)) {
    die("usage: list.ts [limit=20]", 2);
  }
  const limit = Number(rawLimit);
  const apiKey = loadApiKey();
  const { concurrency, timeoutMs, deadlineMs } = occupancyLimits();
  const deadline = Date.now() + deadlineMs;
  try {
    const { items } = await withTimeout(
      Agent.list({ runtime: "cloud", apiKey, limit }),
      timeoutMs,
      "Agent.list",
    );
    if (!items.length) {
      process.stdout.write("CLOUD_LIST empty\n");
      return;
    }
    const lines = await mapWithConcurrency(items, concurrency, async (agent) => {
      const remaining = deadline - Date.now();
      if (remaining <= 0) throw new OccupancyError("occupancy deadline", "deadline");
      const id = agent.agentId || "";
      const status = mapAgentStatus(agent.status);
      const name = agent.name || "";
      const url = agentUrl(id);
      const updated = isoFromEpoch(agent.lastModified);
      const { runStatus, runId } = id
        ? await latestRunMeta(id, apiKey, Math.min(timeoutMs, remaining))
        : { runStatus: "none", runId: "" };
      return (
        `id=${id} status=${status} runStatus=${runStatus} name=${name} ` +
        `url=${url} latestRunId=${runId} updated=${updated}\n`
      );
    });
    for (const line of lines) {
      process.stdout.write(line);
    }
  } catch (err) {
    const reason = err instanceof OccupancyError ? err.reason : "err";
    console.error(`CLOUD_LIST_ERR reason=${reason} ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

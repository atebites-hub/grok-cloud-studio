import { Agent } from "@cursor/sdk";
import { loadApiKey, mapAgentStatus, mapRunStatus, safeError } from "./common.ts";
import {
  OccupancyError,
  formatOccupancyLine,
  mapWithConcurrency,
  occupancyLimits,
  pickLatestRun,
  summarizeOccupancy,
  withTimeout,
} from "./occupancy_lib.ts";

async function main(): Promise<void> {
  const rawLimit = process.argv[2] || process.env.CLOUD_OCCUPANCY_LIMIT || "100";
  if (!/^\d+$/.test(rawLimit)) {
    console.error("usage: occupancy.ts [limit=100]");
    process.exit(2);
  }
  const limit = Number(rawLimit);
  const apiKey = loadApiKey();
  const botId = (process.env.GCS_BOT_AGENT_ID || "").trim();
  const { concurrency, timeoutMs, deadlineMs } = occupancyLimits();
  const deadline = Date.now() + deadlineMs;
  try {
    const { items } = await withTimeout(
      Agent.list({ runtime: "cloud", apiKey, limit }),
      timeoutMs,
      "Agent.list",
    );
    const agents = items.filter((agent) => {
      const id = agent.agentId || "";
      if (!id) return false;
      if (botId && id === botId) return false;
      return true;
    });
    const rows = await mapWithConcurrency(agents, concurrency, async (agent) => {
      const remaining = deadline - Date.now();
      if (remaining <= 0) throw new OccupancyError("occupancy deadline", "deadline");
      const listed = await withTimeout(
        Agent.listRuns(agent.agentId, { runtime: "cloud", apiKey, limit: 20 }),
        Math.min(timeoutMs, remaining),
        "listRuns",
      );
      const run = pickLatestRun(listed.items);
      return {
        agentStatus: mapAgentStatus(agent.status),
        runStatus: mapRunStatus(run?.status),
      };
    });
    process.stdout.write(`${formatOccupancyLine(summarizeOccupancy(rows))}\n`);
  } catch (err) {
    const reason = err instanceof OccupancyError ? err.reason : "err";
    console.error(`CLOUD_OCCUPANCY_ERR reason=${reason} ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

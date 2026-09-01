import { Agent } from "@cursor/sdk";
import { collectResult } from "./collect.ts";
import { die, extraHighModel, loadApiKey, mapRunStatus, safeError } from "./common.ts";

function refuseLive(agentId: string, runStatus: string): never {
  process.stdout.write(`CLOUD_FOLLOWUP_ERR id=${agentId} runStatus=${runStatus}\n`);
  console.error(
    `error: refuse live Extra High runStatus=${runStatus}; do not stack a second run`,
  );
  process.exit(1);
}

async function main(): Promise<void> {
  const agentId = process.argv[2] || "";
  const prompt = process.argv[3] || "";
  if (!agentId || !prompt) {
    die('usage: followup.ts <bc-id> "prompt"', 2);
  }
  const botId = (process.env.GCS_BOT_AGENT_ID || "").trim();
  if (botId && agentId === botId) {
    process.stdout.write("CLOUD_FOLLOWUP_ERR\n");
    console.error("error: never Bot CloudAgent (orchestrator/donald is send.sh)");
    process.exit(1);
  }
  const apiKey = loadApiKey();
  let agent: Awaited<ReturnType<typeof Agent.resume>> | undefined;
  try {
    const snapshot = await collectResult(agentId);
    const latest = mapRunStatus(snapshot.runStatus || undefined);
    if (latest === "RUNNING") {
      refuseLive(agentId, latest);
    }
    agent = await Agent.resume(agentId, { apiKey, model: extraHighModel() });
    const run = await agent.send(prompt, { model: extraHighModel() });
    process.stdout.write(
      `CLOUD_FOLLOWUP_OK id=${agentId} run=${run.id} runStatus=${mapRunStatus(run.status)}\n`,
    );
  } catch (err) {
    process.stdout.write("CLOUD_FOLLOWUP_ERR\n");
    console.error(`id=${agentId} ${safeError(err)}`);
    process.exit(1);
  } finally {
    if (agent) {
      await agent[Symbol.asyncDispose]();
    }
  }
}

void main();

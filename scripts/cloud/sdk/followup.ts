import { Agent } from "@cursor/sdk";
import { die, extraHighModel, loadApiKey, mapRunStatus, safeError } from "./common.ts";

async function main(): Promise<void> {
  const agentId = process.argv[2] || "";
  const prompt = process.argv[3] || "";
  if (!agentId || !prompt) {
    die('usage: followup.ts <bc-id> "prompt"', 2);
  }
  const apiKey = loadApiKey();
  let agent: Awaited<ReturnType<typeof Agent.resume>> | undefined;
  try {
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

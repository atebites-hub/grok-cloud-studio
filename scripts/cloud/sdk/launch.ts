import { Agent } from "@cursor/sdk";
import {
  agentUrl,
  cloudCreateOptions,
  die,
  extraHighModel,
  loadApiKey,
  safeError,
  sdkCreateFailExitCode,
} from "./common.ts";

async function main(): Promise<void> {
  const prompt = process.argv[2] || "";
  const name = (process.argv[3] || "").slice(0, 100);
  if (!prompt) {
    die('usage: launch.ts "prompt" [name]', 2);
  }

  const apiKey = loadApiKey();
  let agent: Awaited<ReturnType<typeof Agent.create>> | undefined;
  try {
    try {
      agent = await Agent.create({
        apiKey,
        name: name || undefined,
        model: extraHighModel(),
        cloud: cloudCreateOptions(),
      });
    } catch (err) {
      process.stdout.write("CLOUD_LAUNCH_ERR\n");
      console.error(safeError(err));
      // 75 → REST fallback. Do not fail closed on v1 metadata / unavailable.
      process.exit(sdkCreateFailExitCode(err));
    }
    const run = await agent.send(prompt);
    const url = agentUrl(agent.agentId);
    process.stdout.write(
      `CLOUD_LAUNCH_OK id=${agent.agentId} run=${run.id} url=${url} name=${name}\n`,
    );
  } catch (err) {
    // Create already succeeded; REST fallback would double-create.
    process.stdout.write("CLOUD_LAUNCH_ERR\n");
    console.error(safeError(err));
    process.exit(1);
  } finally {
    if (agent) {
      await agent[Symbol.asyncDispose]();
    }
  }
}

void main();

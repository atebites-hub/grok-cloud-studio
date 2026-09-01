import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
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

function spawnWaiter(agentId: string, runId: string, name: string): void {
  // Always invoke spawn-waiter.sh after CLOUD_LAUNCH_OK so LIV-82 Living Sky
  // stamp runs even when GCS_SPAWN_WAITER=0. The bash script skips the waiter
  // itself. Inherit stdio so LINEAR_STAMP_* is visible. Do not fail create.
  const here = dirname(fileURLToPath(import.meta.url));
  const script = resolve(here, "..", "spawn-waiter.sh");
  spawnSync(
    "bash",
    [script, "--id", agentId, "--run", runId, ...(name ? ["--name", name] : [])],
    {
      stdio: "inherit",
      env: process.env,
    },
  );
}

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
    spawnWaiter(agent.agentId, run.id, name);
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

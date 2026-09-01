import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Agent } from "@cursor/sdk";
import {
  agentUrl,
  cloudCreateOptions,
  die,
  extraHighModel,
  loadApiKey,
  mapRunStatus,
  safeError,
  sdkCreateFailExitCode,
} from "./common.ts";

function spawnWaiter(agentId: string, runId: string, name: string): void {
  const raw = (process.env.GCS_SPAWN_WAITER || process.env.CLOUD_SPAWN_WAITER || "1").trim();
  if (raw === "0" || raw === "false" || raw === "no") return;
  const here = dirname(fileURLToPath(import.meta.url));
  const script = resolve(here, "..", "spawn-waiter.sh");
  const child = spawn(
    "bash",
    [script, "--id", agentId, "--run", runId, ...(name ? ["--name", name] : [])],
    {
      detached: true,
      stdio: "ignore",
      env: process.env,
    },
  );
  child.unref();
}

function refuseLiveNamed(name: string, agentId: string, runStatus: string): never {
  process.stdout.write(`CLOUD_LAUNCH_ERR runStatus=${runStatus}\n`);
  console.error(
    `error: refuse same-name Extra High runStatus=${runStatus} id=${agentId} name=${name}; do not remint a twin`,
  );
  process.exit(1);
}

function nameScanLimit(): number {
  const raw = Number(process.env.CLOUD_NAME_SCAN_LIMIT || "50");
  if (!Number.isFinite(raw) || raw <= 0) return 50;
  return Math.min(Math.floor(raw), 200);
}

/** REFUSE create when a live runStatus=RUNNING agent already has this name. */
async function refuseIfSameNameRunning(apiKey: string, name: string): Promise<void> {
  if (!name) return;
  const { items } = await Agent.list({ runtime: "cloud", apiKey, limit: nameScanLimit() });
  for (const agent of items ?? []) {
    if ((agent.name || "") !== name) continue;
    const agentId = agent.agentId || "";
    if (!agentId) continue;
    const listed = await Agent.listRuns(agentId, { runtime: "cloud", apiKey, limit: 20 });
    const latest = (listed.items ?? [])
      .slice()
      .sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0))[0];
    const runStatus = mapRunStatus(latest?.status);
    if (runStatus === "RUNNING") {
      refuseLiveNamed(name, agentId, runStatus);
    }
  }
}

async function main(): Promise<void> {
  const prompt = process.argv[2] || "";
  const name = (process.argv[3] || "").slice(0, 100);
  if (!prompt) {
    die('usage: launch.ts "prompt" [name]', 2);
  }

  const botId = (process.env.GCS_BOT_AGENT_ID || "").trim();
  if (botId && name && name === botId) {
    process.stdout.write("CLOUD_LAUNCH_ERR\n");
    console.error("error: never Bot CloudAgent (orchestrator/donald is send.sh)");
    process.exit(1);
  }

  const apiKey = loadApiKey();
  if (name) {
    try {
      await refuseIfSameNameRunning(apiKey, name);
    } catch (err) {
      process.stdout.write("CLOUD_LAUNCH_ERR\n");
      console.error(safeError(err));
      process.exit(1);
    }
  }

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

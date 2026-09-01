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

function refuseLiveNameTwin(id: string, name: string, runStatus: string): never {
  process.stdout.write(`CLOUD_LAUNCH_ERR runStatus=${runStatus} id=${id} name=${name}\n`);
  console.error(
    `error: refuse twin remint name=${name} id=${id} runStatus=${runStatus}; leftover ACTIVE+FINISHED does not block`,
  );
  process.exit(1);
}

async function latestRunStatus(agentId: string, apiKey: string): Promise<string> {
  const listed = await Agent.listRuns(agentId, { runtime: "cloud", apiKey, limit: 20 });
  if (!listed.items.length) return "none";
  const run = listed.items.slice().sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0))[0];
  return mapRunStatus(run?.status);
}

/** Refuse create when a live Extra High already has this --name. Never Bot CloudAgent. */
async function refuseIfLiveNameTwin(apiKey: string, name: string): Promise<void> {
  if (!name) return;
  const botId = (process.env.GCS_BOT_AGENT_ID || "").trim();
  const rawLimit = (process.env.CLOUD_LIST_LIMIT || "50").trim();
  const limit = /^\d+$/.test(rawLimit) ? Number(rawLimit) : 50;
  const { items } = await Agent.list({ runtime: "cloud", apiKey, limit });
  for (const agent of items) {
    const id = agent.agentId || "";
    if (botId && id === botId) continue;
    if ((agent.name || "") !== name) continue;
    const runStatus = id ? await latestRunStatus(id, apiKey) : "none";
    if (runStatus === "RUNNING") {
      refuseLiveNameTwin(id, name, runStatus);
    }
  }
}

async function main(): Promise<void> {
  const prompt = process.argv[2] || "";
  const name = (process.argv[3] || "").slice(0, 100);
  if (!prompt) {
    die('usage: launch.ts "prompt" [name]', 2);
  }

  const apiKey = loadApiKey();
  try {
    await refuseIfLiveNameTwin(apiKey, name);
  } catch (err) {
    process.stdout.write("CLOUD_LAUNCH_ERR\n");
    console.error(safeError(err));
    process.exit(1);
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

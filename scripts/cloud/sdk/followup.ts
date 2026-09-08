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

function errorRecord(err: unknown): Record<string, unknown> | null {
  if (err && typeof err === "object") return err as Record<string, unknown>;
  return null;
}

function errorStatus(err: unknown): number {
  const rec = errorRecord(err);
  if (!rec) return 0;
  const raw = rec.status ?? rec.statusCode ?? rec.status_code;
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

function errorCode(err: unknown): string {
  const rec = errorRecord(err);
  if (!rec) return "";
  if (typeof rec.code === "string" && rec.code) return rec.code.toLowerCase();
  const nested = rec.error;
  if (nested && typeof nested === "object") {
    const inner = nested as Record<string, unknown>;
    if (typeof inner.code === "string" && inner.code) return inner.code.toLowerCase();
  }
  return String(nested ?? rec.code ?? "").toLowerCase();
}

/** HTTP 409 / agent_busy is not waiter 429 backoff. Never mint a unique --name Extra High. */
function isAgentBusy(err: unknown): boolean {
  const status = errorStatus(err);
  const code = errorCode(err);
  const msg = safeError(err).toLowerCase();
  if (status === 409) return true;
  if (status === 429) return false;
  if (code === "agent_busy" || code.includes("agent_busy")) return true;
  return msg.includes("agent_busy");
}

function refuseBusy(agentId: string, http: number): never {
  const code = http || 409;
  process.stdout.write(`CLOUD_FOLLOWUP_ERR http=${code} agent_busy=1 id=${agentId}\n`);
  console.error(
    `error: follow-up HTTP ${code} agent_busy; do not launch a second unique --name twin`,
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
    if (isAgentBusy(err)) {
      refuseBusy(agentId, errorStatus(err) || 409);
    }
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

import { collectResult } from "./collect.ts";
import { die, safeError } from "./common.ts";

function compactLine(result: Awaited<ReturnType<typeof collectResult>>): void {
  const latest = result.runId || "";
  process.stdout.write(
    `id=${result.agentId} status=${result.agentStatus || "unknown"} url=${result.url} latestRunId=${latest}\n`,
  );
  process.stdout.write(
    `runStatus=${result.runStatus || "none"} prUrl=${result.prUrl || "none"} branches=${result.branch || "none"}\n`,
  );
  const snip = (result.result || "").replace(/\s+/g, " ").trim().slice(0, 180);
  process.stdout.write(`result=${snip || "none"}\n`);
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const json = args.includes("--json");
  const agentId = args.find((a) => !a.startsWith("--"));
  if (!agentId) {
    die("usage: status.ts <bc-id> [--json]", 2);
  }
  try {
    const payload = await collectResult(agentId);
    if (json) {
      process.stdout.write(`${JSON.stringify(payload)}\n`);
      return;
    }
    compactLine(payload);
  } catch (err) {
    console.error(`CLOUD_STATUS_ERR id=${agentId} ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

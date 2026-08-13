import { collectResult } from "./collect.ts";
import { die, safeError } from "./common.ts";

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  let runId: string | undefined;
  const positional: string[] = [];
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === "--run" || arg === "--run-id") {
      runId = args[i + 1];
      i += 1;
      continue;
    }
    if (arg.startsWith("--run=")) {
      runId = arg.slice("--run=".length);
      continue;
    }
    positional.push(arg);
  }
  const agentId = positional[0];
  if (!agentId) {
    die("usage: result.ts <bc-id> [--run run-id]", 2);
  }
  try {
    const payload = await collectResult(agentId, runId);
    process.stdout.write(`${JSON.stringify(payload)}\n`);
  } catch (err) {
    console.error(`CLOUD_RESULT_ERR id=${agentId} ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

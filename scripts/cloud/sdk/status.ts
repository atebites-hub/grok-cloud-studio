import { collectResult, type DirectorResult } from "./collect.ts";
import { die, safeError } from "./common.ts";

function compactLine(result: DirectorResult): void {
  const latest = result.runId || "";
  process.stdout.write(
    `id=${result.agentId} agentStatus=${result.agentStatus || "unknown"} runStatus=${result.runStatus || "none"} url=${result.url} latestRunId=${latest}\n`,
  );
}

function parseArgs(argv: string[]): { json: boolean; ids: string[] } {
  const ids: string[] = [];
  let json = false;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--json") {
      json = true;
      continue;
    }
    if (arg === "--ids") {
      const next = argv[++i] || "";
      pushIds(ids, next);
      continue;
    }
    if (arg.startsWith("--ids=")) {
      pushIds(ids, arg.slice("--ids=".length));
      continue;
    }
    if (arg.startsWith("-")) {
      die("usage: status.ts <bc-id> [bc-id...] [--ids id,id] [--json]", 2);
    }
    pushIds(ids, arg);
  }
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const id of ids) {
    if (seen.has(id)) continue;
    seen.add(id);
    unique.push(id);
  }
  return { json, ids: unique };
}

function pushIds(ids: string[], raw: string): void {
  for (const part of raw.split(",")) {
    const id = part.trim();
    if (id) ids.push(id);
  }
}

async function main(): Promise<void> {
  const { json, ids } = parseArgs(process.argv.slice(2));
  if (!ids.length) {
    die("usage: status.ts <bc-id> [bc-id...] [--ids id,id] [--json]", 2);
  }
  try {
    const payloads = await Promise.all(ids.map((id) => collectResult(id)));
    if (json) {
      const body = payloads.length === 1 ? payloads[0] : payloads;
      process.stdout.write(`${JSON.stringify(body)}\n`);
      return;
    }
    for (const payload of payloads) {
      compactLine(payload);
    }
  } catch (err) {
    console.error(`CLOUD_STATUS_ERR ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

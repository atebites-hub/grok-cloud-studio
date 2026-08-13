import { Agent } from "@cursor/sdk";
import { agentUrl, die, isoFromEpoch, loadApiKey, mapAgentStatus, safeError } from "./common.ts";

async function main(): Promise<void> {
  const rawLimit = process.argv[2] || "20";
  if (!/^\d+$/.test(rawLimit)) {
    die("usage: list.ts [limit=20]", 2);
  }
  const limit = Number(rawLimit);
  const apiKey = loadApiKey();
  try {
    const { items } = await Agent.list({ runtime: "cloud", apiKey, limit });
    if (!items.length) {
      process.stdout.write("CLOUD_LIST empty\n");
      return;
    }
    for (const agent of items) {
      const id = agent.agentId || "";
      const status = mapAgentStatus(agent.status);
      const name = agent.name || "";
      const url = agentUrl(id);
      const updated = isoFromEpoch(agent.lastModified);
      process.stdout.write(
        `id=${id} status=${status} name=${name} url=${url} updated=${updated}\n`,
      );
    }
  } catch (err) {
    console.error(`CLOUD_LIST_ERR ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

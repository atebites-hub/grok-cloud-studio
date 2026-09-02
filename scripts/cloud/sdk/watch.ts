import { Agent, type Run } from "@cursor/sdk";
import {
  agentUrl,
  die,
  loadApiKey,
  mapAgentStatus,
  mapRunStatus,
  pickGit,
  safeError,
} from "./common.ts";

const TERMINAL = new Set(["FINISHED", "ERROR", "CANCELLED", "EXPIRED"]);

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function latestRun(agentId: string, apiKey: string): Promise<Run | undefined> {
  const listed = await Agent.listRuns(agentId, { runtime: "cloud", apiKey, limit: 20 });
  if (!listed.items.length) return undefined;
  return listed.items
    .slice()
    .sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0))[0];
}

async function main(): Promise<void> {
  const agentId = process.argv[2] || "";
  const timeoutSec = Number(process.argv[3] || "1800");
  let pollSec = Number(process.argv[4] || "30");
  if (!agentId) {
    die("usage: watch.ts <bc-id> [timeout_sec=1800] [poll_sec=30]", 2);
  }
  const directorSeat = (process.env.GCS_DIRECTOR_SEAT || "").trim();
  const allowBlock = (process.env.CLOUD_ALLOW_BLOCK_WAIT || "").trim() === "1";
  if (directorSeat && !allowBlock) {
    console.error(
      `CLOUD_WATCH_REFUSED seat=${directorSeat} use=spawn-waiter/result-cloud-agent.sh override=CLOUD_ALLOW_BLOCK_WAIT=1`,
    );
    process.exit(2);
  }
  if (!Number.isFinite(timeoutSec) || !Number.isFinite(pollSec) || timeoutSec < 0) {
    die("usage: watch.ts <bc-id> [timeout_sec=1800] [poll_sec=30]", 2);
  }
  if (pollSec < 5) pollSec = 5;

  const apiKey = loadApiKey();
  const started = Date.now();
  // 0 = no deadline (matches scripts/cloud/watch.sh CLOUD_WATCH_TIMEOUT_SEC=0).
  const deadline = timeoutSec > 0 ? started + timeoutSec * 1000 : Number.POSITIVE_INFINITY;
  let lastStatus = "unknown";

  try {
    while (Date.now() < deadline) {
      const elapsed = Math.floor((Date.now() - started) / 1000);
      const info = await Agent.get(agentId, { apiKey });
      const run = await latestRun(agentId, apiKey);
      const runStatus = mapRunStatus(run?.status);
      lastStatus = runStatus;
      const ts = new Date().toISOString().slice(11, 19) + "Z";
      process.stdout.write(
        `[${ts}] id=${agentId} agent=${mapAgentStatus(info.status)} run=${run?.id || ""} runStatus=${runStatus} elapsed=${elapsed}s\n`,
      );

      if (run && TERMINAL.has(runStatus)) {
        const git = pickGit(run);
        const url = agentUrl(info.agentId || agentId);
        if (runStatus === "FINISHED") {
          process.stdout.write(
            `CLOUD_WATCH_OK id=${agentId} runStatus=FINISHED url=${url} prUrl=${git.prUrl || "none"}\n`,
          );
          if (git.prUrl) process.stdout.write(`prUrl=${git.prUrl}\n`);
          const snip = (run.result || "").replace(/\s+/g, " ").trim().slice(0, 160);
          if (snip) process.stdout.write(`result=${snip}\n`);
          process.exit(0);
        }
        console.error(
          `CLOUD_WATCH_FAIL id=${agentId} runStatus=${runStatus} prUrl=${git.prUrl || "none"}`,
        );
        const snip = (run.result || "").replace(/\s+/g, " ").trim().slice(0, 160);
        if (snip) console.error(`result=${snip}`);
        process.exit(1);
      }

      if (run && run.supports("wait")) {
        const remaining = deadline - Date.now();
        if (remaining <= 0) break;
        try {
          await Promise.race([
            run.wait(),
            sleep(remaining).then(() => {
              throw new Error("wait-timeout");
            }),
          ]);
          continue;
        } catch (err) {
          if (safeError(err).includes("wait-timeout")) break;
          // Fall through to poll if wait is not actually live.
        }
      }

      const remaining = deadline - Date.now();
      if (remaining <= 0) break;
      await sleep(Math.min(pollSec * 1000, remaining));
    }

    const elapsed = Math.floor((Date.now() - started) / 1000);
    console.error(
      `CLOUD_WATCH_TIMEOUT id=${agentId} elapsed=${elapsed}s lastStatus=${lastStatus}`,
    );
    process.exit(1);
  } catch (err) {
    console.error(`CLOUD_WATCH_ERR id=${agentId} ${safeError(err)}`);
    process.exit(1);
  }
}

void main();

#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
const root = process.env.GCS_ROOT || process.cwd();
function run(scriptRel, argv) {
  const r = spawnSync("bash", [resolve(root, scriptRel), ...argv], { encoding: "utf8", env: process.env });
  return { out: `${r.stdout || ""}${r.stderr || ""}`.trim() || `exit=${r.status}`, ok: r.status === 0 };
}
const server = new Server({ name: "gcs-cursor-cloud", version: "1.0.0" }, { capabilities: { tools: {} } });
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    { name: "cloud_launch", description: "Launch Extra High grunt (grok-4.6 xhigh, fast=false). Requires GCS_CLOUD_REPO.", inputSchema: { type: "object", properties: { prompt: { type: "string" }, name: { type: "string" } }, required: ["prompt"] } },
    { name: "cloud_list", description: "List Extra High agents (newest first)", inputSchema: { type: "object", properties: { limit: { type: "string" } } } },
    { name: "cloud_status", description: "Status for bc-id", inputSchema: { type: "object", properties: { id: { type: "string" } }, required: ["id"] } },
    { name: "cloud_result", description: "Result JSON for bc-id", inputSchema: { type: "object", properties: { id: { type: "string" } }, required: ["id"] } },
    { name: "cloud_followup", description: "Follow-up on bc-id", inputSchema: { type: "object", properties: { id: { type: "string" }, prompt: { type: "string" } }, required: ["id", "prompt"] } },
  ],
}));
server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const name = req.params.name;
  const args = req.params.arguments || {};
  let r;
  if (name === "cloud_launch") r = run("scripts/launch-cloud-extra-high.sh", args.name ? ["--name", String(args.name), String(args.prompt)] : [String(args.prompt)]);
  else if (name === "cloud_list") r = run("scripts/cloud/list-cloud-agents.sh", args.limit ? [String(args.limit)] : []);
  else if (name === "cloud_status") r = run("scripts/cloud/status-cloud-agent.sh", [String(args.id)]);
  else if (name === "cloud_result") r = run("scripts/cloud/result-cloud-agent.sh", [String(args.id)]);
  else if (name === "cloud_followup") r = run("scripts/cloud/followup-cloud-agent.sh", [String(args.id), String(args.prompt)]);
  else return { content: [{ type: "text", text: `unknown tool ${name}` }], isError: true };
  return { content: [{ type: "text", text: r.out }], isError: !r.ok };
});
await server.connect(new StdioServerTransport());

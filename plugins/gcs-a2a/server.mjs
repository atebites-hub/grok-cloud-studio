#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
const root = process.env.GCS_ROOT || process.cwd();
const sendSh = resolve(root, "scripts/a2a/send.sh");
const registryPath = resolve(root, "docs/a2a/registry.json");
function listSeats() {
  if (!existsSync(registryPath)) return [];
  return Object.keys(JSON.parse(readFileSync(registryPath, "utf8")).seats || {});
}
const server = new Server({ name: "gcs-a2a", version: "1.0.0" }, { capabilities: { tools: {} } });
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    { name: "a2a_list_seats", description: "List A2A seats", inputSchema: { type: "object", properties: {} } },
    { name: "a2a_send", description: "Send A2A text", inputSchema: { type: "object", properties: { seat: { type: "string" }, text: { type: "string" } }, required: ["seat", "text"] } },
  ],
}));
server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const name = req.params.name;
  const args = req.params.arguments || {};
  if (name === "a2a_list_seats") return { content: [{ type: "text", text: JSON.stringify(listSeats()) }] };
  if (name === "a2a_send") {
    const r = spawnSync("bash", [sendSh, String(args.seat), String(args.text)], { encoding: "utf8", env: process.env });
    const out = `${r.stdout || ""}${r.stderr || ""}`.trim();
    return { content: [{ type: "text", text: out || `exit=${r.status}` }], isError: r.status !== 0 };
  }
  return { content: [{ type: "text", text: `unknown tool ${name}` }], isError: true };
});
await server.connect(new StdioServerTransport());

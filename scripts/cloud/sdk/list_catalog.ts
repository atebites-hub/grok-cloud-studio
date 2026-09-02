import { Agent, type SDKAgentInfo } from "@cursor/sdk";

/** Cloud Agents GET /v1/agents and Agent.list max page size. */
export const API_PAGE_MAX = 100;
export const DEFAULT_MAX_PAGES = 50;

export class CatalogError extends Error {
  readonly reason: string;

  constructor(message: string, reason = "page") {
    super(message);
    this.name = "CatalogError";
    this.reason = reason;
  }
}

export type CatalogResult = {
  items: SDKAgentInfo[];
  pages: number;
};

export function nextCursorOf(raw: string | undefined | null): string | undefined {
  const text = (raw || "").trim();
  return text || undefined;
}

function maxPagesFromEnv(): number {
  const raw = (process.env.CLOUD_OCCUPANCY_MAX_PAGES || "").trim();
  const n = raw ? Number(raw) : DEFAULT_MAX_PAGES;
  if (!Number.isFinite(n) || n <= 0) return DEFAULT_MAX_PAGES;
  return Math.min(Math.floor(n), 200);
}

/**
 * Paginate Agent.list beyond limit=100 via nextCursor.
 * Fail-closed (CatalogError reason=page) if a page throws or max pages
 * is hit while a cursor remains. Hive dump scale is 439 (five pages).
 */
export async function listAllCloudAgents(opts: {
  apiKey: string;
  pageSize?: number;
  maxPages?: number;
  maxItems?: number;
}): Promise<CatalogResult> {
  const pageSize = Math.min(Math.max(opts.pageSize ?? API_PAGE_MAX, 1), API_PAGE_MAX);
  const maxPages = Math.max(opts.maxPages ?? maxPagesFromEnv(), 1);
  const maxItems = opts.maxItems;
  const items: SDKAgentInfo[] = [];
  const seen = new Set<string>();
  let cursor: string | undefined;
  let pages = 0;
  while (pages < maxPages) {
    const listed = await Agent.list({
      runtime: "cloud",
      apiKey: opts.apiKey,
      limit: pageSize,
      ...(cursor ? { cursor } : {}),
    });
    pages += 1;
    for (const agent of listed.items) {
      const id = agent.agentId || "";
      if (id) {
        if (seen.has(id)) continue;
        seen.add(id);
      }
      items.push(agent);
      if (maxItems !== undefined && items.length >= maxItems) {
        return { items, pages };
      }
    }
    const next = nextCursorOf(listed.nextCursor);
    if (!next) return { items, pages };
    cursor = next;
  }
  throw new CatalogError("catalog truncated: max pages", "page");
}

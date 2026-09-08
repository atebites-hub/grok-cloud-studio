/**
 * Director collect: prUrl URL vs none. none + FINISHED → CLOSE.
 *
 * Leftover of a merged shard is CLOSE. No MERGE_REQUEST. No twin Extra High.
 * Live RUNNING with prUrl none is not CLOSE.
 * Distinct from waiter-owner-seat-tandem and occupancy remint.
 * Never Bot CloudAgent. Do not vendor Hermes.
 */

export const CLOSE = "CLOSE";

const NONE_TOKENS = new Set(["none", "null", "nil"]);
const CLOSE_STATUSES = new Set(["FINISHED"]);

export function prUrlOrNone(value: unknown): string | null {
  if (value == null) return null;
  const text = String(value).trim();
  if (!text) return null;
  if (NONE_TOKENS.has(text.toLowerCase())) return null;
  if (!text.includes("://") && !text.startsWith("github.com/")) return null;
  return text;
}

export type DirectorAction = "CLOSE";

export function directorAction(payload: {
  prUrl?: string | null;
  pr_url?: string | null;
  runStatus?: string | null;
  status?: string | null;
}): DirectorAction | null {
  const pr = prUrlOrNone(payload.prUrl) ?? prUrlOrNone(payload.pr_url);
  if (pr !== null) return null;
  let status = String(payload.runStatus || payload.status || "")
    .trim()
    .toUpperCase();
  if (status === "CANCELED") status = "CANCELLED";
  if (CLOSE_STATUSES.has(status)) return CLOSE;
  return null;
}

export function attachDirectorAction<
  T extends {
    prUrl?: string | null;
    pr_url?: string | null;
    runStatus?: string | null;
    status?: string | null;
  },
>(payload: T): T & { prUrl: string | null; directorAction: DirectorAction | null } {
  const prUrl = prUrlOrNone(payload.prUrl) ?? prUrlOrNone(payload.pr_url);
  return {
    ...payload,
    prUrl,
    directorAction: directorAction({ ...payload, prUrl }),
  };
}

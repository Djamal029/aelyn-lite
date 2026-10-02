import { getHealth } from "./api";

/** Cached `GET /health` check: commands/pages call this instead of
 * hitting `/health` on every keystroke or render. A short TTL keeps it
 * cheap while still noticing quickly when the backend agent's API comes
 * up or goes down during local testing. */
const TTL_MS = 15_000;
let cached: { value: boolean; at: number } | null = null;

export async function isBackendLive(): Promise<boolean> {
  const now = Date.now();
  if (cached && now - cached.at < TTL_MS) return cached.value;
  const value = await getHealth();
  cached = { value, at: now };
  return value;
}

/** Stub passkey verification for the Settings edit-lock gate.
 *
 * The real check will be an `aelyn-api` (FastAPI) endpoint owned by the
 * backend agent building it; this file exists so the frontend's
 * locked/unlocked UI state is real and testable today, and gets pointed
 * at the real endpoint with a small, contained change once that shape
 * is shared, rather than the UI staying permanently mocked.
 *
 * NOT a real security boundary: this runs entirely client-side and the
 * "passkey" is a placeholder for local UI testing only, never a secret
 * worth protecting. */
const DEMO_PASSKEY = "aelyn";

export async function verifyPasskey(candidate: string): Promise<boolean> {
  // Simulate a network round-trip so the "Vérification…" state has
  // something real to show while this is wired to the actual endpoint.
  await new Promise((resolve) => setTimeout(resolve, 350));
  return candidate.trim().toLowerCase() === DEMO_PASSKEY;
}

/** Shared vocabulary used across the mock API surface. Kept small and
 * literal (not free-form strings) so a real FastAPI backend can slot in
 * later without changing how components consume this data. */

export type Severity = "info" | "warning" | "critical";

export type OperationalState = "operational" | "degraded" | "offline";

export type ConnectivityState = "connected" | "connecting" | "disconnected";

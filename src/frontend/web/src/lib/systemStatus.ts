import type { SystemStatus } from "./api";
import type { NodeStatus, ServiceStatus } from "../types";
import { formatDuration } from "./time";

/** Turns the real `GET /system/status` payload into the same `NodeStatus`
 * shape Overview/System already render via MetricRow/StatusDot, so the
 * "AELYN Core" entry can be swapped from mocks/system.ts's static
 * placeholder to real data with no change to how those pages lay it out,
 * only to where the numbers come from. The two Raspberry Pi entries stay
 * on the mock (still genuinely true: not deployed), this only replaces
 * the one node that's actually real hardware right now.
 *
 * Every field here traces to a real measurement in `status`; where the
 * backend itself couldn't get one honestly (CPU temperature on this
 * Windows machine, no instantaneous network rate from a single
 * cumulative-counter sample) this says so explicitly rather than
 * inventing a plausible number, matching the backend's own stated
 * approach for this endpoint. */
export function coreNodeFromStatus(status: SystemStatus, label: string, role: string): NodeStatus {
  const r = status.resources;
  const s = status.services;

  const services: ServiceStatus[] = [
    {
      name: `ollama (${s.ollama.roles.llm_model.model})`,
      state: s.ollama.reachable ? "operational" : "offline",
      detail: !s.ollama.reachable
        ? (s.ollama.error ?? "injoignable")
        : s.ollama.roles.llm_model.available_locally
          ? undefined
          : "modèle non tiré localement",
    },
    {
      name: "conversational-agent",
      state: s.ollama.reachable ? "operational" : "degraded",
      detail: s.ollama.reachable ? undefined : "dépend d'Ollama, voir ci-dessus",
    },
    {
      name: "email-agent (IMAP)",
      state: s.imap.connected ? "operational" : "offline",
      detail: s.imap.connected ? undefined : s.imap.error,
    },
    {
      name: "career-agent",
      state: s.france_travail.reachable ? "operational" : "degraded",
      detail: s.france_travail.reachable
        ? `France Travail joignable · modèle CV ${s.ollama.roles.llm_model_career.model}${
            s.ollama.roles.llm_model_career.available_locally ? "" : " (non tiré)"
          }`
        : (s.france_travail.error ?? "France Travail injoignable"),
    },
    {
      name: "media-agent",
      state: !s.media_tv.configured ? "offline" : s.media_tv.connected ? "operational" : "degraded",
      detail: !s.media_tv.configured ? "TV non configurée" : s.media_tv.connected ? "TV connectée" : "configurée, pas encore connectée",
    },
    {
      name: "voice (Whisper + Kokoro)",
      state: s.voice_assets.whisper.present && s.voice_assets.kokoro.present ? "operational" : "degraded",
      detail: !s.voice_assets.whisper.present
        ? "modèle Whisper absent du disque"
        : !s.voice_assets.kokoro.present
          ? "modèle Kokoro absent du disque"
          : undefined,
    },
  ];

  return {
    id: "core",
    label,
    role,
    state: s.ollama.reachable ? "operational" : "degraded",
    cpuPercent: Math.round(r.cpu_percent),
    ramPercent: Math.round(r.ram.percent),
    tempC: r.cpu_temp_celsius.available ? Math.round(r.cpu_temp_celsius.value ?? 0) : null,
    diskPercent: Math.round(r.disk.percent),
    disks: r.disks.map((d) => ({ mountpoint: d.mountpoint, percent: Math.round(d.percent) })),
    // No instantaneous rate is possible from one cumulative-counter
    // sample (the endpoint is explicit about this); 0 here is a real
    // "not measured this way" rather than a fabricated reading, and
    // callers show the real cumulative total instead (see
    // `formatNetworkTotal`).
    netMbps: 0,
    // Real now (`tailscale status --json` server-side), not the old
    // mock's hardcoded "connected": on the actual dev machine this is
    // genuinely "disconnected" right now (Tailscale installed but
    // NeedsLogin), which is exactly the kind of thing this field should
    // reflect instead of assuming.
    tailscale: s.tailscale.connected ? "connected" : "disconnected",
    uptime: formatDuration(r.uptime_seconds),
    services,
  };
}

/** `bytes_sent + bytes_recv` as a human size, for the one real network
 * figure this endpoint actually offers (cumulative since the API
 * process started, not a rate: see `coreNodeFromStatus`). */
export function formatNetworkTotal(bytesSent: number, bytesRecv: number): string {
  const total = bytesSent + bytesRecv;
  if (total < 1_000_000) return `${(total / 1000).toFixed(0)} KB`;
  if (total < 1_000_000_000) return `${(total / 1_000_000).toFixed(1)} MB`;
  return `${(total / 1_000_000_000).toFixed(2)} GB`;
}

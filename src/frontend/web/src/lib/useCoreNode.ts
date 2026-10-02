import { useEffect, useState } from "react";
import { getHealth, getSystemStatus, type SystemStatus } from "./api";
import { coreNodeFromStatus, formatNetworkTotal } from "./systemStatus";
import { nodes as mockNodes } from "../mocks";
import type { NodeStatus } from "../types";

const mockCore = mockNodes.find((n) => n.id === "core")!;

interface CoreNodeResult {
  /** The real "AELYN Core" node (GET /system/status) when the backend is
   * reachable, the realistic mock otherwise, exactly like every other
   * live/mock-fallback surface in this app (Assistant, Settings, …). */
  core: NodeStatus;
  live: boolean;
  /** Set only when `live`: the one real network figure the status
   * endpoint can actually offer, a cumulative total since the API
   * process started, not an instantaneous rate (there's no honest way to
   * get a rate from a single sample; see lib/systemStatus.ts). `null`
   * when on the mock, where the old flat "x Mb/s" placeholder is used
   * instead. */
  networkTotal: string | null;
  /** Real NVIDIA GPU temp/utilization/VRAM when present (`nvidia-smi`),
   * `null` both when on the mock and when the live machine genuinely has
   * no NVIDIA GPU/driver; callers should treat both the same (don't show
   * a GPU section) rather than trying to tell them apart. */
  gpu: Extract<SystemStatus["resources"]["gpu"], { available: true }> | null;
  /** The raw Tailscale service status (`tailscale status --json`
   * server-side), `null` when on the mock. `core.tailscale` above is
   * already derived from this for the plain connected/disconnected dot;
   * this is for callers that want the more specific `backend_state`
   * (e.g. "NeedsLogin") instead of just a binary label. */
  tailscale: SystemStatus["services"]["tailscale"] | null;
}

/** Fetches the real system status once per mount (pages using this
 * already live inside AppShell's per-route remount, so "once per page
 * visit" is the right cadence here, not a polling interval this endpoint
 * was never designed for: it does a real IMAP login and a real France
 * Travail OAuth check every call). Falls back to mocks/system.ts's core
 * entry, unchanged, when the backend isn't reachable. */
export function useCoreNode(): CoreNodeResult {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const reachable = await getHealth();
      if (cancelled || !reachable) return;
      try {
        const s = await getSystemStatus();
        if (cancelled) return;
        setStatus(s);
        setLive(true);
      } catch {
        // stay on the mock core node
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (live && status) {
    return {
      core: coreNodeFromStatus(status, mockCore.label, mockCore.role),
      live: true,
      networkTotal: formatNetworkTotal(status.resources.network.bytes_sent, status.resources.network.bytes_recv),
      gpu: status.resources.gpu.available ? status.resources.gpu : null,
      tailscale: status.services.tailscale,
    };
  }
  return { core: mockCore, live: false, networkTotal: null, gpu: null, tailscale: null };
}

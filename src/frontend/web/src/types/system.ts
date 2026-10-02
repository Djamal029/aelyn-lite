import type { ConnectivityState, OperationalState } from "./common";

export interface ServiceStatus {
  name: string;
  state: OperationalState;
  detail?: string;
}

export interface NodeStatus {
  id: string;
  label: string;
  role: string;
  state: OperationalState;
  cpuPercent: number;
  ramPercent: number;
  /** `null` when there is genuinely no reliable reading (e.g. Windows
   * has no standard CPU-temperature sensor API without third-party
   * software, confirmed by GET /system/status): callers must show "N/A"
   * rather than a fabricated number, never default this to 0. */
  tempC: number | null;
  diskPercent: number;
  netMbps: number;
  tailscale: ConnectivityState;
  uptime: string;
  services: ServiceStatus[];
}

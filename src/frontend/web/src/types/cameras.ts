import type { ConnectivityState } from "./common";

export type RecordingState = "recording" | "standby" | "off";

export interface Camera {
  id: string;
  name: string;
  node: string;
  connection: ConnectivityState;
  fps: number;
  resolution: string;
  latencyMs: number;
  lastDetectionAt: string | null;
  lastDetectionLabel: string | null;
  recording: RecordingState;
}

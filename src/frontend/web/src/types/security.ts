import type { Severity } from "./common";

export type SecurityEventType =
  | "face_recognized"
  | "unknown_person"
  | "motion"
  | "intrusion"
  | "spoof_attempt";

export interface SecurityEvent {
  id: string;
  type: SecurityEventType;
  timestamp: string;
  camera: string;
  confidencePercent: number | null;
  severity: Severity;
  detail: string;
}

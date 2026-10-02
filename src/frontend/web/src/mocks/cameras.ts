import type { Camera } from "../types";
import { isoMinutesAgo } from "../lib/time";

/** The vision Raspberry Pi is not deployed yet (see mocks/system.ts), so
 * the detection pipeline (security-agent: YOLOv8 + anti-spoofing, see
 * src/backend/security-agent) currently runs against these cameras from
 * AELYN Core on the dev machine; `node: "core"` reflects that, not a
 * fabricated deployment. Names match the real two-camera test setup
 * (laptop webcam + phone via Iriun Webcam, see components/cameras and
 * lib/useLiveCamera.ts for the real getUserMedia wiring used for local
 * testing on the Cameras page). */
export const cameras: Camera[] = [
  {
    id: "cam-01",
    name: "Entrée",
    node: "core",
    connection: "connected",
    fps: 24,
    resolution: "1920x1080",
    latencyMs: 210,
    lastDetectionAt: isoMinutesAgo(3),
    lastDetectionLabel: "Personne détectée",
    recording: "recording",
  },
  {
    id: "cam-02",
    name: "Appartement",
    node: "core",
    connection: "connected",
    fps: 15,
    resolution: "1280x720",
    latencyMs: 180,
    lastDetectionAt: isoMinutesAgo(41),
    lastDetectionLabel: "Mouvement",
    recording: "recording",
  },
];

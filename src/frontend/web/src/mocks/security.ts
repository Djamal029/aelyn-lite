import type { SecurityEvent } from "../types";
import { isoMinutesAgo } from "../lib/time";

/** security-agent (src/backend/security-agent) ships YOLOv8 detection,
 * an anti-spoofing classifier and ArcFace face matching
 * (FACE_MATCH_THRESHOLD=0.68 in .env.example): these event types map
 * directly to that pipeline, not invented categories. */
export const securityEvents: SecurityEvent[] = [
  {
    id: "evt-01",
    type: "motion",
    timestamp: isoMinutesAgo(3),
    camera: "Entrée",
    confidencePercent: null,
    severity: "info",
    detail: "Mouvement détecté",
  },
  {
    id: "evt-02",
    type: "unknown_person",
    timestamp: isoMinutesAgo(3),
    camera: "Entrée",
    confidencePercent: 91,
    severity: "warning",
    detail: "Personne détectée, visage non reconnu",
  },
  {
    id: "evt-03",
    type: "face_recognized",
    timestamp: isoMinutesAgo(2),
    camera: "Entrée",
    confidencePercent: 97,
    severity: "info",
    detail: "Visage reconnu : Djamal (distance 0.41)",
  },
  {
    id: "evt-04",
    type: "motion",
    timestamp: isoMinutesAgo(41),
    camera: "Appartement",
    confidencePercent: null,
    severity: "info",
    detail: "Mouvement détecté",
  },
  {
    id: "evt-05",
    type: "spoof_attempt",
    timestamp: isoMinutesAgo(187),
    camera: "Entrée",
    confidencePercent: 88,
    severity: "warning",
    detail: "Anti-spoofing : présentation suspecte (photo/écran) rejetée",
  },
  {
    id: "evt-06",
    type: "face_recognized",
    timestamp: isoMinutesAgo(612),
    camera: "Appartement",
    confidencePercent: 95,
    severity: "info",
    detail: "Visage reconnu : Djamal (distance 0.36)",
  },
  {
    id: "evt-07",
    type: "intrusion",
    timestamp: isoMinutesAgo(1290),
    camera: "Appartement",
    confidencePercent: 82,
    severity: "critical",
    detail: "Présence prolongée hors horaires habituels",
  },
  {
    id: "evt-08",
    type: "unknown_person",
    timestamp: isoMinutesAgo(1440),
    camera: "Entrée",
    confidencePercent: 79,
    severity: "warning",
    detail: "Personne détectée, visage non reconnu",
  },
];

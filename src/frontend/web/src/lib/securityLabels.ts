import type { SecurityEventType, Severity } from "../types";
import type { BadgeKind } from "../components/ui/Badge";

/** Shared vocabulary for security-agent event types, kept in one place
 * so the events table, the camera detection filmstrip and any future
 * surface all label the same event the same way. */
export const SECURITY_TYPE_LABEL: Record<SecurityEventType, string> = {
  face_recognized: "Visage reconnu",
  unknown_person: "Personne inconnue",
  motion: "Mouvement",
  intrusion: "Intrusion",
  spoof_attempt: "Anti-spoofing",
};

/** Compact form for dense contexts (filmstrip captions): short enough
 * to sit under a 68px-wide thumbnail without wrapping. */
export const SECURITY_TYPE_SHORT: Record<SecurityEventType, string> = {
  face_recognized: "VISAGE",
  unknown_person: "INCONNU",
  motion: "MVT",
  intrusion: "INTRUSION",
  spoof_attempt: "SPOOF",
};

export const SEVERITY_BADGE: Record<Severity, BadgeKind> = {
  info: "info",
  warning: "warning",
  critical: "critical",
};

import { useMemo, useState } from "react";
import { EventsTable } from "../components/security/EventsTable";
import { securityEvents, cameras } from "../mocks";
import type { SecurityEvent } from "../types";
import styles from "./Security.module.css";

const TYPE_OPTIONS: { value: SecurityEvent["type"] | "all"; label: string }[] = [
  { value: "all", label: "Tous les types" },
  { value: "face_recognized", label: "Visage reconnu" },
  { value: "unknown_person", label: "Personne inconnue" },
  { value: "motion", label: "Mouvement" },
  { value: "intrusion", label: "Intrusion" },
  { value: "spoof_attempt", label: "Anti-spoofing" },
];

const SEVERITY_OPTIONS: { value: SecurityEvent["severity"] | "all"; label: string }[] = [
  { value: "all", label: "Toute sévérité" },
  { value: "info", label: "Info" },
  { value: "warning", label: "Avertissement" },
  { value: "critical", label: "Critique" },
];

export function Security() {
  const [type, setType] = useState<(typeof TYPE_OPTIONS)[number]["value"]>("all");
  const [severity, setSeverity] = useState<(typeof SEVERITY_OPTIONS)[number]["value"]>("all");
  const [camera, setCamera] = useState<string>("all");

  const filtered = useMemo(() => {
    return securityEvents
      .filter((e) => type === "all" || e.type === type)
      .filter((e) => severity === "all" || e.severity === severity)
      .filter((e) => camera === "all" || e.camera === camera)
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  }, [type, severity, camera]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>Sécurité</div>
        <div className={styles.subtitle}>
          Événements du pipeline de vision (security-agent : détection YOLOv8, anti-spoofing, reconnaissance
          faciale ArcFace)
        </div>
      </div>

      <div className={styles.filters}>
        <select className={styles.select} value={type} onChange={(e) => setType(e.target.value as typeof type)}>
          {TYPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select className={styles.select} value={severity} onChange={(e) => setSeverity(e.target.value as typeof severity)}>
          {SEVERITY_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select className={styles.select} value={camera} onChange={(e) => setCamera(e.target.value)}>
          <option value="all">Toutes les caméras</option>
          {cameras.map((c) => (
            <option key={c.id} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
        <span className={styles.count}>
          {filtered.length} / {securityEvents.length} événements
        </span>
      </div>

      <div className={styles.tableWrap}>
        <EventsTable events={filtered} selfContained={false} />
      </div>
    </div>
  );
}

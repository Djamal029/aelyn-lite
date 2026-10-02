import type { CameraUptimeStat, CommandStat, DetectionFrequencyBucket, ResourceTrend } from "../types";
import { formatHHMM, isoHoursAgo } from "../lib/time";

function trendSeries(base: number, spread: number, points: number) {
  const now = new Date();
  return Array.from({ length: points }, (_, i) => {
    const hoursAgo = points - 1 - i;
    const t = formatHHMM(new Date(isoHoursAgo(hoursAgo, now)));
    const wobble = Math.sin(i / 2.3) * spread * 0.6 + (Math.sin(i * 1.7) * spread * 0.4);
    return { t, v: Math.max(0, Math.round(base + wobble)) };
  });
}

export const resourceTrends: ResourceTrend[] = [
  {
    nodeId: "core",
    nodeLabel: "AELYN Core",
    cpu: trendSeries(27, 14, 24),
    ram: trendSeries(58, 9, 24),
    tempC: trendSeries(47, 5, 24),
  },
];

/** 24h detection frequency: highest around entry/exit hours, near zero
 * overnight, consistent with a residential entrance + interior (living
 * room) camera. */
export const detectionFrequency: DetectionFrequencyBucket[] = [
  0, 0, 0, 0, 0, 1, 2, 4, 3, 1, 1, 2, 3, 2, 1, 1, 2, 4, 6, 5, 3, 2, 1, 0,
].map((count, hour) => ({ hour: `${String(hour).padStart(2, "0")}h`, count }));

export const commandStats: CommandStat[] = [
  { command: "verifier", label: "Vérifier mails", count: 34 },
  { command: "triage", label: "Trier mails", count: 21 },
  { command: "chercher_offres", label: "Chercher offres", count: 12 },
  { command: "media", label: "Contrôle média", count: 19 },
  { command: "rapport", label: "Rapport d'activité", count: 6 },
  { command: "camera", label: "Ouvrir caméra", count: 15 },
];

export const cameraUptimeStats: CameraUptimeStat[] = [
  { camera: "Entrée", uptimePercent: 99.4, detections24h: 14, avgLatencyMs: 215 },
  { camera: "Appartement", uptimePercent: 97.1, detections24h: 6, avgLatencyMs: 190 },
];

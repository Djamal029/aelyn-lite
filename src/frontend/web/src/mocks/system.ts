import type { NodeStatus } from "../types";

/** Target architecture per README: AELYN Core + 2 Raspberry Pi (general,
 * vision/security). Repo currently runs everything on a single Windows
 * PC; the two Pi entries reflect the planned split, marked "offline"
 * since they are not deployed yet, rather than inventing fake activity
 * for hardware that does not exist on the network. */
export const nodes: NodeStatus[] = [
  {
    id: "core",
    label: "AELYN Core",
    role: "Orchestration, LLM (Ollama), mail, carrière, conversation",
    state: "operational",
    cpuPercent: 23,
    ramPercent: 61,
    tempC: 48,
    diskPercent: 34,
    netMbps: 1.2,
    tailscale: "connected",
    uptime: "6 j 14 h",
    services: [
      { name: "ollama (qwen3:4b)", state: "operational" },
      { name: "conversational-agent", state: "operational" },
      { name: "email-agent (IMAP poll)", state: "operational" },
      { name: "career-agent", state: "operational", detail: "scoring hors-ligne, non branché au chat" },
      { name: "media-agent", state: "operational", detail: "Freebox Pop appairée" },
      { name: "voice (Whisper + Kokoro)", state: "operational" },
    ],
  },
  {
    id: "pi-general",
    label: "Raspberry Pi 1 : Général",
    role: "Cœur AELYN (cible de déploiement, non déployé)",
    state: "offline",
    cpuPercent: 0,
    ramPercent: 0,
    tempC: 0,
    diskPercent: 0,
    netMbps: 0,
    tailscale: "disconnected",
    uptime: "N/A",
    services: [
      { name: "ollama", state: "offline", detail: "matériel non déployé" },
      { name: "conversational-agent", state: "offline" },
    ],
  },
  {
    id: "pi-vision",
    label: "Raspberry Pi 2 : Vision",
    role: "Caméras, détection, reconnaissance faciale (cible, non déployé)",
    state: "offline",
    cpuPercent: 0,
    ramPercent: 0,
    tempC: 0,
    diskPercent: 0,
    netMbps: 0,
    tailscale: "disconnected",
    uptime: "N/A",
    services: [
      { name: "security-agent (YOLOv8)", state: "offline", detail: "matériel non déployé" },
      { name: "anti-spoofing", state: "offline" },
      { name: "reconnaissance faciale", state: "offline" },
    ],
  },
];

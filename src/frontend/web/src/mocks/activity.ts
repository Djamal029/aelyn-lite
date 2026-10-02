import type { ActivityEntry } from "../types";
import { isoMinutesAgo } from "../lib/time";

/** Real system log of what AELYN did: one entry per actual action taken
 * by an agent (voice/text routing, vision pipeline, mail, career, media),
 * not a decorative feed. Mirrors the transcript style from the design
 * doc's Overview mockup. */
export const activityLog: ActivityEntry[] = [
  { id: "a-01", timestamp: isoMinutesAgo(2), message: "Commande vocale reçue : « montre-moi la caméra de l'entrée »", source: "voice" },
  { id: "a-02", timestamp: isoMinutesAgo(2), message: "Caméra Entrée ouverte", source: "vision" },
  { id: "a-03", timestamp: isoMinutesAgo(3), message: "Personne détectée (Entrée)", source: "vision" },
  { id: "a-04", timestamp: isoMinutesAgo(2), message: "Visage reconnu : Djamal (Entrée)", source: "vision" },
  { id: "a-05", timestamp: isoMinutesAgo(2), message: "Notification envoyée", source: "system" },
  { id: "a-06", timestamp: isoMinutesAgo(9), message: "Commande texte reçue : « vérifie mes mails »", source: "text" },
  { id: "a-07", timestamp: isoMinutesAgo(9), message: "3 mails non lus récupérés (IMAP)", source: "email" },
  { id: "a-08", timestamp: isoMinutesAgo(26), message: "Recherche d'offres France Travail : Data Scientist, Rennes (35)", source: "career" },
  { id: "a-09", timestamp: isoMinutesAgo(26), message: "8 offres trouvées, triées par score BM25/cosinus", source: "career" },
  { id: "a-10", timestamp: isoMinutesAgo(41), message: "Mouvement détecté (Appartement)", source: "vision" },
  { id: "a-11", timestamp: isoMinutesAgo(58), message: "Commande vocale reçue : « lance Netflix »", source: "voice" },
  { id: "a-12", timestamp: isoMinutesAgo(58), message: "Freebox Pop : lancement Netflix", source: "media" },
  { id: "a-13", timestamp: isoMinutesAgo(187), message: "Anti-spoofing : présentation suspecte rejetée (Entrée)", source: "vision" },
  { id: "a-14", timestamp: isoMinutesAgo(190), message: "Triage mail exécuté : 5 mails, 3 propositions", source: "email" },
  { id: "a-15", timestamp: isoMinutesAgo(190), message: "Action #2 validée : archivage (newsletter LinkedIn)", source: "email" },
];

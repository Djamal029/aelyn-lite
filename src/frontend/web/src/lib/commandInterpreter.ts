import type { AelynCommand, ChatResultType } from "../types";
import type { ApiEmailListItem, ApiOfferResult, MediaAction } from "./api";

export interface InterpretedCommand {
  command: AelynCommand;
  understood: string;
  resultText: string;
  status: "done" | "error";
  needsConfirmation: boolean;
  /** Set when `command === "media"`: the real action string
   * (lib/commandResolver.ts calls `POST /media/{action}` with it when
   * aelyn-api is reachable). */
  mediaAction?: MediaAction;
  /** Set when `command === "chercher_offres"` and a keyword phrase was
   * actually extracted, used to call the real `GET /career`. */
  careerKeywords?: string;
  /** Set by lib/commandResolver.ts once a real list is available (either
   * from the fast-path GET /email / GET /career calls, or from
   * POST /chat/message's own result_type/results), so ChatMessage can
   * render a real table instead of a plain-text summary. */
  resultType?: ChatResultType;
  results?: ApiOfferResult[] | ApiEmailListItem[];
}

/** A small, front-end mirror of the real fast-router
 * (conversational-agent/src/aelyn_conversation/fast_router.py): regex
 * classification for unambiguous phrases, same command vocabulary
 * (`Intent.commande`). This function itself never calls a backend: it
 * only classifies the phrase and produces a plausible "COMPRIS : ..." +
 * a default result, used ONLY when aelyn-api is unreachable (offline
 * demo). lib/commandResolver.ts wraps this and, whenever the backend is
 * live, replaces this canned result: verifier/chercher_offres/media via
 * their own dedicated GET/POST call, triage/rapport/valider/rejeter/
 * anything else via POST /chat/message (the real ConversationalAgent,
 * same pipeline as verifier). Only `camera` still has no backend
 * equivalent to fall through to. The demo text below is deliberately
 * fake and labeled as such, since it's the only thing shown while
 * offline. */
export function interpretCommand(raw: string): InterpretedCommand {
  const text = raw.trim();
  const normalized = text.toLowerCase();

  const cameraMatch = normalized.match(/cam[ée]ra?\s*(?:de\s+l['’])?\s*(entr[ée]e|appartement|\d+)/);
  if (cameraMatch) {
    const raw2 = cameraMatch[1];
    const label = raw2 === "1" ? "Entrée" : raw2 === "2" ? "Appartement" : capitalize(raw2);
    return {
      command: "camera",
      understood: `COMPRIS : Ouvrir caméra / ${label}`,
      resultText: `Caméra ${label} ouverte.`,
      status: "done",
      needsConfirmation: false,
    };
  }

  if (/\btrie|triage\b/.test(normalized)) {
    return {
      command: "triage",
      understood: "COMPRIS : Trier les mails (proposition, sans exécution)",
      resultText:
        "#1 EDF : Facture septembre -> Proposition : archiver\n#2 LinkedIn : Offres pour vous -> Proposition : archiver\n(démonstration locale, aelyn-api n'expose pas encore de tri/exécution mail)",
      status: "done",
      needsConfirmation: false,
    };
  }

  if (/\bv[ée]rifi/.test(normalized)) {
    return {
      command: "verifier",
      understood: "COMPRIS : Vérifier les mails non lus",
      resultText: "3 mails non lus.",
      status: "done",
      needsConfirmation: false,
    };
  }

  const validateMatch = normalized.match(/\bvalide?\w*\s+(?:la\s+|le\s+|#)?(\d+)/);
  if (validateMatch) {
    return {
      command: "valider",
      understood: `COMPRIS : Valider l'action #${validateMatch[1]}`,
      resultText: "Action exécutée. (démonstration locale, aucun endpoint de validation mail côté aelyn-api pour l'instant)",
      status: "done",
      needsConfirmation: true,
    };
  }

  const rejectMatch = normalized.match(/\brejette?\w*\s+(?:la\s+|le\s+|#)?(\d+)/);
  if (rejectMatch) {
    return {
      command: "rejeter",
      understood: `COMPRIS : Rejeter l'action #${rejectMatch[1]}`,
      resultText: "Action rejetée. (démonstration locale, aucun endpoint de rejet mail côté aelyn-api pour l'instant)",
      status: "done",
      needsConfirmation: true,
    };
  }

  if (/\brapport\b/.test(normalized)) {
    return {
      command: "rapport",
      understood: "COMPRIS : Générer le rapport d'activité",
      resultText:
        "12 actions sur les dernières 24h : 3 mails triés, 1 recherche d'offres, 2 commandes média. (démonstration locale, aucun endpoint de rapport côté aelyn-api pour l'instant)",
      status: "done",
      needsConfirmation: false,
    };
  }

  if (/\boffres?\b|\bemploi\b|\bstage\b|\balternance\b/.test(normalized)) {
    const keywordMatch = normalized.match(/offres?\s+(?:de\s+|d['’])?(.+)/);
    const keywords = keywordMatch?.[1]?.trim();
    return {
      command: "chercher_offres",
      understood: `COMPRIS : Chercher des offres / mots-clés : ${keywords || "non précisés"}`,
      resultText: "6 offres trouvées, triées par score BM25/cosinus.",
      status: "done",
      needsConfirmation: false,
      careerKeywords: keywords || undefined,
    };
  }

  if (/\bnetflix\b/.test(normalized)) {
    return {
      command: "media",
      understood: "COMPRIS : Média / netflix",
      resultText: "Netflix lancé sur la TV.",
      status: "done",
      needsConfirmation: false,
      mediaAction: "netflix",
    };
  }
  if (/\byoutube\b/.test(normalized)) {
    return {
      command: "media",
      understood: "COMPRIS : Média / youtube",
      resultText: "YouTube lancé sur la TV.",
      status: "done",
      needsConfirmation: false,
      mediaAction: "youtube",
    };
  }
  if (/\bvolume\b|\bson\b/.test(normalized)) {
    const action = /baisse|diminue/.test(normalized) ? "volume_down" : "volume_up";
    return {
      command: "media",
      understood: `COMPRIS : Média / ${action}`,
      resultText: "Volume ajusté.",
      status: "done",
      needsConfirmation: false,
      mediaAction: action,
    };
  }

  if (text.length === 0) {
    return {
      command: "inconnu",
      understood: "",
      resultText: "",
      status: "error",
      needsConfirmation: false,
    };
  }

  return {
    command: "inconnu",
    understood: "COMPRIS : conversation libre",
    resultText:
      "Je n'ai pas de commande pour ça, mais je t'écoute. Reformule si tu attendais une action précise.",
    status: "done",
    needsConfirmation: false,
  };
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

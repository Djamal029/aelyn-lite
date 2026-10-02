import type { ApiEmailListItem, ApiOfferResult } from "../lib/api";

/** Mirrors the real backend's `Intent.commande` vocabulary
 * (conversational-agent/src/aelyn_conversation/models.py) plus `camera`,
 * which is not wired to the conversational agent yet but is exercised
 * from the Overview command bar per the design brief. */
export type AelynCommand =
  | "verifier"
  | "triage"
  | "valider"
  | "rejeter"
  | "rapport"
  | "chercher_offres"
  | "media"
  | "camera"
  | "inconnu";

export type ChatRole = "user" | "aelyn";

export type ChatStatus = "executing" | "done" | "error" | "cancelled";

export type ChatResultType = "offers" | "mails";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  timestamp: string;
  text: string;
  /** The "COMPRIS : ..." transparency line shown before the result,
   * present on AELYN turns that were routed through a command rather
   * than free conversation. */
  understood?: string;
  command?: AelynCommand;
  status?: ChatStatus;
  via?: "text" | "voice";
  /** Set on AELYN turns whose reply is a real structured list (offer
   * search or mail check) rather than a plain sentence, from either the
   * real `POST /chat/message` (result_type/results) or the fast-router
   * paths that already fetch a real list directly (verifier -> GET
   * /email, chercher_offres -> GET /career). When present, ChatMessage
   * renders a real table (ChatResultTable) instead of relying on `text`
   * to spell the list out as bullets. */
  resultType?: ChatResultType;
  results?: ApiOfferResult[] | ApiEmailListItem[];
}

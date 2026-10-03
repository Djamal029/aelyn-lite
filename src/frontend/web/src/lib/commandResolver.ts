import { interpretCommand, type InterpretedCommand } from "./commandInterpreter";
import { ApiError, rejectEmailAction, sendChatMessage, triggerMediaAction, validateEmailAction } from "./api";
import { isBackendLive } from "./backendStatus";
import { LITE_MODE } from "./liteMode";

/** Wraps the synchronous, regex-based classifier (commandInterpreter.ts)
 * with real execution against aelyn-api for the commands that now have
 * a genuine backend behind them:
 *  - media   -> POST /media/{action} (real TV control)
 *  - tout le reste de non vide (verifier, chercher_offres, triage,
 *    rapport, valider, rejeter, inconnu/conversation libre) ->
 *    POST /chat/message, qui exécute le vrai ConversationalAgent (fast
 *    router, routage SYSTEM_INTENT, résolution de référence mail/offre).
 *
 * verifier et chercher_offres (avec mot-clé) appelaient auparavant
 * directement GET /email / GET /career, en contournant
 * ConversationalAgent entièrement : plus rapide, mais DEUX bugs réels
 * observés en direct par ce court-circuit. (1) GET /career n'a jamais
 * reçu la limite demandée ("cherche 15 offres..." retombait toujours sur
 * le défaut de 10 de l'endpoint, le nombre dans la phrase était juste
 * ignoré) ; le filet de sécurité regex pour `limit`/`mots_cles`
 * (cf. `_OFFERS_LIMIT_RE`/`_OFFERS_KEYWORDS_RE` côté agent) ne vit QUE
 * dans `_dispatch_phrase`, jamais exécuté par ce court-circuit. (2) GET
 * /email et GET /career n'alimentent ni `_last_mails` ni `_last_offers`
 * sur l'agent conversationnel (état interne à `/chat/message` seul) :
 * "vérifie mes mails" puis "résume-moi le mail de X" répondait "je ne
 * sais pas de quel mail tu parles", et "cherche des offres..." puis
 * "décris la première offre" retombait sur un `_last_offers` périmé
 * d'une recherche précédente (ou déclenchait une nouvelle recherche),
 * l'agent n'ayant simplement jamais vu la recherche faite via le
 * court-circuit. `verifier` a par ailleurs son propre raccourci rapide
 * côté `fast_router.py` (aucune latence LLM perdue en le routant par
 * /chat/message) ; pour `chercher_offres`, le coût latence du LLM est
 * accepté au profit d'une limite/mots-clés et d'un suivi de contexte
 * enfin corrects. Seul `camera` reste sans équivalent /chat/message côté
 * lecture vidéo. Si aelyn-api est injoignable, tout retombe sur le
 * résultat classifié localement comme avant. */
export async function resolveCommand(rawText: string): Promise<InterpretedCommand> {
  const base = interpretCommand(rawText);
  if (LITE_MODE && base.command === "camera") {
    return {
      ...base,
      command: "inconnu",
      understood: "",
      resultText: "Cette commande n'est pas disponible dans cette version.",
      status: "error",
      needsConfirmation: false,
    };
  }
  const live = await isBackendLive();
  if (!live) return base;

  try {
    if (base.command === "media" && base.mediaAction) {
      await triggerMediaAction(base.mediaAction);
      return base;
    }

    // `POST /chat/message` refuse délibérément d'exécuter valider/rejeter
    // (cf. le docstring de `ConversationalAgent.handle_message`,
    // `confirm=False`) : jusqu'ici, "valide l'action 3" dans le chat web
    // n'avait donc JAMAIS d'effet réel, juste un texte l'expliquant. Avec
    // un id numérique trouvé dans la phrase, on appelle directement la
    // vraie route d'exécution à la place.
    if ((base.command === "valider" || base.command === "rejeter") && base.actionId !== undefined) {
      const result =
        base.command === "valider" ? await validateEmailAction(base.actionId) : await rejectEmailAction(base.actionId);
      return {
        ...base,
        resultText:
          base.command === "valider"
            ? result.status === "executed"
              ? `Action #${base.actionId} exécutée.`
              : `Action #${base.actionId} non exécutée (envoi autonome désactivé, voir réglages).`
            : `Action #${base.actionId} rejetée.`,
        status: "done",
      };
    }

    if (
      (base.command === "inconnu" ||
        base.command === "verifier" ||
        base.command === "triage" ||
        base.command === "rapport" ||
        base.command === "valider" ||
        base.command === "rejeter" ||
        base.command === "chercher_offres") &&
      rawText.trim()
    ) {
      const reply = await sendChatMessage(rawText.trim());
      // `triage` renvoie désormais `result_type: "mails"` avec, en plus
      // des champs mail habituels, `action_proposee`/`urgence`/`resume`
      // par mail (cf. `_mail_to_dict` côté agent) : ChatResultTable y
      // ajoute une colonne "Action proposée" dédiée, donc le tableau est
      // transmis pour TOUTES les commandes désormais, triage inclus
      // (avant cette colonne, l'afficher aurait effacé le détail du
      // triage, visible uniquement dans le texte prose ; ce n'est plus
      // le cas).
      return {
        command: base.command,
        understood: base.command === "inconnu" ? "" : base.understood,
        resultText: reply.text,
        status: "done",
        needsConfirmation: false,
        resultType: reply.result_type ?? undefined,
        results: reply.results ?? undefined,
      };
    }
  } catch (err) {
    const detail = err instanceof ApiError ? err.message : "AELYN Core injoignable";
    return { ...base, resultText: `${base.resultText}\n(échec de l'exécution réelle : ${detail})`, status: "error" };
  }

  return base;
}

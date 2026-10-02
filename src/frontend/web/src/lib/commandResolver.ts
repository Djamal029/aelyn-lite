import { interpretCommand, type InterpretedCommand } from "./commandInterpreter";
import { ApiError, getCareerOffers, getEmails, sendChatMessage, triggerMediaAction } from "./api";
import { isBackendLive } from "./backendStatus";

/** Wraps the synchronous, regex-based classifier (commandInterpreter.ts)
 * with real execution against aelyn-api for the commands that now have
 * a genuine backend behind them:
 *  - verifier          -> GET /email (real unread mail)
 *  - chercher_offres   -> GET /career (real France Travail results)
 *  - media             -> POST /media/{action} (real TV control)
 *  - inconnu (free text, non-empty) -> POST /chat/message, which now
 *    runs the real ConversationalAgent pipeline (fast router,
 *    SYSTEM_INTENT routing, offer/mail reference resolution), not a bare
 *    LLM call, so a follow-up like "affiche les offres" correctly
 *    returns the same list rather than a generic reply. When its
 *    `result_type`/`results` are populated, they're carried straight
 *    through to `resultType`/`results` below.
 *
 * verifier et chercher_offres (avec un mot-clé explicite) gardent leur
 * appel direct (GET /email, GET /career) : plus rapide qu'un
 * aller-retour /chat/message, et `resultType`/`results` sont renseignés
 * directement pour que ChatMessage affiche un vrai tableau sans passer
 * par le LLM. Pour triage/rapport/valider/rejeter, et pour
 * chercher_offres SANS mot-clé (ex. "cherche des offres"/"affiche les
 * offres"), aucun GET dédié n'existe (GET /career sans mots_cles ne
 * reproduit pas le choix par défaut réel du profil, et surtout
 * n'alimente pas `_last_offers` de ConversationalAgent, le state que
 * /chat/message consulte pour un suivi comme "prépare un cv" ou
 * "cv" tout court) ; ConversationalAgent les traite déjà réellement via
 * /chat/message (même pipeline que "verifie mes mails"), donc on y route
 * ces commandes au lieu de garder le texte de démonstration local
 * d'commandInterpreter — un bug réel observé en direct : "cherche des
 * offres" (sans mot-clé) affichait le texte figé "6 offres trouvées..."
 * de commandInterpreter (jamais une vraie recherche), si bien qu'un
 * "cv" juste après échouait ("je ne sais pas de quelle offre tu
 * parles"), alors que le texte précédent prétendait avoir trouvé des
 * offres. Seul `camera` reste sans équivalent /chat/message côté lecture
 * vidéo. Si aelyn-api est injoignable, tout retombe sur le résultat
 * classifié localement comme avant. */
export async function resolveCommand(rawText: string): Promise<InterpretedCommand> {
  const base = interpretCommand(rawText);
  const live = await isBackendLive();
  if (!live) return base;

  try {
    if (base.command === "verifier") {
      const emails = await getEmails(5);
      if (emails.length === 0) return { ...base, resultText: "Aucun mail non lu." };
      return {
        ...base,
        resultText: `${emails.length} mail(s) non lu(s).`,
        resultType: "mails",
        results: emails,
      };
    }

    if (base.command === "chercher_offres" && base.careerKeywords) {
      const offers = await getCareerOffers({ motsCles: base.careerKeywords });
      if (offers.length === 0) return { ...base, resultText: `Aucune offre trouvée pour « ${base.careerKeywords} ».` };
      return {
        ...base,
        resultText: `${offers.length} offre(s) trouvée(s) pour « ${base.careerKeywords} ».`,
        resultType: "offers",
        results: offers,
      };
    }

    if (base.command === "media" && base.mediaAction) {
      await triggerMediaAction(base.mediaAction);
      return base;
    }

    if (
      (base.command === "inconnu" ||
        base.command === "triage" ||
        base.command === "rapport" ||
        base.command === "valider" ||
        base.command === "rejeter" ||
        (base.command === "chercher_offres" && !base.careerKeywords)) &&
      rawText.trim()
    ) {
      const reply = await sendChatMessage(rawText.trim());
      // `triage` renvoie `result_type: "mails"` côté backend (même forme
      // que "vérifie mes mails" : la liste brute des mails lus), mais ici
      // l'information utile (action proposée/urgence/justification par
      // mail) vit UNIQUEMENT dans `reply.text` : ChatMessage, dès qu'un
      // tableau est affiché, ne montre que la PREMIÈRE ligne du texte
      // (cf. `hasTable` dans ChatMessage.tsx, pensé pour "X mails non
      // lus" + tableau). Pour triage, afficher ce même tableau effacerait
      // tout le détail du triage ; on ne transmet donc pas le tableau
      // pour cette commande, seul le texte complet compte.
      const forwardTable = base.command !== "triage";
      return {
        command: base.command,
        understood: base.command === "inconnu" ? "" : base.understood,
        resultText: reply.text,
        status: "done",
        needsConfirmation: false,
        resultType: forwardTable ? (reply.result_type ?? undefined) : undefined,
        results: forwardTable ? (reply.results ?? undefined) : undefined,
      };
    }
  } catch (err) {
    const detail = err instanceof ApiError ? err.message : "AELYN Core injoignable";
    return { ...base, resultText: `${base.resultText}\n(échec de l'exécution réelle : ${detail})`, status: "error" };
  }

  return base;
}

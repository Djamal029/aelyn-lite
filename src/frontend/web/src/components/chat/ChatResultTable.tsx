import type { ApiEmailListItem, ApiOfferResult } from "../../lib/api";
import type { ChatResultType } from "../../types";
import { formatTimestamp } from "../../lib/time";
import styles from "./ChatResultTable.module.css";

interface ChatResultTableProps {
  resultType: ChatResultType;
  results: ApiOfferResult[] | ApiEmailListItem[];
}

function formatMailDate(value: string | null): string {
  if (!value) return "N/A";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : formatTimestamp(date.toISOString());
}

function formatOfferDate(value?: string | null): string {
  if (!value) return "N/A";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : formatTimestamp(date.toISOString());
}

// Normalise les deux formes possibles d'une offre (cf. ApiOfferResult) :
// sans ça, le dict brut France Travail que /chat/message renvoie
// maintenant (entreprise/lieuTravail en objets imbriqués, pas les
// chaînes aplaties que GET /career fournissait) affichait "[object
// Object]" ou "N/A" partout dans ce tableau.
function offerCompany(o: ApiOfferResult): string {
  if (typeof o.entreprise === "string") return o.entreprise || "N/A";
  if (o.entreprise?.nom) return o.entreprise.nom;
  if (typeof o.company === "string") return o.company || "N/A";
  return o.company?.name ?? "N/A";
}
function offerLocation(o: ApiOfferResult): string {
  if (o.lieu || o.lieuTravail?.libelle) return o.lieu ?? o.lieuTravail?.libelle ?? "N/A";
  if (typeof o.location === "string") return o.location || "N/A";
  return o.location?.city ?? o.location?.raw ?? o.location?.remote ?? "N/A";
}
function offerContract(o: ApiOfferResult): string {
  return o.contrat ?? o.typeContrat ?? o.contract_type ?? "N/A";
}
function offerApplyUrl(o: ApiOfferResult): string | undefined {
  const candidates = [
    o.application?.url,
    o.url,
    o.urlOffre,
    o.lien,
    ...(o.origineOffre?.partenaires ?? []).map((partner) => partner.url),
    o.origineOffre?.urlOrigine,
  ];
  for (const candidate of candidates) {
    if (!candidate) continue;
    try {
      const parsed = new URL(candidate);
      if (parsed.protocol === "https:" || parsed.protocol === "http:") return parsed.href;
    } catch {
      // Ignore malformed links from upstream APIs; never invent a destination.
    }
  }
  return undefined;
}
function offerDeadline(o: ApiOfferResult): string | undefined {
  return o.application?.deadline ?? o.deadline ?? o.expires_at ?? o.dateLimiteDePotentiel ?? o.dateLimite ?? o.dateFin;
}
function offerSource(o: ApiOfferResult): string {
  const source = o.source ?? o.sources_seen?.[0]?.source ?? "France Travail";
  return source === "francetravail" ? "France Travail" : source;
}

/** Renders a real chat-reply list (offer search / mail check) as an
 * actual table instead of the plain-sentence/bullet-list summary the
 * backend's `text` field alone would produce, same borders/spacing
 * language as EventsTable (components/security/EventsTable.tsx) so it
 * reads as one system rather than a one-off style. Used by ChatMessage
 * whenever `resultType`/`results` are present on an AELYN turn. */
export function ChatResultTable({ resultType, results }: ChatResultTableProps) {
  if (results.length === 0) return null;

  if (resultType === "offers") {
    const offers = results as ApiOfferResult[];
    return (
      <div className={styles.wrap}>
        <div className={styles.scroll}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Poste</th>
                <th>Entreprise</th>
                <th>Lieu</th>
                <th>Contrat</th>
                <th>Publié</th>
                <th>Deadline</th>
                <th>Source</th>
                <th>Score</th>
                <th>Postuler</th>
              </tr>
            </thead>
            <tbody>
              {offers.map((o, i) => {
                const applyUrl = offerApplyUrl(o);
                return (
                  <tr key={o.id ?? `${o.intitule ?? "offre"}-${i}`}>
                    <td>{o.intitule ?? o.title ?? "N/A"}</td>
                    <td>{offerCompany(o)}</td>
                    <td>{offerLocation(o)}</td>
                    <td>{offerContract(o)}</td>
                    <td className={styles.date}>{formatOfferDate(o.date_publication ?? o.dateCreation ?? o.date_creation ?? o.posted_at)}</td>
                    <td className={styles.date}>{formatOfferDate(offerDeadline(o))}</td>
                    <td>{offerSource(o)}</td>
                    <td className={styles.score}>{typeof o.score === "number" ? `${Math.round(o.score * 100)}%` : "N/A"}</td>
                    <td>
                      {applyUrl ? (
                        <a href={applyUrl} target="_blank" rel="noreferrer noopener">
                          Lien
                        </a>
                      ) : (
                        "N/A"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  const mails = results as ApiEmailListItem[];
  // "triage" renvoie une action_proposee par mail, "verifier" non (simple
  // liste des non-lus) : colonne ajoutée seulement quand il y a vraiment
  // quelque chose à y montrer, plutôt qu'une colonne "Action" vide pour
  // verifier.
  const hasActions = mails.some((m) => m.action_proposee);
  return (
    <div className={styles.wrap}>
      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              {hasActions ? <th>#</th> : null}
              <th>Expéditeur</th>
              <th>Objet</th>
              <th>Date</th>
              {hasActions ? <th>Action proposée</th> : null}
            </tr>
          </thead>
          <tbody>
            {mails.map((m) => (
              <tr key={m.uid}>
                {/* Numéro affiché tel quel : c'est ce qu'il faut dire pour
                 * agir dessus ("valide l'action 265"), aucun autre moyen
                 * fiable de désigner une proposition précise par la voix/le
                 * texte (une recherche par expéditeur/sujet ne peut pas se
                 * résoudre côté client, l'historique des propositions
                 * n'existe que côté serveur). */}
                {hasActions ? <td className={styles.actionId}>{m.action_id ?? "—"}</td> : null}
                <td>{m.sender || m.sender_email}</td>
                <td>{m.subject}</td>
                <td className={styles.date}>{formatMailDate(m.date)}</td>
                {hasActions ? <td>{m.action_proposee ?? "N/A"}</td> : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

import { useState } from "react";
import type { ApiEmailListItem, ApiOfferResult } from "../../lib/api";
import type { ChatResultType } from "../../types";
import { formatTimestamp } from "../../lib/time";
import styles from "./ChatResultTable.module.css";

interface ChatResultTableProps {
  resultType: ChatResultType;
  results: ApiOfferResult[] | ApiEmailListItem[];
  /** Quand fourni, affiche une case à cocher par offre et une barre
   * d'action "Préparer N CV" / "Préparer N lettres" (candidature facile
   * sur plusieurs offres à la fois) - omis par défaut (ex. CommandBar en
   * variante "console", un simple aperçu sans fil de conversation où
   * ajouter le résultat). */
  onPrepareCvs?: (offers: { id: string; title: string }[]) => void;
  onPrepareCoverLetters?: (offers: { id: string; title: string }[]) => void;
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
export function ChatResultTable({ resultType, results, onPrepareCvs, onPrepareCoverLetters }: ChatResultTableProps) {
  // Un seul état de sélection pour toute la vie du composant : React lui
  // donne une identité stable tant que la position dans l'arbre ne change
  // pas (même si `results` change de contenu), donc pas besoin de la
  // réinitialiser explicitement - un nouveau tableau de résultats a de
  // toute façon de nouveaux `id`, les anciens cochés ne matcheraient rien.
  const [selected, setSelected] = useState<Set<string>>(new Set());

  if (results.length === 0) return null;

  if (resultType === "offers") {
    const offers = results as ApiOfferResult[];
    const selectable = Boolean(onPrepareCvs || onPrepareCoverLetters);
    const offersWithId = offers.filter((o) => Boolean(o.id));
    const chosenOffers = () =>
      offers
        .filter((o) => o.id && selected.has(o.id))
        .map((o) => ({ id: o.id!, title: o.intitule ?? o.title ?? "cette offre" }));
    const toggle = (id: string) => {
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
    };
    const toggleAll = () => {
      setSelected((prev) =>
        prev.size === offersWithId.length ? new Set() : new Set(offersWithId.map((o) => o.id!))
      );
    };
    return (
      <div className={styles.wrap}>
        <div className={styles.scroll}>
          <table className={styles.table}>
            <thead>
              <tr>
                {selectable ? (
                  <th>
                    {offersWithId.length > 0 ? (
                      <input
                        type="checkbox"
                        checked={selected.size === offersWithId.length}
                        onChange={toggleAll}
                        aria-label="Tout sélectionner"
                      />
                    ) : null}
                  </th>
                ) : null}
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
                const title = o.intitule ?? o.title ?? "N/A";
                return (
                  <tr key={o.id ?? `${title}-${i}`}>
                    {selectable ? (
                      <td>
                        {o.id ? (
                          <input
                            type="checkbox"
                            checked={selected.has(o.id)}
                            onChange={() => toggle(o.id!)}
                            aria-label={`Sélectionner ${title}`}
                          />
                        ) : null}
                      </td>
                    ) : null}
                    <td>{title}</td>
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
        {selectable && selected.size > 0 ? (
          <div className={styles.bulkBar}>
            <span>{selected.size} offre{selected.size > 1 ? "s" : ""} sélectionnée{selected.size > 1 ? "s" : ""}</span>
            {onPrepareCvs ? (
              <button
                type="button"
                className={styles.bulkButton}
                onClick={() => onPrepareCvs(chosenOffers())}
              >
                Préparer {selected.size > 1 ? `${selected.size} CV` : "le CV"}
              </button>
            ) : null}
            {onPrepareCoverLetters ? (
              <button
                type="button"
                className={styles.bulkButton}
                onClick={() => onPrepareCoverLetters(chosenOffers())}
              >
                Préparer {selected.size > 1 ? `${selected.size} lettres` : "la lettre"}
              </button>
            ) : null}
          </div>
        ) : null}
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
                {hasActions ? <td className={styles.actionId}>{m.action_id ?? "N/A"}</td> : null}
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

import { Fragment, useState } from "react";
import { Badge, type BadgeKind } from "../components/ui/Badge";
import { EmptyState } from "../components/ui/EmptyState";
import { formatTimestamp } from "../lib/time";
import { useApplications } from "../lib/useApplications";
import type { ApiApplication, ApplicationStatus } from "../lib/api";
import styles from "./Applications.module.css";

const STATUS_OPTIONS: { value: ApplicationStatus; label: string }[] = [
  { value: "postule", label: "Postulé" },
  { value: "relance", label: "Relance à faire" },
  { value: "entretien", label: "Entretien" },
  { value: "refuse", label: "Refusé" },
  { value: "accepte", label: "Accepté" },
];

const STATUS_BADGE: Record<ApplicationStatus, BadgeKind> = {
  postule: "info",
  relance: "warning",
  entretien: "active",
  refuse: "critical",
  accepte: "operational",
};

interface DetailRowProps {
  application: ApiApplication;
  onSetDescription: (offerId: string, description: string) => void;
  onSetInterviewDate: (offerId: string, interviewDate: string) => void;
  onGenerateQuestions: (offerId: string, description?: string) => void;
  onGeneratePrep: (offerId: string, description?: string) => void;
}

/** Panneau déplié sous une ligne : description de l'offre (collée/éditée
 * à la main, AELYN n'invente jamais le contenu d'une offre), date
 * proposée pour l'entretien (éditée à la main aussi), questions à poser
 * au recruteur (cf. `generate_interview_questions`) et préparation côté
 * candidat - questions que LE RECRUTEUR pourrait poser + présentation
 * personnelle orale, toutes deux ancrées dans le profil réel (cf.
 * `generate_likely_questions`/`generate_personal_pitch`), l'inverse des
 * questions à poser. Édition locale avant envoi : coller un long texte
 * ne doit pas déclencher une requête à chaque caractère. */
function DetailRow({
  application, onSetDescription, onSetInterviewDate, onGenerateQuestions, onGeneratePrep,
}: DetailRowProps) {
  const [draft, setDraft] = useState(application.description ?? "");
  const [dateDraft, setDateDraft] = useState(application.interview_date ?? "");
  const [generating, setGenerating] = useState(false);
  const [preparing, setPreparing] = useState(false);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      if (draft !== (application.description ?? "")) {
        onSetDescription(application.offer_id, draft);
      }
      await onGenerateQuestions(application.offer_id, draft || undefined);
    } finally {
      setGenerating(false);
    }
  };

  const handlePrepare = async () => {
    setPreparing(true);
    try {
      if (draft !== (application.description ?? "")) {
        onSetDescription(application.offer_id, draft);
      }
      await onGeneratePrep(application.offer_id, draft || undefined);
    } finally {
      setPreparing(false);
    }
  };

  return (
    <tr className={styles.detailRow}>
      <td colSpan={8}>
        <div className={styles.detailGrid}>
          <div className={styles.detailBlock}>
            <div className={styles.detailLabel}>Description de l'offre</div>
            <textarea
              className={styles.descriptionInput}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onBlur={() => {
                if (draft !== (application.description ?? "")) {
                  onSetDescription(application.offer_id, draft);
                }
              }}
              placeholder="Colle ici le texte de l'offre (optionnel, utilisé pour générer des questions pertinentes)."
              rows={6}
            />
          </div>
          <div className={styles.detailBlock}>
            <div className={styles.detailLabel}>Date proposée pour l'entretien</div>
            <input
              type="text"
              className={styles.interviewDateInput}
              value={dateDraft}
              onChange={(event) => setDateDraft(event.target.value)}
              onBlur={() => {
                if (dateDraft !== (application.interview_date ?? "")) {
                  onSetInterviewDate(application.offer_id, dateDraft);
                }
              }}
              placeholder="Ex. 20/10/2026 14h, à confirmer"
            />
          </div>
          <div className={styles.detailBlock}>
            <div className={styles.detailLabel}>Questions à poser au recruteur</div>
            {application.questions ? (
              <pre className={styles.questionsText}>{application.questions}</pre>
            ) : (
              <div className={styles.questionsEmpty}>Pas encore générées.</div>
            )}
            <button
              type="button"
              className={styles.generateButton}
              onClick={() => void handleGenerate()}
              disabled={generating}
            >
              {generating
                ? "Génération…"
                : application.questions
                  ? "Régénérer les questions"
                  : "Générer des questions"}
            </button>
          </div>
          <div className={styles.detailBlock}>
            <div className={styles.detailLabel}>Questions que le recruteur pourrait poser</div>
            {application.likely_questions ? (
              <pre className={styles.questionsText}>{application.likely_questions}</pre>
            ) : (
              <div className={styles.questionsEmpty}>Pas encore préparées.</div>
            )}
          </div>
          <div className={styles.detailBlock}>
            <div className={styles.detailLabel}>Ma présentation personnelle</div>
            {application.personal_pitch ? (
              <pre className={styles.questionsText}>{application.personal_pitch}</pre>
            ) : (
              <div className={styles.questionsEmpty}>Pas encore préparée.</div>
            )}
            <button
              type="button"
              className={styles.generateButton}
              onClick={() => void handlePrepare()}
              disabled={preparing}
            >
              {preparing
                ? "Préparation…"
                : application.likely_questions || application.personal_pitch
                  ? "Régénérer la préparation"
                  : "Préparer l'entretien"}
            </button>
          </div>
        </div>
      </td>
    </tr>
  );
}

export function Applications() {
  const {
    applications,
    loading,
    error,
    checkingReplies,
    setStatus,
    remove,
    checkReplies,
    setDescription,
    setInterviewDate,
    generateQuestions,
    generatePrep,
  } = useApplications();
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [checkMessage, setCheckMessage] = useState<string | null>(null);

  const handleDelete = (offerId: string) => {
    if (confirmingDelete !== offerId) {
      setConfirmingDelete(offerId);
      return;
    }
    setConfirmingDelete(null);
    void remove(offerId);
  };

  const handleCheckReplies = async () => {
    setCheckMessage(null);
    const result = await checkReplies();
    if (result === null) return;
    setCheckMessage(
      result.found.length === 0
        ? "Rien de nouveau."
        : `${result.found.length} nouvelle(s) réponse(s) trouvée(s).`
    );
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.title}>Mes candidatures</div>
          <div className={styles.subtitle}>
            Statut modifiable ici ou par AELYN ("marque ma candidature chez X comme entretien").
            Actualisé automatiquement.
          </div>
        </div>
        <div className={styles.headerActions}>
          {checkMessage ? <span className={styles.checkMessage}>{checkMessage}</span> : null}
          <button
            type="button"
            className={styles.refreshButton}
            onClick={() => void handleCheckReplies()}
            disabled={checkingReplies}
          >
            {checkingReplies ? "Vérification…" : "Actualiser (vérifier les réponses)"}
          </button>
        </div>
      </div>

      {error ? <div className={styles.error}>{error}</div> : null}

      <div className={styles.tableWrap}>
        {loading ? (
          <EmptyState icon="applications" title="Chargement…" compact />
        ) : applications.length === 0 ? (
          <EmptyState
            icon="applications"
            title="Aucune candidature suivie pour le moment"
            description={'Chaque envoi par mail ("postule par mail chez X") apparaîtra ici automatiquement.'}
          />
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Postulé le</th>
                <th>Intitulé</th>
                <th>Entreprise</th>
                <th>Statut</th>
                <th>Entretien proposé</th>
                <th>Mis à jour</th>
                <th>Notes</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {applications.map((application) => (
                <Fragment key={application.offer_id}>
                  <tr
                    className={styles.row}
                    onClick={() =>
                      setExpandedId((current) =>
                        current === application.offer_id ? null : application.offer_id
                      )
                    }
                  >
                    <td className={styles.date}>{formatTimestamp(application.applied_at)}</td>
                    <td className={styles.titleCell}>{application.title}</td>
                    <td>{application.company || "—"}</td>
                    <td onClick={(event) => event.stopPropagation()}>
                      <div className={styles.statusCell}>
                        <Badge kind={STATUS_BADGE[application.status]}>
                          {application.status_label}
                        </Badge>
                        <select
                          className={styles.select}
                          value={application.status}
                          onChange={(event) =>
                            void setStatus(
                              application.offer_id,
                              event.target.value as ApplicationStatus
                            )
                          }
                          aria-label={`Statut de la candidature ${application.title}`}
                        >
                          {STATUS_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    </td>
                    <td className={styles.date}>{application.interview_date || "—"}</td>
                    <td className={styles.date}>{formatTimestamp(application.updated_at)}</td>
                    <td className={styles.notes}>{application.notes || "—"}</td>
                    <td onClick={(event) => event.stopPropagation()}>
                      <button
                        type="button"
                        className={[
                          styles.deleteButton,
                          confirmingDelete === application.offer_id ? styles.deleteButtonConfirm : "",
                        ].join(" ")}
                        onClick={() => handleDelete(application.offer_id)}
                        onBlur={() => setConfirmingDelete(null)}
                      >
                        {confirmingDelete === application.offer_id ? "Confirmer ?" : "Retirer"}
                      </button>
                    </td>
                  </tr>
                  {expandedId === application.offer_id ? (
                    <DetailRow
                      key={`${application.offer_id}-detail`}
                      application={application}
                      onSetDescription={(offerId, description) =>
                        void setDescription(offerId, description)
                      }
                      onSetInterviewDate={(offerId, interviewDate) =>
                        void setInterviewDate(offerId, interviewDate)
                      }
                      onGenerateQuestions={(offerId, description) =>
                        generateQuestions(offerId, description)
                      }
                      onGeneratePrep={(offerId, description) =>
                        generatePrep(offerId, description)
                      }
                    />
                  ) : null}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

import { useState } from "react";
import { Badge, type BadgeKind } from "../components/ui/Badge";
import { EmptyState } from "../components/ui/EmptyState";
import { formatTimestamp } from "../lib/time";
import { useApplications } from "../lib/useApplications";
import type { ApplicationStatus } from "../lib/api";
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

export function Applications() {
  const { applications, loading, error, setStatus, remove } = useApplications();
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null);

  const handleDelete = (offerId: string) => {
    if (confirmingDelete !== offerId) {
      setConfirmingDelete(offerId);
      return;
    }
    setConfirmingDelete(null);
    void remove(offerId);
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>Mes candidatures</div>
        <div className={styles.subtitle}>
          Statut modifiable ici ou par AELYN ("marque ma candidature chez X comme entretien").
          Actualisé automatiquement.
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
                <th>Mis à jour</th>
                <th>Notes</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {applications.map((application) => (
                <tr key={application.offer_id}>
                  <td className={styles.date}>{formatTimestamp(application.applied_at)}</td>
                  <td className={styles.titleCell}>{application.title}</td>
                  <td>{application.company || "—"}</td>
                  <td>
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
                  <td className={styles.date}>{formatTimestamp(application.updated_at)}</td>
                  <td className={styles.notes}>{application.notes || "—"}</td>
                  <td>
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
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

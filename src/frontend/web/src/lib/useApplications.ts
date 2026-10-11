import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  deleteApplication,
  getApplications,
  updateApplication,
  type ApiApplication,
  type ApplicationStatus,
} from "./api";

/** Mêmes principes que `useActivityEntries` (poll régulier, pas de
 * fallback inventé) : AELYN peut modifier ce suivi depuis le chat/la
 * voix à tout moment (ex. "marque ma candidature chez X comme
 * entretien"), donc la page doit refléter ces changements même sans
 * action de l'utilisateur dans cet onglet. Pas de store "local"
 * équivalent à `localActivity` : sans backend joignable il n'y a
 * simplement rien de significatif à montrer (une candidature n'existe
 * que dans la vraie base de suivi), contrairement au journal d'activité
 * qui a un sens même hors-ligne. */
export function useApplications() {
  const [applications, setApplications] = useState<ApiApplication[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const refreshing = useRef(false);

  const refresh = useCallback(async () => {
    if (refreshing.current) return;
    refreshing.current = true;
    try {
      const entries = await getApplications();
      setApplications(entries);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "AELYN Core injoignable.");
    } finally {
      setLoading(false);
      refreshing.current = false;
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  /** Mise à jour optimiste : la ligne change de statut immédiatement au
   * clic, sans attendre le prochain cycle de poll (15s, perceptible). En
   * cas d'échec serveur, `refresh()` resynchronise sur le vrai état
   * plutôt que de laisser la ligne dans un état local jamais confirmé. */
  const setStatus = useCallback(
    async (offerId: string, status: ApplicationStatus) => {
      setApplications((prev) =>
        prev.map((a) => (a.offer_id === offerId ? { ...a, status } : a))
      );
      try {
        const updated = await updateApplication(offerId, { status });
        setApplications((prev) =>
          prev.map((a) => (a.offer_id === offerId ? updated : a))
        );
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Mise à jour impossible.");
        await refresh();
      }
    },
    [refresh]
  );

  const remove = useCallback(
    async (offerId: string) => {
      const previous = applications;
      setApplications((prev) => prev.filter((a) => a.offer_id !== offerId));
      try {
        await deleteApplication(offerId);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Suppression impossible.");
        setApplications(previous);
      }
    },
    [applications]
  );

  return { applications, loading, error, refresh, setStatus, remove };
}

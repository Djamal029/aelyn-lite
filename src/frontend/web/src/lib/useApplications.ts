import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  checkApplicationReplies,
  deleteApplication,
  generateApplicationQuestions,
  generateInterviewPrep,
  getApplications,
  updateApplication,
  type ApiApplication,
  type ApplicationStatus,
  type CheckRepliesResult,
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
  const [checkingReplies, setCheckingReplies] = useState(false);
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

  /** Relit les mails récents côté backend (lus ou non) pour y chercher
   * des réponses de recruteurs, jamais les mêmes mails deux fois (cf.
   * `check_application_replies`, dédoublonné via le journal) : un clic
   * répété sur "Actualiser" ne refacture donc jamais le même mail. */
  const checkReplies = useCallback(async (): Promise<CheckRepliesResult | null> => {
    setCheckingReplies(true);
    try {
      const result = await checkApplicationReplies();
      await refresh();
      setError(null);
      return result;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Vérification des réponses impossible.");
      return null;
    } finally {
      setCheckingReplies(false);
    }
  }, [refresh]);

  const setDescription = useCallback(
    async (offerId: string, description: string) => {
      try {
        const updated = await updateApplication(offerId, { description });
        setApplications((prev) => prev.map((a) => (a.offer_id === offerId ? updated : a)));
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Mise à jour impossible.");
      }
    },
    []
  );

  const setInterviewDate = useCallback(
    async (offerId: string, interviewDate: string) => {
      try {
        const updated = await updateApplication(offerId, { interview_date: interviewDate });
        setApplications((prev) => prev.map((a) => (a.offer_id === offerId ? updated : a)));
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Mise à jour impossible.");
      }
    },
    []
  );

  const generateQuestions = useCallback(async (offerId: string, description?: string) => {
    try {
      const updated = await generateApplicationQuestions(offerId, description);
      setApplications((prev) => prev.map((a) => (a.offer_id === offerId ? updated : a)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Génération des questions impossible.");
    }
  }, []);

  const generatePrep = useCallback(async (offerId: string, description?: string) => {
    try {
      const updated = await generateInterviewPrep(offerId, description);
      setApplications((prev) => prev.map((a) => (a.offer_id === offerId ? updated : a)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Préparation de l'entretien impossible.");
    }
  }, []);

  return {
    applications,
    loading,
    error,
    checkingReplies,
    refresh,
    setStatus,
    remove,
    checkReplies,
    setDescription,
    setInterviewDate,
    generateQuestions,
    generatePrep,
  };
}

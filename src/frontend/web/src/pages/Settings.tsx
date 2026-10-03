import { useEffect, useState, type FormEvent } from "react";
import { Panel } from "../components/ui/Panel";
import { StatusDot } from "../components/ui/StatusDot";
import { Badge } from "../components/ui/Badge";
import { configGroups } from "../mocks/config";
import { LITE_MODE } from "../lib/liteMode";
import { getAelynTheme, setAelynTheme, THEME_OPTIONS, type AelynTheme } from "../lib/theme";
import { verifyPasskey } from "../lib/passkey";
import {
  ApiError,
  authSettings,
  getHealth,
  getSettings,
  setAllowAutonomousSend,
  patchSettings,
  getSettingsModels,
  getCareerProfile,
  putCareerProfile,
  type ApiSettings,
  type SettingsPatch,
} from "../lib/api";
import styles from "./Settings.module.css";

/** Keys in the static .env.example reflection (mocks/config.ts) that the
 * real `GET /settings` also exposes as plain read-only values (not an
 * editable field of its own, see EditableFieldsPanel/ModelsPanel for
 * those): when the API is reachable, these rows show the live value
 * (with a LIVE badge) instead of the static placeholder. */
const LIVE_KEY_MAP: Partial<Record<string, keyof ApiSettings>> = {
  USER_NAME: "user_name",
  OLLAMA_HOST: "ollama_host",
};

const CANDIDATE_LEVELS = ["stage", "junior", "senior", "postdoc"] as const;

interface EditableDraft {
  wake_timeout_seconds: string;
  camera_entree_index: string;
  camera_salon_index: string;
  candidate_level: string;
  weight_score_txt_match: string;
  weight_score_cos: string;
  face_match_threshold: string;
  keywords: string;
  department: string;
}

function draftFromSettings(s: ApiSettings): EditableDraft {
  return {
    wake_timeout_seconds: String(s.wake_timeout_seconds),
    camera_entree_index: s.camera_entree_index === null ? "" : String(s.camera_entree_index),
    camera_salon_index: s.camera_salon_index === null ? "" : String(s.camera_salon_index),
    candidate_level: s.candidate_level,
    weight_score_txt_match: String(s.weight_score_txt_match),
    weight_score_cos: String(s.weight_score_cos),
    face_match_threshold: String(s.face_match_threshold),
    keywords: s.keywords.join(", "),
    department: s.department.join(", "),
  };
}

/** Settings page: reads real config from `aelyn-api`'s `GET /settings`
 * when it's reachable (falling back to the static .env.example
 * reflection otherwise, clearly marked), and gates every mutating
 * endpoint behind the real passkey flow (`POST /settings/auth`):
 * unlock -> hold the bearer token in memory only (never localStorage) ->
 * attach it to every PATCH/PUT -> re-prompt on 401. When the API isn't
 * running locally, the lock/unlock interaction still works against
 * `lib/passkey.ts`'s offline demo stub, but actually saving a field, a
 * model choice, or the career profile all genuinely require the live
 * backend (there's no offline-demo write path for those, unlike the
 * single legacy ALLOW_AUTONOMOUS_SEND toggle). */
export function Settings() {
  const [theme, setTheme] = useState<AelynTheme>(() => getAelynTheme());
  const [live, setLive] = useState(false);
  const [apiSettings, setApiSettings] = useState<ApiSettings | null>(null);
  const [editingDisabled, setEditingDisabled] = useState(false);

  const [unlocked, setUnlocked] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [passkey, setPasskey] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [autonomousSend, setAutonomousSendState] = useState(false);
  const [saving, setSaving] = useState(false);

  // ---- generic editable fields (PATCH /settings) ------------------------
  const [draft, setDraft] = useState<EditableDraft | null>(null);
  const [fieldsSaving, setFieldsSaving] = useState(false);
  const [fieldsSaved, setFieldsSaved] = useState(false);
  const [fieldsError, setFieldsError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // ---- LLM model selection (PATCH /settings, its own save state) -------
  const [models, setModels] = useState<string[]>([]);
  const [modelDraft, setModelDraft] = useState({ llm_model: "", llm_model_heavy: "", llm_model_career: "" });
  const [modelsSaving, setModelsSaving] = useState(false);
  const [modelsSaved, setModelsSaved] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);

  // ---- profil.json editor (GET/PUT /career/profile) ---------------------
  const [profileText, setProfileText] = useState<string | null>(null);
  const [profileLoadError, setProfileLoadError] = useState<string | null>(null);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const reachable = await getHealth();
      if (cancelled) return;
      setLive(reachable);
      if (!reachable) return;
      try {
        const s = await getSettings();
        if (cancelled) return;
        setApiSettings(s);
        setAutonomousSendState(s.allow_autonomous_send);
        setDraft(draftFromSettings(s));
        setModelDraft({ llm_model: s.llm_model, llm_model_heavy: s.llm_model_heavy, llm_model_career: s.llm_model_career });
      } catch {
        if (!cancelled) setLive(false);
        return;
      }
      try {
        const { models: m } = await getSettingsModels();
        if (!cancelled) setModels(m);
      } catch {
        // the models dropdown just shows "aucun modèle" below; not fatal
      }
      try {
        const profile = await getCareerProfile();
        if (!cancelled) setProfileText(JSON.stringify(profile, null, 2));
      } catch (err) {
        if (!cancelled) setProfileLoadError(err instanceof ApiError ? err.message : "profil.json injoignable.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleUnlock = async (e: FormEvent) => {
    e.preventDefault();
    if (!passkey.trim()) return;
    setChecking(true);
    setError(null);
    try {
      if (live) {
        const { token: t } = await authSettings(passkey);
        setToken(t);
        setUnlocked(true);
        setPasskey("");
      } else {
        const ok = await verifyPasskey(passkey);
        if (ok) {
          setUnlocked(true);
          setPasskey("");
        } else {
          setError("Passkey incorrecte.");
        }
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setEditingDisabled(true);
        setError("Édition désactivée sur cette installation (aucune passkey configurée côté serveur).");
      } else if (err instanceof ApiError && err.status === 401) {
        setError("Passkey incorrecte.");
      } else {
        setError("AELYN Core injoignable, passkey non vérifiée.");
      }
    } finally {
      setChecking(false);
    }
  };

  const handleLock = () => {
    setUnlocked(false);
    setToken(null);
    setPasskey("");
    setError(null);
  };

  /** Shared by every save handler below: a 401 means the token expired
   * mid-session (the passkey flow's own 15-minute TTL), so re-lock and
   * say so plainly rather than leaving the form stuck silently failing. */
  const handleSessionExpired = (): boolean => {
    setUnlocked(false);
    setToken(null);
    return true;
  };

  const handleToggleAutonomousSend = async (checked: boolean) => {
    if (!live) {
      // Offline demo path: local-only state, matches the pre-API
      // behavior exactly.
      setAutonomousSendState(checked);
      return;
    }
    if (!token) return;
    setSaving(true);
    const previous = autonomousSend;
    setAutonomousSendState(checked);
    try {
      const res = await setAllowAutonomousSend(checked, token);
      setAutonomousSendState(res.allow_autonomous_send);
    } catch (err) {
      setAutonomousSendState(previous);
      if (err instanceof ApiError && err.status === 401) {
        handleSessionExpired();
        setError("Session expirée, ressaisis la passkey.");
      } else {
        setError("Échec de la mise à jour, AELYN Core injoignable.");
      }
    } finally {
      setSaving(false);
    }
  };

  const handleSaveFields = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !draft) return;
    setFieldsSaving(true);
    setFieldsSaved(false);
    setFieldsError(null);
    setFieldErrors({});
    const body: SettingsPatch = {
      wake_timeout_seconds: Number(draft.wake_timeout_seconds),
      camera_entree_index: Number(draft.camera_entree_index),
      camera_salon_index: Number(draft.camera_salon_index),
      candidate_level: draft.candidate_level,
      weight_score_txt_match: Number(draft.weight_score_txt_match),
      weight_score_cos: Number(draft.weight_score_cos),
      face_match_threshold: Number(draft.face_match_threshold),
      keywords: draft.keywords.split(",").map((s) => s.trim()).filter(Boolean),
      department: draft.department.split(",").map((s) => s.trim()).filter(Boolean),
    };
    try {
      const updated = await patchSettings(body, token);
      setApiSettings(updated);
      setDraft(draftFromSettings(updated));
      setFieldsSaved(true);
      window.setTimeout(() => setFieldsSaved(false), 2400);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        handleSessionExpired();
        setFieldsError("Session expirée, ressaisis la passkey.");
      } else if (err instanceof ApiError && err.fieldErrors) {
        const perField: Record<string, string> = {};
        for (const fe of err.fieldErrors) perField[String(fe.loc[fe.loc.length - 1])] = fe.msg;
        setFieldErrors(perField);
        setFieldsError("Un ou plusieurs champs sont invalides ; rien n'a été enregistré.");
      } else {
        setFieldsError(err instanceof ApiError ? err.message : "Échec de l'enregistrement.");
      }
    } finally {
      setFieldsSaving(false);
    }
  };

  const handleSaveModels = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setModelsSaving(true);
    setModelsSaved(false);
    setModelsError(null);
    try {
      const updated = await patchSettings(modelDraft, token);
      setApiSettings(updated);
      setModelsSaved(true);
      window.setTimeout(() => setModelsSaved(false), 2400);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        handleSessionExpired();
        setModelsError("Session expirée, ressaisis la passkey.");
      } else if (err instanceof ApiError && err.fieldErrors) {
        setModelsError(err.fieldErrors.map((fe) => fe.msg).join(" "));
      } else {
        setModelsError(err instanceof ApiError ? err.message : "Échec de l'enregistrement.");
      }
    } finally {
      setModelsSaving(false);
    }
  };

  const handleSaveProfile = async () => {
    if (!token || profileText === null) return;
    setProfileSaving(true);
    setProfileSaved(false);
    setProfileError(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(profileText);
    } catch (err) {
      setProfileSaving(false);
      setProfileError(`JSON invalide : ${err instanceof Error ? err.message : "erreur de syntaxe"}.`);
      return;
    }
    try {
      await putCareerProfile(parsed, token);
      setProfileSaved(true);
      window.setTimeout(() => setProfileSaved(false), 2400);
    } catch (err) {
      // Deliberately never touches `profileText` on failure: the user's
      // edit (valid JSON or not) stays exactly as typed so a rejected
      // save doesn't also cost them their work.
      if (err instanceof ApiError && err.status === 401) {
        handleSessionExpired();
        setProfileError("Session expirée, ressaisis la passkey.");
      } else if (err instanceof ApiError && err.fieldErrors) {
        setProfileError(err.fieldErrors.map((fe) => fe.msg).join("\n"));
      } else {
        setProfileError(err instanceof ApiError ? err.message : "Échec de l'enregistrement.");
      }
    } finally {
      setProfileSaving(false);
    }
  };

  const displayValue = (key: string, fallback: string): { value: string; isLive: boolean } => {
    const liveKey = LIVE_KEY_MAP[key];
    if (live && liveKey && apiSettings) {
      const v = apiSettings[liveKey];
      return { value: String(v), isLive: true };
    }
    return { value: fallback, isLive: false };
  };

  return (
    <div className={styles.page}>
      <Panel title="Apparence" meta={<span>Choix conservé sur cet appareil</span>}>
        <p className={styles.themeHint}>Choisissez l’ambiance qui vous convient. Vous pourrez la changer à tout moment.</p>
        <div className={styles.themeGrid} role="group" aria-label="Thème de l’application">
          {THEME_OPTIONS.map((option) => (
            <button
              className={[styles.themeOption, theme === option.id ? styles.themeOptionSelected : ""].join(" ")}
              key={option.id}
              type="button"
              aria-pressed={theme === option.id}
              onClick={() => {
                setAelynTheme(option.id);
                setTheme(option.id);
              }}
            >
              <span className={[styles.themeSwatch, styles[`swatch_${option.id}`]].join(" ")} aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
              <span className={styles.themeName}>{option.label}</span>
              <span className={styles.themeNote}>{option.note}</span>
            </button>
          ))}
        </div>
      </Panel>

      <div className={styles.notice}>
        {live
          ? "Connecté à AELYN Core (aelyn-api) : les champs marqués LIVE viennent de GET /settings ; le reste reflète src/backend/.env.example (pas encore exposé par l'API)."
          : "AELYN Core (aelyn-api) injoignable sur " +
            "cette machine, valeurs d'exemple depuis src/backend/.env.example. Lance `uv run uvicorn aelyn_api.main:app --reload` depuis src/backend pour voir les valeurs réelles."}
      </div>

      <Panel
        title="Verrou des réglages"
        meta={
          <span className={styles.lockState}>
            <StatusDot kind={unlocked ? "active" : "neutral"} />
            {unlocked ? "Déverrouillé" : "Verrouillé"}
          </span>
        }
      >
        {editingDisabled ? (
          <p className={styles.lockHint}>
            L'édition des réglages est désactivée sur cette installation d'aelyn-api (aucun{" "}
            <code>SETTINGS_PASSKEY</code> configuré côté serveur).
          </p>
        ) : unlocked ? (
          <div className={styles.unlockedRow}>
            <span className={styles.unlockedText}>
              {live
                ? "Édition autorisée pour 15 minutes (jeton en mémoire, non persisté)."
                : "Édition autorisée pour cette session (mode démo hors-ligne), rien n'est persisté."}
            </span>
            <button type="button" className={styles.lockButton} onClick={handleLock}>
              Reverrouiller
            </button>
          </div>
        ) : (
          <form className={styles.lockForm} onSubmit={handleUnlock}>
            <p className={styles.lockHint}>
              {live
                ? "Toute modification d'un réglage nécessite une passkey, vérifiée par AELYN Core (POST /settings/auth)."
                : "AELYN Core injoignable, passkey vérifiée localement (démo hors-ligne uniquement)."}
            </p>
            <div className={styles.lockRow}>
              <input
                type="password"
                className={styles.lockInput}
                placeholder="Passkey"
                value={passkey}
                onChange={(e) => setPasskey(e.target.value)}
                autoComplete="off"
              />
              <button type="submit" className={styles.lockButton} disabled={checking || !passkey.trim()}>
                {checking ? "Vérification…" : "Déverrouiller"}
              </button>
            </div>
            {error ? <div className={styles.lockError}>{error}</div> : null}
          </form>
        )}
      </Panel>

      {live && draft ? (
        <Panel
          title="Réglages modifiables"
          meta={!unlocked ? <span className={styles.lockNote}>déverrouille pour modifier</span> : undefined}
        >
          <form className={styles.editForm} onSubmit={handleSaveFields}>
            <div className={styles.fieldGrid}>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>WAKE_TIMEOUT_SECONDS</span>
                <input
                  type="number"
                  min={10}
                  max={3600}
                  className={styles.fieldInput}
                  disabled={!unlocked || fieldsSaving}
                  value={draft.wake_timeout_seconds}
                  onChange={(e) => setDraft({ ...draft, wake_timeout_seconds: e.target.value })}
                />
                {fieldErrors.wake_timeout_seconds ? (
                  <span className={styles.fieldError}>{fieldErrors.wake_timeout_seconds}</span>
                ) : null}
              </label>

              {!LITE_MODE ? <label className={styles.field}>
                <span className={styles.fieldLabel}>CAMERA_ENTREE_INDEX</span>
                <input
                  type="number"
                  min={0}
                  className={styles.fieldInput}
                  disabled={!unlocked || fieldsSaving}
                  value={draft.camera_entree_index}
                  onChange={(e) => setDraft({ ...draft, camera_entree_index: e.target.value })}
                />
                {fieldErrors.camera_entree_index ? (
                  <span className={styles.fieldError}>{fieldErrors.camera_entree_index}</span>
                ) : null}
              </label> : null}

              {!LITE_MODE ? <label className={styles.field}>
                <span className={styles.fieldLabel}>CAMERA_SALON_INDEX</span>
                <input
                  type="number"
                  min={0}
                  className={styles.fieldInput}
                  disabled={!unlocked || fieldsSaving}
                  value={draft.camera_salon_index}
                  onChange={(e) => setDraft({ ...draft, camera_salon_index: e.target.value })}
                />
                {fieldErrors.camera_salon_index ? (
                  <span className={styles.fieldError}>{fieldErrors.camera_salon_index}</span>
                ) : null}
              </label> : null}

              <label className={styles.field}>
                <span className={styles.fieldLabel}>CANDIDATE_LEVEL</span>
                <select
                  className={styles.fieldInput}
                  disabled={!unlocked || fieldsSaving}
                  value={draft.candidate_level}
                  onChange={(e) => setDraft({ ...draft, candidate_level: e.target.value })}
                >
                  {CANDIDATE_LEVELS.map((lvl) => (
                    <option key={lvl} value={lvl}>
                      {lvl}
                    </option>
                  ))}
                </select>
                {fieldErrors.candidate_level ? <span className={styles.fieldError}>{fieldErrors.candidate_level}</span> : null}
              </label>

              <label className={styles.field}>
                <span className={styles.fieldLabel}>WEIGHT_SCORE_TXT_MATCH</span>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  className={styles.fieldInput}
                  disabled={!unlocked || fieldsSaving}
                  value={draft.weight_score_txt_match}
                  onChange={(e) => setDraft({ ...draft, weight_score_txt_match: e.target.value })}
                />
                <span className={styles.fieldNote}>pondération BM25 (0-1)</span>
                {fieldErrors.weight_score_txt_match ? (
                  <span className={styles.fieldError}>{fieldErrors.weight_score_txt_match}</span>
                ) : null}
              </label>

              <label className={styles.field}>
                <span className={styles.fieldLabel}>WEIGHT_SCORE_COS</span>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  className={styles.fieldInput}
                  disabled={!unlocked || fieldsSaving}
                  value={draft.weight_score_cos}
                  onChange={(e) => setDraft({ ...draft, weight_score_cos: e.target.value })}
                />
                <span className={styles.fieldNote}>pondération cosinus (0-1)</span>
                {fieldErrors.weight_score_cos ? <span className={styles.fieldError}>{fieldErrors.weight_score_cos}</span> : null}
              </label>

              {!LITE_MODE ? <label className={styles.field}>
                <span className={styles.fieldLabel}>FACE_MATCH_THRESHOLD</span>
                <input
                  type="number"
                  min={0}
                  max={2}
                  step={0.01}
                  className={styles.fieldInput}
                  disabled={!unlocked || fieldsSaving}
                  value={draft.face_match_threshold}
                  onChange={(e) => setDraft({ ...draft, face_match_threshold: e.target.value })}
                />
                <span className={styles.fieldNote}>seuil ArcFace</span>
                {fieldErrors.face_match_threshold ? (
                  <span className={styles.fieldError}>{fieldErrors.face_match_threshold}</span>
                ) : null}
              </label> : null}

              <label className={[styles.field, styles.fieldWide].join(" ")}>
                <span className={styles.fieldLabel}>KEYWORDS</span>
                <input
                  type="text"
                  className={styles.fieldInput}
                  disabled={!unlocked || fieldsSaving}
                  value={draft.keywords}
                  onChange={(e) => setDraft({ ...draft, keywords: e.target.value })}
                  placeholder="Data Scientist, Machine Learning"
                />
                <span className={styles.fieldNote}>séparés par des virgules</span>
                {fieldErrors.keywords ? <span className={styles.fieldError}>{fieldErrors.keywords}</span> : null}
              </label>

              <label className={[styles.field, styles.fieldWide].join(" ")}>
                <span className={styles.fieldLabel}>DEPARTMENT</span>
                <input
                  type="text"
                  className={styles.fieldInput}
                  disabled={!unlocked || fieldsSaving}
                  value={draft.department}
                  onChange={(e) => setDraft({ ...draft, department: e.target.value })}
                  placeholder="35, 75"
                />
                <span className={styles.fieldNote}>codes département, séparés par des virgules</span>
                {fieldErrors.department ? <span className={styles.fieldError}>{fieldErrors.department}</span> : null}
              </label>
            </div>

            <div className={styles.saveRow}>
              <button type="submit" className={styles.saveButton} disabled={!unlocked || fieldsSaving}>
                {fieldsSaving ? "Enregistrement…" : "Enregistrer les modifications"}
              </button>
              {fieldsSaved ? <span className={styles.saveSuccess}>Enregistré.</span> : null}
              {fieldsError ? <span className={styles.lockError}>{fieldsError}</span> : null}
            </div>
          </form>
        </Panel>
      ) : null}

      {live ? (
        <Panel
          title="Modèles LLM"
          meta={!unlocked ? <span className={styles.lockNote}>déverrouille pour modifier</span> : undefined}
        >
          <form className={styles.editForm} onSubmit={handleSaveModels}>
            {models.length === 0 ? (
              <p className={styles.lockHint}>
                Aucun modèle Ollama détecté (service injoignable, ou <code>ollama list</code> vide) : impossible de
                proposer un vrai choix pour l'instant.
              </p>
            ) : (
              <div className={styles.fieldGrid}>
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>LLM_MODEL</span>
                  <select
                    className={styles.fieldInput}
                    disabled={!unlocked || modelsSaving}
                    value={modelDraft.llm_model}
                    onChange={(e) => setModelDraft({ ...modelDraft, llm_model: e.target.value })}
                  >
                    {models.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                  <span className={styles.fieldNote}>modèle léger, routage d'intention par défaut</span>
                </label>

                <label className={styles.field}>
                  <span className={styles.fieldLabel}>LLM_MODEL_HEAVY</span>
                  <select
                    className={styles.fieldInput}
                    disabled={!unlocked || modelsSaving}
                    value={modelDraft.llm_model_heavy}
                    onChange={(e) => setModelDraft({ ...modelDraft, llm_model_heavy: e.target.value })}
                  >
                    {models.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                  <span className={styles.fieldNote}>escalade routage d'intention</span>
                </label>

                <label className={styles.field}>
                  <span className={styles.fieldLabel}>LLM_MODEL_CAREER</span>
                  <select
                    className={styles.fieldInput}
                    disabled={!unlocked || modelsSaving}
                    value={modelDraft.llm_model_career}
                    onChange={(e) => setModelDraft({ ...modelDraft, llm_model_career: e.target.value })}
                  >
                    {models.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                  <span className={styles.fieldNote}>génération CV / lettre de motivation</span>
                </label>
              </div>
            )}

            <div className={styles.saveRow}>
              <button type="submit" className={styles.saveButton} disabled={!unlocked || modelsSaving || models.length === 0}>
                {modelsSaving ? "Enregistrement…" : "Enregistrer les modèles"}
              </button>
              {modelsSaved ? <span className={styles.saveSuccess}>Enregistré.</span> : null}
              {modelsError ? <span className={styles.lockError}>{modelsError}</span> : null}
            </div>
          </form>
        </Panel>
      ) : null}

      {live ? (
        <Panel
          title="Profil carrière (profil.json)"
          meta={!unlocked ? <span className={styles.lockNote}>déverrouille pour modifier</span> : undefined}
        >
          {profileLoadError ? (
            <p className={styles.lockHint}>{profileLoadError}</p>
          ) : profileText === null ? (
            <p className={styles.lockHint}>Chargement de profil.json…</p>
          ) : (
            <div className={styles.editForm}>
              <p className={styles.lockHint}>
                Édité comme du JSON brut (pas un formulaire par champ) : la structure doit rester celle que
                CV/lettre de motivation attendent (expériences, projets, formation, …). Une sauvegarde invalide est
                refusée avant écriture, ton édition reste affichée telle quelle pour corriger.
              </p>
              <textarea
                className={styles.jsonEditor}
                spellCheck={false}
                disabled={!unlocked || profileSaving}
                value={profileText}
                onChange={(e) => setProfileText(e.target.value)}
              />
              <div className={styles.saveRow}>
                <button type="button" className={styles.saveButton} disabled={!unlocked || profileSaving} onClick={handleSaveProfile}>
                  {profileSaving ? "Enregistrement…" : "Enregistrer profil.json"}
                </button>
                {profileSaved ? <span className={styles.saveSuccess}>Enregistré (sauvegarde : profil.json.bak).</span> : null}
                {profileError ? <span className={[styles.lockError, styles.profileError].join(" ")}>{profileError}</span> : null}
              </div>
            </div>
          )}
        </Panel>
      ) : null}

      <div className={styles.grid}>
        {(LITE_MODE
          ? configGroups.filter((group) => !/sécurité|security|face|vision|caméra/i.test(group.title + group.entries.map((entry) => entry.key).join(" ")))
          : configGroups
        ).map((group) => (
          <Panel title={group.title} key={group.title}>
            {group.entries.map((entry) => {
              if (entry.key === "ALLOW_AUTONOMOUS_SEND") {
                return (
                  <label
                    className={[styles.row, styles.toggleRow, !unlocked ? styles.toggleRowLocked : ""].join(" ")}
                    key={entry.key}
                  >
                    <span className={styles.key}>
                      {entry.key} {live ? <Badge kind="active">live</Badge> : null}
                    </span>
                    <span className={styles.valueGroup}>
                      <span className={styles.toggle}>
                        <input
                          type="checkbox"
                          checked={autonomousSend}
                          disabled={!unlocked || saving}
                          onChange={(e) => handleToggleAutonomousSend(e.target.checked)}
                        />
                        {autonomousSend ? "true" : "false"}
                      </span>
                      {entry.note ? <span className={styles.note}>{entry.note}</span> : null}
                      {!unlocked ? <span className={styles.note}>déverrouille pour modifier</span> : null}
                    </span>
                  </label>
                );
              }
              const { value, isLive } = displayValue(entry.key, entry.value);
              return (
                <div className={styles.row} key={entry.key}>
                  <span className={styles.key}>
                    {entry.key} {isLive ? <Badge kind="active">live</Badge> : null}
                  </span>
                  <span className={styles.valueGroup}>
                    <span className={styles.value}>{value}</span>
                    {entry.note ? <span className={styles.note}>{entry.note}</span> : null}
                  </span>
                </div>
              );
            })}
          </Panel>
        ))}

        {live && apiSettings && !LITE_MODE ? (
          <Panel title="Caméras locales (aelyn-api)">
            <div className={styles.row}>
              <span className={styles.key}>
                TV_CONFIGURED <Badge kind="active">live</Badge>
              </span>
              <span className={styles.valueGroup}>
                <span className={styles.value}>{String(apiSettings.tv_configured)}</span>
              </span>
            </div>
            <div className={styles.row}>
              <span className={styles.key}>Index caméras</span>
              <span className={styles.valueGroup}>
                <span className={styles.note}>Modifiables dans « Réglages modifiables » ci-dessus.</span>
              </span>
            </div>
          </Panel>
        ) : null}
      </div>
    </div>
  );
}

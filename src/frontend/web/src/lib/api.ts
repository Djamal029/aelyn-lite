/** Typed client for the real AELYN backend (`aelyn-api`, FastAPI,
 * src/backend/aelyn-api). Every function here calls a genuinely running
 * service (IMAP, France Travail, Ollama, Freebox/Android TV, a local
 * OpenCV webcam, SQLite chat history); there is no mocking inside this
 * file. Callers are expected to fall back to the existing realistic
 * mocks (src/mocks) when the API is unreachable (dev machine without
 * the backend running), rather than this module pretending to succeed.
 *
 * Base URL: `VITE_API_BASE_URL`, defaulting to `http://localhost:8000`
 * (the API's own default `uvicorn` bind). CORS is wide open on the API
 * during this phase, per the backend agent. */
const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") || "http://localhost:8000";

/** FastAPI's per-field validation error shape (`detail: [...]` on a 422),
 * e.g. from `PATCH /settings` or `PUT /career/profile`: `loc` is the
 * field path (`["body", "wake_timeout_seconds"]`), `msg` is a message
 * already meant to be read by a human. */
export interface ApiFieldError {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export class ApiError extends Error {
  status: number;
  /** Present only for a 422 whose `detail` was the FastAPI field-error
   * array (not every error is shaped this way: a 401/503/network error
   * still just has `message`). Callers that want to highlight a specific
   * input, not just show one generic error string, read this. */
  fieldErrors?: ApiFieldError[];
  constructor(status: number, message: string, fieldErrors?: ApiFieldError[]) {
    super(message);
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.name = "ApiError";
  }
}

/** `detail` on an error response is either a plain string (most
 * endpoints) or FastAPI's validation array (422s built from a Pydantic
 * validator or an explicit `HTTPException(422, detail=[...])`, e.g.
 * `PATCH /settings`/`PUT /career/profile`). Building one readable string
 * either way means every caller gets a sane `err.message` for free,
 * while `fieldErrors` carries the structured version for callers that
 * want to point at a specific field instead. */
function describeErrorDetail(detail: unknown, fallback: string): { message: string; fieldErrors?: ApiFieldError[] } {
  if (typeof detail === "string" && detail) return { message: detail };
  if (Array.isArray(detail) && detail.length > 0 && detail.every((e) => e && typeof e.msg === "string")) {
    const fieldErrors = detail as ApiFieldError[];
    const message = fieldErrors
      .map((e) => {
        const field = e.loc[e.loc.length - 1];
        return typeof field === "string" && field !== "body" ? `${field} : ${e.msg}` : e.msg;
      })
      .join(" ; ");
    return { message, fieldErrors };
  }
  return { message: fallback };
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT";
  body?: unknown;
  token?: string;
  /** Most calls are quick reads (short default timeout so an
   * unreachable backend fails fast and the UI can fall back to mocks).
   * The CV-generation and email-summary endpoints are real LLM calls
   * the backend agent measured at 30s-2min; those pass a longer one. */
  timeoutMs?: number;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, token, timeoutMs = 6000 } = options;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    if (!res.ok) {
      let message = res.statusText;
      let fieldErrors: ApiFieldError[] | undefined;
      try {
        const data = await res.json();
        ({ message, fieldErrors } = describeErrorDetail(data?.detail, message));
      } catch {
        // response wasn't JSON: keep statusText
      }
      throw new ApiError(res.status, message, fieldErrors);
    }

    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "Délai dépassé, l'API AELYN ne répond pas.");
    }
    throw new ApiError(0, "AELYN Core (aelyn-api) injoignable.");
  } finally {
    window.clearTimeout(timeout);
  }
}

/** Fast, short-timeout reachability check: pages use this to decide
 * "show live data" vs "fall back to the demo mocks" without a long
 * hang when the backend simply isn't running locally. */
export async function getHealth(): Promise<boolean> {
  try {
    const res = await request<{ status: string }>("/health", { timeoutMs: 1500 });
    return res.status === "ok";
  } catch {
    return false;
  }
}

// ---- Email ---------------------------------------------------------

export interface ApiEmailListItem {
  uid: number | string;
  sender: string;
  sender_email: string;
  subject: string;
  date: string | null;
  preview: string;
  has_attachments: boolean;
  /** Présents uniquement pour un résultat de "triage" (pas "verifier") :
   * ce que le LLM propose pour ce mail, cf.
   * aelyn_conversation.agent._mail_to_dict. */
  action_proposee?: string;
  urgence?: number;
  resume?: string;
  action_id?: number;
}

export interface ApiEmailSummary {
  uid: number | string;
  subject: string;
  summary: string;
}

export function getEmails(limit = 20): Promise<ApiEmailListItem[]> {
  return request(`/email?limit=${limit}`);
}

export interface ApiEmailActionResult {
  status: string;
}

/** Exécute/rejette une proposition de triage déjà faite (uniquement cette
 * route-ci le permet : POST /chat/message refuse délibérément valider/
 * rejeter, cf. son docstring). */
export function validateEmailAction(actionId: number): Promise<ApiEmailActionResult> {
  return request(`/email/${actionId}/validate`, { method: "POST" });
}

export function rejectEmailAction(actionId: number): Promise<ApiEmailActionResult> {
  return request(`/email/${actionId}/reject`, { method: "POST" });
}

export function getEmailSummary(uid: number | string): Promise<ApiEmailSummary> {
  return request(`/email/${uid}/summary`, { timeoutMs: 60_000 });
}

// ---- Career ---------------------------------------------------------

export type ContractType = "cdi" | "cdd" | "alternance" | "stage";

export interface ApiCareerOffer {
  id: string;
  intitule: string;
  entreprise: string;
  lieu: string;
  contrat: string;
  date_creation: string;
  date_publication?: string | null;
  date_limite?: string | null;
  deadline?: string | null;
  url?: string | null;
  description?: string | null;
  score?: number;
}

export interface ApiCvExperience {
  role: string;
  entreprise: string;
  periode: string;
  puces: string[];
}

export interface ApiCvProjet {
  titre: string;
  description: string;
}

export interface ApiCvContent {
  profil: string;
  experiences: ApiCvExperience[];
  projets: ApiCvProjet[];
  competences: Record<string, string[]>;
  formation: string[];
  certifications: string[];
  langues: string[];
  centres_interet: string[];
}

/** The shape of a single item in POST /chat/message's `results` when
 * `result_type === "offers"`. These are the raw France Travail offer
 * dicts the career-agent pipeline uses internally (per the backend
 * agent, "richer than GET /career's OfferOut"), so only the fields this
 * app actually displays are typed here; everything else is ignored
 * rather than assumed. All optional since a fast-path result (plain
 * `ApiCareerOffer`, e.g. from `getCareerOffers`) is also valid here. */
/** Deux formes possibles selon la route qui a produit ce résultat :
 * `GET /career` (OfferOut, pas utilisé actuellement côté frontend)
 * aplatit entreprise/lieu/contrat en chaînes ; `POST /chat/message`
 * renvoie le dict France Travail BRUT (`TurnResult.results`, aucun
 * modèle Pydantic ne le filtre), avec `entreprise`/`lieuTravail` en
 * objets imbriqués et `typeContrat`/`dateCreation` en camelCase. Les
 * deux formes sont acceptées ici ; voir les fonctions `offer*` dans
 * ChatResultTable.tsx qui les normalisent à l'affichage. */
export interface ApiOfferResult {
  id?: string;
  intitule?: string;
  title?: string;
  entreprise?: string | { nom?: string };
  company?: string | { name?: string };
  lieuTravail?: { libelle?: string };
  location?: string | { city?: string; raw?: string; remote?: string };
  lieu?: string;
  typeContrat?: string;
  contrat?: string;
  contract_type?: string;
  dateCreation?: string;
  date_creation?: string;
  date_publication?: string;
  posted_at?: string;
  dateLimiteDePotentiel?: string;
  dateLimite?: string;
  dateFin?: string;
  deadline?: string;
  expires_at?: string;
  score?: number;
  source?: string;
  url?: string;
  urlOffre?: string;
  lien?: string;
  application?: { url?: string; source?: string; deadline?: string };
  sources_seen?: { source?: string; url?: string }[];
  /** Jamais un lien inventé, toujours celui de l'annonce source. France
   * Travail héberge rarement la candidature elle-même : `partenaires[0].
   * url` (ex. PMEJOB, DirectEmploi...) est en général la VRAIE
   * destination, `urlOrigine` (la fiche France Travail) n'étant qu'un
   * repli qui redirige de toute façon vers ce même partenaire. */
  origineOffre?: { urlOrigine?: string; partenaires?: { nom?: string; url?: string }[] };
}

export function getCareerOffers(params: { motsCles?: string; contractType?: ContractType } = {}): Promise<ApiCareerOffer[]> {
  const q = new URLSearchParams();
  if (params.motsCles) q.set("mots_cles", params.motsCles);
  if (params.contractType) q.set("contract_type", params.contractType);
  const qs = q.toString();
  // Timeout long (pas le défaut de 6s) : `GET /career` lance désormais le
  // vrai scoring BM25/cosinus contre le profil (structuration LLM par
  // offre non encore vue), jusqu'à ~2-3 min sur une recherche jamais vue
  // avant mise en cache (observé en direct) : le défaut, pensé pour un
  // simple fetch France Travail avant ce changement, coupait la requête
  // bien avant la fin et affichait une fausse erreur de timeout.
  return request(`/career${qs ? `?${qs}` : ""}`, { timeoutMs: 180_000 });
}

export function getCareerCv(offerId: string): Promise<ApiCvContent> {
  return request(`/career/${offerId}/cv`, { method: "POST", timeoutMs: 150_000 });
}

export function getCareerCoverLetter(offerId: string): Promise<{ text: string }> {
  return request(`/career/${offerId}/lm`, { method: "POST", timeoutMs: 150_000 });
}

export interface ApplyByMailResult {
  sent_to: string;
  offer_title: string;
}

export function applyCareerByMail(offerId: string): Promise<ApplyByMailResult> {
  return request(`/career/${offerId}/apply-by-mail`, { method: "POST", timeoutMs: 150_000 });
}

// ---- Media (TV) -------------------------------------------------------

export type MediaAction =
  | "netflix"
  | "youtube"
  | "tv_power"
  | "home"
  | "back"
  | "up"
  | "down"
  | "left"
  | "right"
  | "select"
  | "play_pause"
  | "next"
  | "previous"
  | "volume_up"
  | "volume_down"
  | "mute"
  | "search_youtube"
  | "search_netflix";

export function getMediaActions(): Promise<MediaAction[]> {
  return request("/media/actions");
}

export function triggerMediaAction(
  action: MediaAction,
  body: { query?: string | null; amount?: number | null } = {}
): Promise<{ status: string; action: string }> {
  return request(`/media/${action}`, { method: "POST", body });
}

// ---- Security / local camera preview -----------------------------------

/** Local-machine OpenCV camera, wired for real by the backend: NOT the
 * same thing as this frontend's browser-based `getUserMedia` live feed
 * (lib/useLiveCamera.ts). This only opens a native window on whatever
 * machine runs `aelyn-api`; there is no browser video stream for it yet
 * (the backend agent flagged that as a real, unbuilt streaming feature,
 * MJPEG/WebRTC, if the UI ever needs it embedded). */
export interface ApiCameraInfo {
  name: "entree" | "salon";
  index: number;
  configured: boolean;
}

export function getApiCameras(): Promise<ApiCameraInfo[]> {
  return request("/security/cameras");
}

export function getApiCamera(name: string): Promise<ApiCameraInfo> {
  return request(`/security/cameras/${name}`);
}

export function openApiCameraPreview(name: string): Promise<{ status: string; name: string }> {
  return request(`/security/cameras/${name}/preview`, { method: "POST" });
}

// ---- Chat -------------------------------------------------------------

export interface ApiChatEntry {
  id: string | number;
  ts: string;
  role: "user" | "assistant";
  content: string;
}

export function getChatHistory(limit = 50, beforeId?: number): Promise<ApiChatEntry[]> {
  const before = beforeId !== undefined ? `&before_id=${beforeId}` : "";
  return request(`/chat/history?limit=${limit}${before}`);
}

// ---- Activity ------------------------------------------------------

export interface ApiActivityEntry {
  id: string;
  timestamp: string;
  message: string;
  source: string;
}

/** GET /activity : le vrai Journal (aelyn.core.journal), vide pour un
 * utilisateur sans historique réel au lieu du mock toujours affiché
 * (mocks/activity.ts). `hours` par défaut côté backend (168 = 7 jours). */
export function getActivity(hours?: number): Promise<ApiActivityEntry[]> {
  return request(hours ? `/activity?hours=${hours}` : "/activity");
}

/** POST /chat/message's response shape. This now goes through the real
 * ConversationalAgent pipeline (same fast router + SYSTEM_INTENT routing
 * + offer/mail reference resolution as the CLI), not a bare LLM call, so
 * a follow-up like "affiche les offres" after a search correctly returns
 * the same list instead of a generic reply. `text` is always the
 * natural-language reply; `result_type`/`results` are populated only
 * when that reply represents a structured list (offer search or mail
 * check) rather than a plain sentence, so the UI can render a real table
 * instead of parsing bullets out of `text`. Note this is deliberately a
 * different shape from `ApiChatEntry`: `id`/`ts`/`role` (the persisted
 * row) aren't part of "the reply to render right now"; fetch
 * `getChatHistory()` if those are needed. Commands that mutate state
 * (valider/rejeter) are never executed here; `text` says so plainly
 * instead. */
export interface ApiChatTurn {
  text: string;
  result_type: "offers" | "mails" | null;
  results: ApiOfferResult[] | ApiEmailListItem[] | null;
}

export function sendChatMessage(message: string): Promise<ApiChatTurn> {
  // 30s n'etait pas assez : une reponse conversationnelle reelle peut
  // depasser ce delai, surtout juste apres un changement de modele Ollama
  // (confirme : qwen3:4b et le modele d'escalade s'evincent mutuellement
  // de la VRAM a 6 Go, le rechargement a lui seul prend plusieurs
  // secondes avant meme que la reponse ne commence). 90s ne suffit plus
  // non plus depuis que "cherche des offres" (meme sans mot-cle, qui part
  // par ici) lance le vrai scoring BM25/cosinus (structuration LLM par
  // offre jamais vue) : jusqu'a ~2-3 min sur une recherche jamais mise en
  // cache (observe en direct), d'ou 180s desormais, meme valeur que
  // `getCareerOffers` pour le meme type d'appel plus lent.
  return request("/chat/message", { method: "POST", body: { message }, timeoutMs: 180_000 });
}

// ---- Settings -----------------------------------------------------------

export interface ApiSettings {
  user_name: string;
  llm_model: string;
  llm_model_heavy: string;
  llm_model_career: string;
  ollama_host: string;
  wake_timeout_seconds: number;
  allow_autonomous_send: boolean;
  tv_configured: boolean;
  camera_entree_index: number | null;
  camera_salon_index: number | null;
  candidate_level: string;
  weight_score_txt_match: number;
  weight_score_cos: number;
  face_match_threshold: number;
  keywords: string[];
  department: string[];
  proactive_search_enabled: boolean;
  proactive_search_interval_minutes: number;
}

export function getSettings(): Promise<ApiSettings> {
  return request("/settings");
}

/** Throws ApiError with status 401 (wrong passkey) or 503 (no
 * SETTINGS_PASSKEY configured on this install: editing is disabled). */
export function authSettings(passkey: string): Promise<{ token: string; expires_in: number }> {
  return request("/settings/auth", { method: "POST", body: { passkey } });
}

export function setAllowAutonomousSend(value: boolean, token: string): Promise<{ allow_autonomous_send: boolean }> {
  return request("/settings/allow-autonomous-send", { method: "PATCH", body: { value }, token });
}

/** Every field is optional: send only what actually changed (a true
 * partial PATCH). The backend validates and persists all-or-nothing, so
 * a 422 on one field leaves every other field, and `.env`, untouched;
 * `ApiError.fieldErrors` carries exactly which field(s) failed and why. */
export interface SettingsPatch {
  allow_autonomous_send?: boolean;
  wake_timeout_seconds?: number;
  camera_entree_index?: number;
  camera_salon_index?: number;
  candidate_level?: string;
  weight_score_txt_match?: number;
  weight_score_cos?: number;
  face_match_threshold?: number;
  keywords?: string[];
  department?: string[];
  proactive_search_enabled?: boolean;
  proactive_search_interval_minutes?: number;
  llm_model?: string;
  llm_model_heavy?: string;
  llm_model_career?: string;
}

/** Persists for real (writes `.env`, reloads any already-constructed
 * instance that needs it, e.g. the LLM clients for a model-role change)
 * and returns the full, freshly-read settings. */
export function patchSettings(body: SettingsPatch, token: string): Promise<ApiSettings> {
  return request("/settings", { method: "PATCH", body, token });
}

/** Models actually pulled locally in Ollama right now (real `ollama
 * list`, not a hardcoded catalog): the only valid values `patchSettings`
 * will accept for `llm_model`/`llm_model_heavy`/`llm_model_career`.
 * Empty (not an error) if Ollama itself is unreachable. */
export function getSettingsModels(): Promise<{ models: string[] }> {
  return request("/settings/models");
}

// ---- Career profile -------------------------------------------------------

/** The raw, current `profil.json` content, re-read from disk on every
 * call (never a stale in-memory copy): shown/edited as JSON text by the
 * Settings page's profile editor. No auth needed, it's a read. */
export function getCareerProfile(): Promise<Record<string, unknown>> {
  return request("/career/profile");
}

/** Replaces `profil.json` wholesale with `profile`, validated
 * structurally server-side BEFORE anything is written (a bad edit never
 * reaches disk: `ApiError.fieldErrors[].msg` names exactly what's
 * missing, e.g. "profile.experience[0] : champ 'company' manquant").
 * On success the backend keeps one `.bak` of the previous content and
 * reloads CV/cover-letter generation to use the new profile immediately. */
export function putCareerProfile(profile: unknown, token: string): Promise<{ status: string; backup: string }> {
  return request("/career/profile", { method: "PUT", body: profile, token });
}

// ---- System status --------------------------------------------------------

/** `GET /system/status`'s shape: every field is either a genuinely
 * measured value or an explicit `null`/`available: false` with a reason,
 * never a plausible-looking fabricated number (see the backend's own
 * docstring on this endpoint). Replaces the previously-static mock
 * uptime/CPU/RAM/service-status text on Overview/System with this when
 * the backend is reachable. */
export interface SystemResources {
  cpu_percent: number;
  cpu_temp_celsius: { value: number | null; available: boolean; reason?: string };
  ram: { percent: number; used_mb: number; total_mb: number };
  disk: { percent: number; used_gb: number; total_gb: number };
  disks: { mountpoint: string; percent: number; used_gb: number; total_gb: number }[];
  gpu:
    | {
        available: true;
        name: string;
        temperature_celsius: number;
        utilization_percent: number;
        memory_used_mb: number;
        memory_total_mb: number;
      }
    | { available: false; reason: string };
  network: { bytes_sent: number; bytes_recv: number; note: string };
  uptime_seconds: number;
  uptime_note: string;
}

export interface SystemStatus {
  resources: SystemResources;
  services: {
    ollama: {
      reachable: boolean;
      error: string | null;
      models: string[];
      roles: Record<"llm_model" | "llm_model_heavy" | "llm_model_career", { model: string; available_locally: boolean }>;
    };
    imap: { connected: boolean; server: string; error?: string };
    france_travail: { reachable: boolean; source: string; error?: string };
    media_tv: { configured: boolean; connected: boolean };
    voice_assets: {
      whisper: { model_size: string; present: boolean; note: string };
      kokoro: { present: boolean; note: string };
    };
    tailscale:
      | { available: true; connected: boolean; backend_state: string; tailscale_ips: string[] }
      | { available: false; connected: false; reason: string };
  };
}

/** Lightweight, real resource sample for the Data page. Unlike
 * `/system/status`, this route does not check mail, France Travail or
 * Ollama, so it is safe to refresh periodically while the page is open. */
export function getSystemResources(): Promise<SystemResources> {
  return request("/system/resources", { timeoutMs: 10_000 });
}

export function getSystemStatus(): Promise<SystemStatus> {
  // Real IMAP login + a real France Travail OAuth check (when no session
  // token is already cached) alongside the usual psutil/nvidia-smi reads,
  // so this is slower than a typical GET; still bounded well under
  // getSettings()'s default in case either service is slow to respond.
  return request("/system/status", { timeoutMs: 10_000 });
}

// ---- Text-to-speech -----------------------------------------------------

export interface TtsResult {
  blob: Blob;
  /** The real `Content-Type` from the response: either "audio/mpeg"
   * (Edge TTS, the common case) or "audio/wav" (local Kokoro fallback).
   * Never assume one; the backend agent was explicit that it varies
   * per call and must be read from the response, not hardcoded. */
  contentType: string;
}

/** AELYN's real voice, same Edge TTS ("Vivienne") / local Kokoro
 * fallback the CLI's `aelyn chat --voix` uses, not the browser's
 * synthetic voice. `request()` isn't reused here since it assumes a
 * JSON body; this reads raw audio bytes instead. Throws ApiError(400)
 * for empty text, ApiError(502) if both Edge TTS and Kokoro fail on the
 * server, or a network/timeout ApiError if aelyn-api itself is
 * unreachable; callers (lib/useSpeechSynthesis.ts) fall back to the
 * browser's own SpeechSynthesis on any of these. */
export async function synthesizeSpeech(text: string): Promise<TtsResult> {
  const controller = new AbortController();
  // Edge TTS is a real network round-trip that scales with text length
  // (backend agent measured ~5s for a short sentence): generous but
  // bounded so a hung request still eventually falls back.
  const timeout = window.setTimeout(() => controller.abort(), 25_000);

  try {
    const res = await fetch(`${API_BASE}/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    });

    if (!res.ok) {
      let message = res.statusText;
      try {
        const data = await res.json();
        message = data?.detail ?? message;
      } catch {
        // not JSON: keep statusText
      }
      throw new ApiError(res.status, message);
    }

    const contentType = res.headers.get("content-type") || "audio/mpeg";
    let blob = await res.blob();
    if (!blob.type) blob = new Blob([blob], { type: contentType });
    return { blob, contentType };
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "Délai dépassé pour la synthèse vocale (aelyn-api /tts).");
    }
    throw new ApiError(0, "aelyn-api /tts injoignable.");
  } finally {
    window.clearTimeout(timeout);
  }
}

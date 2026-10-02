export interface ConfigGroup {
  title: string;
  entries: { key: string; value: string; note?: string }[];
}

/** Mirrors the real, versioned .env.example (src/backend/.env.example),
 * grouped the same way the backend README documents it. Values shown
 * are placeholders (never secrets); read-only for fields `PATCH
 * /settings` doesn't cover.
 *
 * Deliberately NOT listed here anymore: LLM_MODEL/LLM_MODEL_HEAVY/
 * LLM_MODEL_CAREER (now the real model-picker section),
 * FACE_MATCH_THRESHOLD/KEYWORDS/DEPARTMENT/CANDIDATE_LEVEL/
 * WAKE_TIMEOUT_SECONDS (now the real editable-fields section): showing
 * both a static placeholder AND a live editable control for the same
 * setting would just be confusing, so each of those now lives in exactly
 * one place on this page. */
export const configGroups: ConfigGroup[] = [
  {
    title: "Utilisateur",
    entries: [
      { key: "USER_NAME", value: "djamal" },
      { key: "USER_FULL_NAME", value: "Djamal Toe" },
      { key: "USER_CITY", value: "Rennes" },
    ],
  },
  {
    title: "LLM (Ollama)",
    entries: [
      { key: "OLLAMA_HOST", value: "http://localhost:11434" },
      { key: "LLM_THINK", value: "false" },
    ],
  },
  {
    title: "Sécurité (visage)",
    entries: [{ key: "FACES_DIR", value: "security-agent/src/faces" }],
  },
  {
    title: "Voix",
    entries: [
      { key: "WHISPER_MODEL_SIZE", value: "small" },
      { key: "WHISPER_DEVICE", value: "cuda" },
    ],
  },
  {
    title: "Média (TV)",
    entries: [{ key: "TV_IP_ADRESS", value: "192.168.1.42" }],
  },
  {
    title: "Garde-fous",
    entries: [
      { key: "ALLOW_AUTONOMOUS_SEND", value: "false", note: "aucun mail envoyé sans validation manuelle" },
      { key: "MAX_MAILS_PER_RUN", value: "15" },
    ],
  },
];

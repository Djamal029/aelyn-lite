"""Configuration centralisée d'AELYN.

Une seule source de vérité pour les réglages. Aucun os.getenv() ailleurs
dans le code : tout passe par `settings`.

Note : on n'utilise pas `pydantic-settings` (non installé pour l'instant,
et évitable ici) ; `python-dotenv` + un `BaseModel` suffisent pour ce
qu'on valide.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw is not None else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw is not None else default


class Settings(BaseModel):
    # --- Utilisateur ---
    # Pour signer les brouillons de réponse ("Cordialement, {user_name}").
    # Par défaut, la partie locale de l'adresse mail, à surcharger via
    # USER_NAME dans .env pour un vrai prénom.
    user_name: str = "toi"
    # Coordonnées pour l'en-tête d'un CV/lettre de motivation (career-agent),
    # jamais laissées au LLM à générer : une identité inventée (mauvais nom,
    # faux téléphone) est un risque bien plus grave qu'un champ vide.
    user_full_name: str | None = None
    user_contact_email: str | None = None
    user_phone: str | None = None
    user_linkedin: str | None = None
    user_city: str | None = None

    # --- Messagerie ---
    email_user: str
    email_pass: str
    imap_server: str = "imap.gmail.com"
    imap_port: int = 993
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587

    # --- LLM local ---
    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen3:4b"
    llm_model_heavy: str = "qwen3:8b"
    # Modèle dédié à la rédaction de candidatures (career-agent), DISTINCT
    # de `llm_model_heavy` (escalade de routage d'intention) : les deux
    # usages ont des contraintes différentes (contexte long + JSON
    # contraint ici, classification courte là), voir
    # `career-agent/src/aelyn_career/application_writer.py` pour
    # l'historique de choix. Avant ce champ, lu directement via
    # `os.getenv("LLM_MODEL_CAREER", ...)` dans ce module career-agent,
    # jamais centralisé ici ; déplacé pour que `PATCH /settings` (aelyn-api)
    # ait une seule source de vérité à modifier, comme les deux autres.
    llm_model_career: str = "mistral:7b"
    llm_temperature: float = 0.2
    # qwen3 génère un raisonnement caché avant sa réponse si on ne le
    # désactive pas explicitement (~18x plus lent pour un simple JSON
    # de classification, sans gain de qualité mesurable ici).
    llm_think: bool = False

    # --- Sécurité (reconnaissance faciale, DeepFace/ArcFace) ---
    faces_dir: Path = Field(default=Path("security-agent/src/faces"))
    # Distance cosinus (0 = identique, 2 = opposé) en dessous de laquelle
    # deux visages sont considérés comme la même personne. 0.68 est le
    # seuil calibré par DeepFace pour ArcFace+cosinus ; à ajuster sur mes
    # propres photos si besoin.
    face_match_threshold: float = 0.68

    # --- Voix (chat --voix) ---
    # Nom (ou sous-chaîne) d'un périphérique de `sr.Microphone.list_microphone_names()`.
    # None = périphérique d'entrée par défaut du système.
    microphone_name: str | None = None
    # Transcription locale (faster-whisper) : tentée EN PREMIER (bien plus
    # robuste sur le français mélangé à de l'anglais technique et sur les
    # noms propres que l'API Google gratuite), avec repli automatique sur
    # `recognize_google` en cas d'échec (modèle absent, GPU indisponible,
    # pas encore téléchargé faute de connexion...). "small" = bon rapport
    # qualité/latence sur GPU ; "cuda" suppose un GPU NVIDIA disponible
    # (même hypothèse que EMBEDDING_DEVICE pour le career-agent).
    whisper_model_size: str = "small"
    whisper_device: str = "cuda"
    # Après une réponse d'AELYN, durée (secondes) pendant laquelle elle
    # reste active sans qu'il faille redire "Éline" pour continuer à lui
    # parler. Au-delà de ce silence, retour en veille (mot d'activation
    # de nouveau nécessaire).
    wake_timeout_seconds: int = 180

    # --- Média (Freebox Pop / Android TV) ---
    tv_ip: str | None = None
    tv_cert_file: Path | None = None
    tv_key_file: Path | None = None
    # Clé API YouTube Data v3 (https://console.cloud.google.com/apis/credentials,
    # activer "YouTube Data API v3"), pour GET /media/youtube/search côté
    # aelyn-api. Le quota gratuit (10 000 unités/jour, une recherche en
    # coûte 100) suffit largement pour un usage personnel.
    youtube_api_key: str | None = None

    # --- Caméras locales (test local via OpenCV) ---
    # Index de périphérique vidéo (`cv2.VideoCapture(index)`) pour chaque
    # caméra nommée. Jamais devinés : sur Windows, l'ordre des index
    # dépend du matériel/pilotes de la machine (webcam intégrée et Iriun
    # Webcam peuvent être 0/1 dans un sens ou dans l'autre selon le PC),
    # voir media-agent/scripts/list_cameras.py pour les identifier.
    # Par défaut : 0 = webcam intégrée/branchée (entrée), 1 = Iriun
    # Webcam (salon), à vérifier/corriger dans .env avant tout test réel.
    camera_entree_index: int = 0
    camera_salon_index: int = 1

    # --- Stockage ---
    data_dir: Path = Field(default=Path.home() / ".aelyn")

    # --- Garde-fous ---
    # Aucun mail ne part sans validation humaine tant que c'est False.
    allow_autonomous_send: bool = False
    max_mails_per_run: int = 15
    # Code requis avant toute modification via aelyn-api (PATCH /settings/*) :
    # cf. aelyn-api/src/aelyn_api/security.py. `None` = passkey non configuré :
    # dans ce cas l'API refuse TOUTE modification plutôt que de l'autoriser
    # sans protection (jamais de "pas de code = ouvert à tous").
    settings_passkey: str | None = None

    # --- Carrière (France Travail + scoring, career-agent) ---
    # Déplacés ici (avant : constantes de module lues via `os.getenv()`
    # directement dans `embbeder.py`/`france_travail/offers.py`, figées à
    # l'import) pour que `PATCH /settings` (aelyn-api) puisse les modifier
    # EN DIRECT sur le process déjà démarré, sans redémarrage : ces deux
    # modules lisent désormais `settings.xxx` à CHAQUE appel plutôt qu'une
    # copie locale gelée.
    #
    # "stage"/"junior"/"senior"/"postdoc" (cf. `NiveauRequis`,
    # aelyn_career.models) : niveau de LA personne qui utilise ce
    # programme, pénalise le score d'une offre trop loin de ce niveau.
    candidate_level: str = "junior"
    # Pondération BM25 (correspondance lexicale) vs similarité cosinus
    # (embeddings) dans le score final d'une offre, chacun dans [0, 1]
    # (cf. `TextEmbbeder.final_score`). Pensés pour se compléter à 1, mais
    # non forcé : un total différent de 1 change seulement l'échelle
    # globale du score, pas son classement relatif entre offres.
    weight_score_txt_match: float = 0.4
    weight_score_cos: float = 0.6
    # Mots-clés de recherche France Travail, UNE chaîne séparée par des
    # virgules (format natif de l'API France Travail, cf.
    # `france_travail/offers.py`) ; exposée à l'API comme `list[str]` pour
    # un champ répétable côté frontend, rejointe ici au moment d'écrire.
    keywords: str = ""
    # Codes département France Travail (ex. "75,35"), même logique que
    # `keywords` ci-dessus.
    department: str = ""

    @property
    def journal_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "journal.db"

    @property
    def chat_history_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "chat_history.db"

    @property
    def embeddings_dir(self) -> Path:
        path = self.data_dir / "faces"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def tv_cert_path(self) -> Path:
        if self.tv_cert_file:
            return self.tv_cert_file
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "tv_cert.pem"

    @property
    def tv_key_path(self) -> Path:
        if self.tv_key_file:
            return self.tv_key_file
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "tv_key.pem"


@lru_cache
def get_settings() -> Settings:
    missing = [name for name in ("EMAIL_USER", "EMAIL_PASS") if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Variables d'environnement manquantes : "
            f"{', '.join(missing)} (voir .env)"
        )
    email_user = os.environ["EMAIL_USER"]
    return Settings(
        user_name=os.getenv("USER_NAME") or email_user.split("@")[0],
        user_full_name=os.getenv("USER_FULL_NAME") or None,
        user_contact_email=os.getenv("USER_CONTACT_EMAIL") or None,
        user_phone=os.getenv("USER_PHONE") or None,
        user_linkedin=os.getenv("USER_LINKEDIN") or None,
        user_city=os.getenv("USER_CITY") or None,
        email_user=email_user,
        email_pass=os.environ["EMAIL_PASS"],
        imap_server=os.getenv("IMAP_SERVER", "imap.gmail.com"),
        imap_port=_env_int("IMAP_PORT", 993),
        smtp_server=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        smtp_port=_env_int("SMTP_PORT", 587),
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        llm_model=os.getenv("LLM_MODEL", "qwen3:4b"),
        llm_model_heavy=os.getenv("LLM_MODEL_HEAVY", "qwen3:8b"),
        llm_model_career=os.getenv("LLM_MODEL_CAREER", "mistral:7b"),
        llm_temperature=_env_float("LLM_TEMPERATURE", 0.2),
        llm_think=_env_bool("LLM_THINK", False),
        faces_dir=Path(os.getenv("FACES_DIR", "security-agent/src/faces")),
        face_match_threshold=_env_float("FACE_MATCH_THRESHOLD", 0.68),
        microphone_name=os.getenv("MICROPHONE_NAME") or None,
        whisper_model_size=os.getenv("WHISPER_MODEL_SIZE", "small"),
        whisper_device=os.getenv("WHISPER_DEVICE", "cuda"),
        wake_timeout_seconds=_env_int("WAKE_TIMEOUT_SECONDS", 180),
        tv_ip=os.getenv("TV_IP_ADRESS") or None,
        tv_cert_file=Path(os.environ["TV_CERT_FILE"]) if os.getenv("TV_CERT_FILE") else None,
        tv_key_file=Path(os.environ["TV_KEY_FILE"]) if os.getenv("TV_KEY_FILE") else None,
        youtube_api_key=os.getenv("YOUTUBE_API_KEY") or None,
        camera_entree_index=_env_int("CAMERA_ENTREE_INDEX", 0),
        camera_salon_index=_env_int("CAMERA_SALON_INDEX", 1),
        data_dir=Path(os.getenv("DATA_DIR", str(Path.home() / ".aelyn"))),
        allow_autonomous_send=_env_bool("ALLOW_AUTONOMOUS_SEND", False),
        max_mails_per_run=_env_int("MAX_MAILS_PER_RUN", 15),
        settings_passkey=os.getenv("SETTINGS_PASSKEY") or None,
        candidate_level=os.getenv("CANDIDATE_LEVEL", "junior"),
        weight_score_txt_match=_env_float("WEIGHT_SCORE_TXT_MATCH", 0.4),
        weight_score_cos=_env_float("WEIGHT_SCORE_COS", 0.6),
        keywords=os.getenv("KEYWORDS", ""),
        department=os.getenv("DEPARTMENT", ""),
    )


settings = get_settings()

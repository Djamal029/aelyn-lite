"""Réglages exposés en lecture (aucun secret) + passkey pour toute
modification (cf. `aelyn_api.security`).

`PATCH /settings` (générique) PERSISTE réellement dans `.env` (cf.
`aelyn_api.env_file`), contrairement à l'ancien comportement "en mémoire
seulement" de ce module (gardé un temps sur `allow_autonomous_send`
avant ce correctif). Il met AUSSI à jour `aelyn.core.config.settings` (le
singleton déjà chargé par ce process) et, pour les 3 réglages qui ne
sont PAS déjà lus en direct depuis `settings` à chaque appel (les 3
modèles LLM, capturés une fois dans des `LLMClient` construits au
démarrage), recharge explicitement les instances vivantes
(`ConversationalAgent`, `ApplicationWriter`) pour un effet immédiat, sans
redémarrage de l'API. Les autres réglages (poids de scoring,
mots-clés/département France Travail, seuil facial, timeout vocal, index
caméra, garde-fou d'envoi autonome) étaient déjà, ou ont été rendus par
ce même chantier, des lectures directes de `settings.xxx` au moment de
l'usage : les modifier ici suffit, aucun rechargement dédié requis.

Jamais exposés en écriture ici (secrets réels ou identité du passkey
lui-même) : `EMAIL_PASS`, `FRANCE_TRAVAIL_CLIENT_SECRET`,
`SETTINGS_PASSKEY`. `EMAIL_USER`/`FRANCE_TRAVAIL_CLIENT_ID` ne sont pas
des secrets au même sens, mais rester hors de ce formulaire aussi : les
changer casserait silencieusement la connexion IMAP/France Travail sans
aucun moyen pour ce endpoint de le vérifier avant d'écrire.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from aelyn.core.config import settings
from aelyn.core.llm import list_available_models

from aelyn_api.deps import get_application_writer, get_conversational_agent
from aelyn_api.env_file import set_env_value
from aelyn_api.security import TOKEN_TTL_SECONDS, require_settings_token, verify_passkey

router = APIRouter(prefix="/settings", tags=["settings"])

_CANDIDATE_LEVELS = {"stage", "junior", "senior", "postdoc"}
# Champs qui, en plus de `settings.xxx`, demandent un rechargement
# explicite d'une instance déjà construite (cf. docstring du module).
_LLM_ROLE_FIELDS = {"llm_model", "llm_model_heavy", "llm_model_career"}


class SettingsOut(BaseModel):
    user_name: str
    llm_model: str
    llm_model_heavy: str
    llm_model_career: str
    ollama_host: str
    wake_timeout_seconds: int
    allow_autonomous_send: bool
    tv_configured: bool
    camera_entree_index: int
    camera_salon_index: int
    candidate_level: str
    weight_score_txt_match: float
    weight_score_cos: float
    face_match_threshold: float
    keywords: list[str]
    department: list[str]
    proactive_search_enabled: bool
    proactive_search_interval_minutes: int


class PasskeyIn(BaseModel):
    passkey: str


class TokenOut(BaseModel):
    token: str
    expires_in: int


class AllowAutonomousSendIn(BaseModel):
    value: bool


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _settings_out() -> SettingsOut:
    return SettingsOut(
        user_name=settings.user_name,
        llm_model=settings.llm_model,
        llm_model_heavy=settings.llm_model_heavy,
        llm_model_career=settings.llm_model_career,
        ollama_host=settings.ollama_host,
        wake_timeout_seconds=settings.wake_timeout_seconds,
        allow_autonomous_send=settings.allow_autonomous_send,
        tv_configured=bool(settings.tv_ip),
        camera_entree_index=settings.camera_entree_index,
        camera_salon_index=settings.camera_salon_index,
        candidate_level=settings.candidate_level,
        weight_score_txt_match=settings.weight_score_txt_match,
        weight_score_cos=settings.weight_score_cos,
        face_match_threshold=settings.face_match_threshold,
        keywords=_split_csv(settings.keywords),
        department=_split_csv(settings.department),
        proactive_search_enabled=settings.proactive_search_enabled,
        proactive_search_interval_minutes=settings.proactive_search_interval_minutes,
    )


@router.get("", response_model=SettingsOut)
def read_settings() -> SettingsOut:
    return _settings_out()


@router.get("/models")
def list_models() -> dict:
    """Modèles Ollama réellement tirés localement (`ollama list`), pour
    peupler un VRAI menu déroulant côté frontend plutôt qu'un champ texte
    libre (cf. `PATCH /settings`, qui refuse tout modèle absent d'ici).
    Liste vide (pas d'erreur) si Ollama est injoignable : au frontend de
    l'afficher honnêtement plutôt qu'une 500 brute."""
    return {"models": list_available_models()}


@router.post("/auth", response_model=TokenOut)
def authenticate(body: PasskeyIn) -> TokenOut:
    token = verify_passkey(body.passkey)
    return TokenOut(token=token, expires_in=TOKEN_TTL_SECONDS)


@router.patch("/allow-autonomous-send", dependencies=[Depends(require_settings_token)])
def set_allow_autonomous_send(body: AllowAutonomousSendIn) -> dict:
    """Conservé pour compatibilité ; `PATCH /settings` (générique, voir
    plus bas) couvre désormais ce même champ EN PLUS de persister dans
    `.env` (ce que cette route historique ne fait toujours pas)."""
    settings.allow_autonomous_send = body.value
    return {"allow_autonomous_send": settings.allow_autonomous_send}


class SettingsPatchIn(BaseModel):
    """Toutes les clés sont optionnelles : seules celles fournies sont
    validées et modifiées (`PATCH` partiel), les autres restent
    inchangées. Chaque validateur lève un message PRÉCIS (pas un "422
    invalide" générique) : FastAPI les restitue un par un dans la réponse
    422 (`detail: [{"loc": [...], "msg": ...}, ...]`), ce que le
    frontend peut afficher champ par champ."""

    allow_autonomous_send: bool | None = None
    wake_timeout_seconds: int | None = Field(default=None, ge=10, le=3600)
    camera_entree_index: int | None = Field(default=None, ge=0)
    camera_salon_index: int | None = Field(default=None, ge=0)
    candidate_level: str | None = None
    weight_score_txt_match: float | None = Field(default=None, ge=0.0, le=1.0)
    weight_score_cos: float | None = Field(default=None, ge=0.0, le=1.0)
    face_match_threshold: float | None = Field(default=None, ge=0.0, le=2.0)
    keywords: list[str] | None = None
    department: list[str] | None = None
    proactive_search_enabled: bool | None = None
    proactive_search_interval_minutes: int | None = Field(
        default=None, ge=15, le=1440
    )
    llm_model: str | None = None
    llm_model_heavy: str | None = None
    llm_model_career: str | None = None

    @field_validator("candidate_level")
    @classmethod
    def _check_candidate_level(cls, v: str) -> str:
        if v not in _CANDIDATE_LEVELS:
            raise ValueError(
                f"doit être l'un de {sorted(_CANDIDATE_LEVELS)}, reçu {v!r}"
            )
        return v

    @field_validator("keywords", "department")
    @classmethod
    def _clean_string_list(cls, v: list[str]) -> list[str]:
        cleaned = [item.strip() for item in v if item.strip()]
        return cleaned


# Correspondance champ -> (clé .env, sérialiseur pour `dotenv.set_key`).
_ENV_KEYS: dict[str, tuple[str, Callable[[object], str]]] = {
    "allow_autonomous_send": ("ALLOW_AUTONOMOUS_SEND", lambda v: "true" if v else "false"),
    "wake_timeout_seconds": ("WAKE_TIMEOUT_SECONDS", str),
    "camera_entree_index": ("CAMERA_ENTREE_INDEX", str),
    "camera_salon_index": ("CAMERA_SALON_INDEX", str),
    "candidate_level": ("CANDIDATE_LEVEL", str),
    "weight_score_txt_match": ("WEIGHT_SCORE_TXT_MATCH", str),
    "weight_score_cos": ("WEIGHT_SCORE_COS", str),
    "face_match_threshold": ("FACE_MATCH_THRESHOLD", str),
    "keywords": ("KEYWORDS", lambda v: ",".join(v)),
    "department": ("DEPARTMENT", lambda v: ",".join(v)),
    "proactive_search_enabled": (
        "PROACTIVE_SEARCH_ENABLED",
        lambda v: "true" if v else "false",
    ),
    "proactive_search_interval_minutes": ("PROACTIVE_SEARCH_INTERVAL_MINUTES", str),
    "llm_model": ("LLM_MODEL", str),
    "llm_model_heavy": ("LLM_MODEL_HEAVY", str),
    "llm_model_career": ("LLM_MODEL_CAREER", str),
}


@router.patch("", response_model=SettingsOut, dependencies=[Depends(require_settings_token)])
def patch_settings(body: SettingsPatchIn) -> SettingsOut:
    """Modifie un sous-ensemble de réglages, PERSISTE chacun dans `.env`
    (survit à un redémarrage), et recharge les instances déjà construites
    quand nécessaire (modèles LLM, cf. docstring du module).

    Un modèle LLM (`llm_model`/`llm_model_heavy`/`llm_model_career`) est
    validé contre `GET /settings/models` (modèles RÉELLEMENT tirés
    localement) : en assigner un absent échouerait au premier appel une
    fois en place, refusé ici avec un 422 explicite plutôt qu'un échec
    différé et confus pendant une vraie conversation/candidature.

    Tout ou rien : si un SEUL champ échoue sa validation, RIEN n'est écrit
    (ni `.env`, ni `settings` en mémoire), pour ne jamais laisser `.env`
    et le process en mémoire diverger sur un échec partiel.
    """
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return _settings_out()

    llm_fields_changed = {f for f in changes if f in _LLM_ROLE_FIELDS}
    if llm_fields_changed:
        available = set(list_available_models())
        errors = []
        for field in sorted(llm_fields_changed):
            model = changes[field]
            if model not in available:
                errors.append(
                    {
                        "loc": ["body", field],
                        "msg": (
                            f"Modèle Ollama '{model}' non trouvé localement "
                            f"(`ollama pull {model}` d'abord). Modèles disponibles : "
                            f"{sorted(available) or 'aucun (Ollama injoignable ?)'}."
                        ),
                        "type": "value_error.model_not_found",
                    }
                )
        if errors:
            raise HTTPException(status_code=422, detail=errors)

    # Validé : persister dans .env PUIS en mémoire (dans cet ordre, pour
    # qu'une erreur d'écriture disque laisse `settings` intact plutôt que
    # désynchronisé du fichier).
    for field, value in changes.items():
        env_key, serialize = _ENV_KEYS[field]
        set_env_value(env_key, serialize(value))
        if field in ("keywords", "department"):
            setattr(settings, field, ",".join(value))
        else:
            setattr(settings, field, value)

    if llm_fields_changed:
        agent = get_conversational_agent()
        if "llm_model" in llm_fields_changed or "llm_model_heavy" in llm_fields_changed:
            agent.reload_llm_clients()
        if "llm_model_career" in llm_fields_changed:
            agent.application_writer.reload_llm()
            get_application_writer().reload_llm()

    return _settings_out()

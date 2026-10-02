"""Couche LLM d'AELYN : un seul point d'entrée vers Ollama.

Trois modes :
  - `structured()` : la réponse est validée par un modèle Pydantic.
    C'est le mode par défaut pour tout ce qui alimente du code.
  - `text()` : réponse libre, pour ce qui est lu par un humain,
    renvoyée d'un bloc (attend la fin de la génération).
  - `text_stream()` : comme `text()`, mais renvoie un générateur de
    fragments au fur et à mesure, pour l'affichage progressif (CLI,
    SSE) sur les tâches longues, où la latence PERÇUE compte plus que
    le temps total (cf. son docstring pour la limite acceptée face à
    `_strip_thinking`).

Aucun agent ne parle directement à `ollama`.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from aelyn.core.config import settings

# Ollama décharge un modèle de la VRAM 5 minutes après le dernier appel
# par défaut : sur une session d'usage normale (plusieurs échanges
# espacés de quelques minutes), ça revient à repayer le chargement à
# chaque fois. Une demi-heure couvre une session réelle sans garder le
# modèle en mémoire indéfiniment quand AELYN n'est pas utilisé.
#
# Par défaut pour `LLM_MODEL` (le modèle léger, utilisé partout dans la
# conversation : triage, résumé, brouillon, conversation libre). Les
# modèles OCCASIONNELS (escalade de routage, career-agent) utilisent un
# `keep_alive` bien plus court par défaut (`KEEP_ALIVE_OCCASIONAL`) :
# mesuré en conditions réelles sur un GPU 6 Go (RTX 3060 Laptop) que
# qwen3:4b (léger, ~3.2 Go, 100% GPU) et mistral:7b (~5-7 Go selon
# num_ctx, jamais 100% GPU même seul) ne COEXISTENT JAMAIS en VRAM :
# charger l'un ÉVINCE ENTIÈREMENT l'autre (confirmé via `ollama ps`,
# pas juste un ralentissement). Les garder chauds 30 minutes chacun
# revient à payer un rechargement complet (~8-17s) à CHAQUE
# alternance entre eux — au minimum à chaque tour de chat qui déclenche
# l'escalade de routage (`settings.llm_model_heavy`), bien plus fréquent
# que le seul cas carrière. Un `keep_alive` court pour le modèle
# occasionnel laisse la VRAM revenir plus vite au modèle léger (utilisé
# pour presque tout le reste) entre deux usages espacés, sans empêcher
# le rechargement initial quand les deux sont utilisés en succession
# immédiate (inévitable sur ce GPU tant que les deux modèles sont
# distincts : voir le commentaire sur `settings.llm_model_heavy` dans
# `conversational-agent/src/aelyn_conversation/agent.py` pour la
# discussion complète du compromis précision/latence).
_KEEP_ALIVE = "30m"
KEEP_ALIVE_OCCASIONAL = "2m"

try:
    import ollama
except ModuleNotFoundError:  # paquet pas encore installé (cf. `uv sync`)
    ollama = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_THINK_CLOSE_RE = re.compile(r"</think>", re.IGNORECASE)


def _strip_thinking(content: str) -> str:
    """Retire tout ce qui précède (et inclut) le DERNIER `</think>`.

    `think=False` devrait suffire, mais certains modèles/versions
    d'Ollama laissent quand même passer leur raisonnement dans le
    contenu visible, parfois sans balise `<think>` ouvrante (le chat
    template l'injecte côté serveur, seule `</think>` ressort). Le
    modèle peut aussi mentionner ce mot DANS son raisonnement (ex. en
    recopiant une consigne qui l'interdit) avant d'atteindre son vrai
    marqueur de fin : s'arrêter à la PREMIÈRE occurrence laisse alors
    fuiter tout le reste. On garde donc ce qui suit la dernière.
    """
    parts = _THINK_CLOSE_RE.split(content)
    return parts[-1].strip()


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, model: str | None = None, *, keep_alive: str | None = None) -> None:
        if ollama is None:
            raise LLMError(
                "Le paquet Python 'ollama' n'est pas installé."
                "Lancez `uv sync` dans src/backend une fois en ligne, puis réessayez."
            )
        self.model = model or settings.llm_model
        # `keep_alive` explicite : pour un modèle OCCASIONNEL qui ne
        # coexiste pas en VRAM avec le modèle léger par défaut (cf.
        # `KEEP_ALIVE_OCCASIONAL` ci-dessus), passer un délai court
        # (ex. `aelyn.core.llm.KEEP_ALIVE_OCCASIONAL`). `None` = le
        # comportement historique (`_KEEP_ALIVE`, 30 min), adapté au
        # modèle léger utilisé pour presque tout le reste.
        self.keep_alive = keep_alive or _KEEP_ALIVE
        self._client = ollama.Client(host=settings.ollama_host)

    def structured(
        self,
        *,
        schema: type[T],
        system: str,
        user: str,
        retries: int = 2,
        num_ctx: int | None = None,
    ) -> T:
        """Force le modèle à répondre selon un JSON Schema, puis valide.

        Ollama contraint le décodage au schéma, mais un petit modèle peut
        quand même produire un JSON valide et sémantiquement bancal :
        la validation Pydantic reste indispensable.

        `num_ctx` : Ollama limite la fenêtre de contexte à 4096 tokens par
        défaut, quelle que soit la fenêtre native du modèle : un prompt
        plus long échoue avec `exceed_context_size_error` au lieu d'être
        tronqué. Laisser à `None` pour les appels courts (comportement
        historique) ; à augmenter explicitement pour un prompt long (ex.
        profil complet pour une candidature, cf. `application_writer.py`).
        """
        last_error: Exception | None = None
        options = {"temperature": settings.llm_temperature}
        if num_ctx is not None:
            options["num_ctx"] = num_ctx

        for attempt in range(retries + 1):
            try:
                response = self._client.chat(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    format=schema.model_json_schema(),
                    think=settings.llm_think,
                    options=options,
                    keep_alive=self.keep_alive,
                )
                raw = _strip_thinking(response["message"]["content"])
                return schema.model_validate_json(raw)
            except (ValidationError, json.JSONDecodeError, KeyError) as exc:
                last_error = exc
                logger.warning(
                    "Sortie invalide (tentative %d/%d) : %s",
                    attempt + 1,
                    retries + 1,
                    exc,
                )

        raise LLMError(f"Le modèle n'a pas produit de sortie valide : {last_error}")

    def text(
        self,
        *,
        system: str,
        user: str,
        history: list[dict[str, str]] | None = None,
        num_ctx: int | None = None,
    ) -> str:
        """`history` : tours précédents (`{"role": "user"/"assistant", "content": ...}`).

        Sans ça, chaque appel est isolé, utile pour un résumé ponctuel,
        mais une conversation qui redemande le sujet d'il y a deux
        phrases en a besoin.

        `num_ctx` : voir `structured()`, même limite Ollama à 4096 tokens
        par défaut, même échappatoire pour un prompt long.
        """
        options = {"temperature": settings.llm_temperature}
        if num_ctx is not None:
            options["num_ctx"] = num_ctx
        response = self._client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                *(history or []),
                {"role": "user", "content": user},
            ],
            think=settings.llm_think,
            options=options,
            keep_alive=self.keep_alive,
        )
        return _strip_thinking(response["message"]["content"])

    def text_stream(
        self,
        *,
        system: str,
        user: str,
        history: list[dict[str, str]] | None = None,
        num_ctx: int | None = None,
    ) -> Iterator[str]:
        """Comme `text()`, mais renvoie les fragments au fur et à mesure
        qu'Ollama les génère au lieu d'attendre la réponse complète.

        Pensé pour les tâches longues (lettre de motivation, résumé,
        conversation) : le temps total ne change pas, mais l'utilisateur
        voit le texte apparaître au lieu de fixer un simple accusé de
        réception pendant 10 à 60+ secondes : la latence PERÇUE chute
        radicalement, ce qui compte le plus pour "sentir" comme un vrai
        assistant.

        Limite acceptée par rapport à `_strip_thinking()` (`text()`) :
        celle-ci ne garde que ce qui suit le DERNIER `</think>`, pour
        parer le cas rare où le modèle mentionne ce mot dans son propre
        raisonnement avant sa vraie balise de fin. En flux, on ne peut
        pas "reprendre" du texte déjà affiché à l'écran/à l'oral : on
        s'arrête donc au PREMIER `</think>` rencontré et on diffuse tout
        ce qui suit tel quel.

        Tant qu'aucun `</think>` n'est trouvé, RIEN n'est diffusé : le
        texte est retenu en mémoire jusqu'à la fin du flux. Une version
        antérieure tentait de deviner, à partir d'un seuil de longueur,
        si le modèle "ne pense jamais" pour diffuser plus tôt — observé
        en conditions réelles (qwen3:4b, conversation libre) : `think=False`
        ne supprime pas toujours le raisonnement pour un appel sans schéma
        JSON (contrairement à `structured()`, jamais pris en défaut), et ce
        raisonnement dépasse régulièrement MILLE caractères avant sa
        balise `</think>` ; aucun seuil raisonnable ne permet de distinguer
        "encore en train de réfléchir" de "ce modèle ne réfléchit jamais"
        sans soit laisser fuiter du raisonnement, soit retarder inutilement
        les modèles qui ne réfléchissent pas. Quand la réponse entière se
        termine sans jamais avoir vu `</think>`, tout le texte accumulé est
        diffusé d'un bloc : on perd l'affichage progressif pour CE cas
        précis, mais on élimine complètement le risque de fuite, qui est
        un défaut bien plus grave (raisonnement interne affiché ET parlé à
        l'utilisateur, observé en direct) qu'une latence perçue réduite.
        """
        options = {"temperature": settings.llm_temperature}
        if num_ctx is not None:
            options["num_ctx"] = num_ctx

        stream = self._client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                *(history or []),
                {"role": "user", "content": user},
            ],
            think=settings.llm_think,
            options=options,
            keep_alive=self.keep_alive,
            stream=True,
        )

        close_tag = "</think>"
        buffer = ""
        started = False
        for chunk in stream:
            piece = chunk.get("message", {}).get("content") or ""
            if not piece:
                continue
            if started:
                yield piece
                continue

            buffer += piece
            idx = buffer.find(close_tag)
            if idx != -1:
                started = True
                remainder = buffer[idx + len(close_tag):]
                if remainder:
                    yield remainder
                continue

            # Pas de balise fermante pour l'instant : on ne tranche PAS sur
            # une longueur (voir docstring : aucun seuil n'est fiable). On
            # continue d'accumuler en silence jusqu'à la fin du flux.

        # Flux terminé sans jamais avoir basculé en diffusion directe :
        # soit une réponse courte SANS "<think>" (jamais assez longue pour
        # franchir le seuil ci-dessus, ex. "Oui." pour un modèle qui ne
        # raisonne pas) : on la diffuse tel quel plutôt que la perdre en
        # silence. Soit un bloc <think> resté ouvert (réponse tronquée,
        # ex. connexion coupée en pleine réflexion) : on coupe tout à
        # partir de "<think>" plutôt que de laisser fuiter du raisonnement
        # brut, quitte à ne rien renvoyer si tout était dedans.
        if not started and buffer:
            idx = buffer.find("<think>")
            visible = buffer[:idx] if idx != -1 else buffer
            if visible:
                yield visible


def is_model_available(model: str) -> bool:
    """Vrai si `model` est déjà tiré localement dans Ollama.

    Sert à décider une escalade vers un modèle plus costaud (ex.
    `settings.llm_model_heavy`) SANS jamais déclencher un téléchargement à
    la volée ni un appel bloquant sur du matériel contraint (Raspberry Pi) :
    si le modèle n'est pas déjà là, on reste sur le modèle par défaut.
    """
    if ollama is None:
        return False
    try:
        client = ollama.Client(host=settings.ollama_host)
        installed = {m.model for m in client.list().models}
    except Exception:
        logger.warning("Impossible de vérifier les modèles Ollama disponibles.")
        return False
    return model in installed


def ollama_status() -> dict:
    """Vrai état d'Ollama (`GET /system/status`, aelyn-api) : joignable ou
    non, et la liste réellement installée si oui. Jamais une supposition
    ("sûrement bon") : un `reachable=False` explicite plutôt qu'un
    `is_model_available` qui masquerait silencieusement la DIFFÉRENCE
    entre "Ollama répond mais ce modèle précis n'est pas tiré" et "Ollama
    ne répond pas du tout", deux causes très différentes à diagnostiquer."""
    if ollama is None:
        return {"reachable": False, "error": "paquet python 'ollama' non installé", "models": []}
    try:
        client = ollama.Client(host=settings.ollama_host)
        models = sorted(m.model for m in client.list().models if m.model)
        return {"reachable": True, "error": None, "models": models}
    except Exception as exc:
        return {"reachable": False, "error": str(exc), "models": []}


def list_available_models() -> list[str]:
    """Modèles réellement tirés localement dans Ollama (`ollama list`),
    pour `GET /settings/models` (aelyn-api) : la liste déroulante du
    frontend doit proposer de VRAIS modèles installés, jamais du texte
    libre qui échouerait au premier appel une fois assigné à un rôle
    (`LLM_MODEL`/`LLM_MODEL_HEAVY`/`LLM_MODEL_CAREER`).

    Liste VIDE (pas d'exception) si Ollama est injoignable : laisse
    l'appelant décider comment le signaler (ex. un message honnête côté
    frontend plutôt qu'une 500 brute), cohérent avec `is_model_available`
    ci-dessus qui renvoie `False` plutôt que de lever dans le même cas.
    """
    if ollama is None:
        return []
    try:
        client = ollama.Client(host=settings.ollama_host)
        return sorted(m.model for m in client.list().models if m.model)
    except Exception:
        logger.warning("Impossible de lister les modèles Ollama disponibles.")
        return []

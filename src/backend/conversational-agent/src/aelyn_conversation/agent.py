"""Agent conversationnel d'AELYN : traduit une phrase libre en commande.

Le LLM (ou le fast router) interprète l'intention et rédige une
reformulation courte ; il n'exécute jamais rien lui-même.
`aelyn_email.agent.run_command` reste seul responsable de l'exécution.

Deux modes d'entrée :
- clavier (`_run_text`) : chaque ligne tapée est traitée directement.
- voix (`_run_voice`) : AELYN reste en veille et n'écoute activement
  qu'après avoir entendu son mot d'activation ("Éline"). Une fois
  activée, elle reste "en ligne" jusqu'à obtenir une phrase exploitable
  (silence/incompréhension ne renvoient PAS en veille, pas besoin de
  redire "Éline" pour se répéter).

Confirmation : seules `valider`/`rejeter` changent l'état de la boîte
mail (envoi, archivage) et restent confirmées avant exécution.
`verifier`/`triage`/`rapport` ne modifient jamais rien (triage ne fait
que PROPOSER, cf. `EmailAgent.triage`) et s'exécutent directement.

`_try_read_back` permet de redemander la lecture d'un résultat déjà
affiché ("lis le premier", "lis le résultat 3", "lis le mail de
LinkedIn") sans refaire tourner la commande d'origine.
"""

from __future__ import annotations

import contextlib
import io
import logging
import queue
import random
import re
import sys
import threading
import unicodedata
from datetime import datetime

from rich.align import Align
from rich.console import Console
from rich.panel import Panel

from aelyn.core.chat_history import ChatHistory
from aelyn.core.config import settings
from aelyn.core.llm import KEEP_ALIVE_OCCASIONAL, LLMClient, LLMError, is_model_available
from aelyn.core.spinner import Spinner
from aelyn_career.agent import run_command as career_run_command
from aelyn_career.application_writer import (
    ApplicationWriter,
    format_cv_text,
    offer_text,
)
from aelyn_career.france_travail.offers import FTOffers
from aelyn_email.agent import EmailAgent, run_command
from aelyn_email.models import Mail
from aelyn_media.agent import MediaController
from aelyn_media.camera import show_camera

from aelyn_conversation.fast_router import fast_intent
from aelyn_conversation.models import Intent, TurnResult
from aelyn_conversation.prompts import (
    ACK_CANCEL,
    ACK_DONE,
    ACK_ERROR,
    ACK_STARTING,
    GREETINGS,
    NOT_UNDERSTOOD,
    SILENCE,
    SYSTEM_DRAFT,
    SYSTEM_INTENT,
    SYSTEM_PERSONA,
    SYSTEM_REFORMULATE,
    SYSTEM_SUMMARY,
    WAKE_ACK,
)

logger = logging.getLogger(__name__)

READ_ONLY_COMMANDS = {"verifier", "triage", "rapport", "chercher_offres", "media", "camera"}
CAREER_COMMANDS = {"chercher_offres"}
MEDIA_COMMANDS = {"media"}
CAMERA_COMMANDS = {"camera"}

# ~5 échanges de contexte pour la conversation libre, assez pour ne
# pas oublier le sujet d'un tour à l'autre, sans laisser grossir le
# prompt indéfiniment sur une session longue.
_MAX_CONVERSATION_HISTORY = 10

# Variantes plausibles de ce que Google Speech peut renvoyer pour "Éline"
# (le nom que prononce AELYN, cf. SYSTEM_PERSONA), accents déjà retirés
# par `_normalize`, donc "éline" et "eline" sont la même entrée ici.
WAKE_WORDS = {"eline", "aelyn", "aline"}

READ_BACK_RE = re.compile(
    # "montre\w*" est AUSSI le mot-clé de "montre la caméra de l'entrée"
    # (cf. fast_router.py), plutôt que l'exclure ici (ce qui empêchait
    # "montre les offres"/"montre tous les mails" de fonctionner, cf.
    # rapport utilisateur réel), `_try_read_back` bascule explicitement
    # sur la caméra quand le mot "caméra"/"webcam" est présent (voir plus
    # bas) : la caméra n'est jamais interceptée par erreur, et "montre"
    # marche pour relire une liste comme "affiche"/"liste".
    r"\b(?:lis|relis|r[ée]p[èe]te|lire|affiche\w*|liste\w*|montre\w*)\b", re.IGNORECASE
)
# "affiche LES offres"/"montre TOUS les mails" : redemande la LISTE
# ENTIÈRE déjà trouvée, pas un item précis ("lis le premier") : sans
# cette distinction, une telle phrase tombait dans la recherche par
# mot-clé de `_resolve_reference` (pensée pour UN seul élément), ne
# matchait jamais rien, et retombait sur `_last_said` (la simple phrase
# "6 offres trouvées", pas la liste) : le bug concret rapporté, "cherche
# des offres" puis "affiche les offres" reperdait la liste au lieu de la
# réafficher.
_SHOW_ALL_RE = re.compile(r"\b(les|toutes?|tous)\b", re.IGNORECASE)
# Clés déjà sans accent : comparées à `_normalize(...).lower()`, qui
# retire les accents avant la recherche (une entrée accentuée ne
# matcherait donc jamais). "deuxieme"/"second"/"seconde" désignent le
# même index (1) ; la voix hésite entre les deux formes selon l'usager.
_INDEX_WORDS = {
    "premier": 0,
    "deuxieme": 1,
    "second": 1,
    "seconde": 1,
    "troisieme": 2,
    "quatrieme": 3,
    "cinquieme": 4,
    "dernier": -1,
}

# "quelle heure est-il"/"on est le combien" : interceptés AVANT le
# routage LLM. Constaté en direct : sans ça, le LLM (routage d'intention)
# classe parfois cette phrase en `rapport`/`verifier` (aucune commande
# "heure" n'existe, il improvise vers la plus proche). Même sans cette
# confusion, laisser `_converse` répondre serait pire : le LLM n'a aucune
# notion fiable de l'heure réelle et inventerait une réponse, contraire à
# la règle "jamais d'information inventée" (cf. SYSTEM_PERSONA) : seule
# l'horloge système fait foi, jamais le LLM.
# "bonjour"/"salut" SEUL (rien d'autre dans la phrase) : interceptés
# AVANT le routage LLM pour la même raison que l'heure/la date ci-dessous
# (constaté en direct, dès le début des tests réels : "bonjour" tout seul
# se faisait classer en `verifier`, déclenchant une vérification de
# mails jamais demandée). Ancré sur la phrase ENTIÈRE (pas juste son
# début) : "bonjour, vérifie mes mails" doit toujours déclencher la
# vraie vérification, seul un salut SANS rien d'autre doit être
# intercepté ici.
GREETING_RE = re.compile(
    r"^(bonjour|bonsoir|salut|coucou|hello|hey+|yo|cc)[\s,!.]*(eline|aelyn)?[\s,!.]*$",
    re.IGNORECASE,
)
GREETING_REPLIES = [
    "Bonjour ! Qu'est-ce que je peux faire pour toi ?",
    "Salut ! Je t'écoute.",
    "Bonjour, je suis là. Tu veux que je regarde tes mails, des offres, autre chose ?",
]
# "cherche 20 offres"/"montre-moi 30 offres"/"je veux 15 résultats" :
# capture le nombre explicitement demandé, en filet de sécurité derrière
# l'extraction LLM (cf. `_dispatch_phrase`, peu fiable sur ce champ précis).
_OFFERS_LIMIT_RE = re.compile(r"\b(\d{1,3})\s+(?:offres?|resultats?)\b", re.IGNORECASE)
# "cherche des offres de/pour X" : constaté en direct, l'extraction LLM de
# `mots_cles` échoue de façon reproductible selon le connecteur utilisé
# SANS nombre dans la phrase ("...offres de data scientist" ->
# mots_cles=None à CHAQUE appel ; "...offres en X"/"...offres chez X"
# fonctionnent, et "...20 offres de X" aussi) — jamais corrigé en
# retouchant SYSTEM_INTENT (même constat que `_OFFERS_LIMIT_RE` pour
# `limit`), filet de sécurité déterministe à la place. Volontairement
# appliqué sur la phrase ORIGINALE (pas `_normalize`) pour garder les
# accents du métier/mot-clé capturé (meilleure recherche France Travail).
_OFFERS_KEYWORDS_RE = re.compile(r"\boffres?\s+(?:d['’]|de\s+|en\s+|chez\s+|pour\s+)(.+)$", re.IGNORECASE)
_TRAILING_CONTRACT_RE = re.compile(r"\s+en\s+(cdi|cdd|stage|alternance)\s*$", re.IGNORECASE)
TIME_RE = re.compile(r"\bquelle\s+heure\b|\bheure\s+est[\s-]?il\b", re.IGNORECASE)
DATE_RE = re.compile(
    r"\bquel\s+jour\b|\bquelle\s+date\b|\bon\s+est\s+le\s+combien\b|\bquel\s+jour\s+on\s+est\b",
    re.IGNORECASE,
)
_JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

# "résume le mail de X" / "brouillon pour le mail de X" / "reformule ça" :
# interceptés AVANT le routage LLM (comme la lecture arrière) : sans ça,
# le LLM improvise vers la commande existante la plus proche (ex.
# "résume" → `rapport`, qui résume le JOURNAL, pas le mail demandé).
SUMMARIZE_RE = re.compile(r"\bresum\w*\b", re.IGNORECASE)
# `Intent.commande` n'a AUCUNE catégorie "brouillon de mail" (cf.
# models.py) : elle n'existe que via cette interception. "brouillon"/
# "rédige"/"draft" suffisent seuls (ce sont déjà des mots-objets, pas de
# risque de faux positif hors contexte mail). Les verbes plus génériques
# ("prépare", "génère", "écris", "réponds"...) ne sont acceptés QUE
# combinés à "mail"/"mails" : seuls, ils capteraient des phrases sans
# rapport ("prépare-toi", "réponds-moi vite") ; observé en pratique que
# "prépare un mail pour X"/"réponds à ce mail" tombaient sinon dans
# `inconnu` (aucune catégorie où les faire atterrir) au lieu de
# déclencher un brouillon, alors que l'intention était évidente.
DRAFT_RE = re.compile(
    r"\bbrouillon\w*\b|\br[ée]dige\w*\b|\bdraft\b"
    r"|\b(?:pr[ée]par\w*|g[ée]n[èe]r\w*|[ée]cri\w*|r[ée]pon\w*)\b.*\bmails?\b"
    r"|\bmails?\b.*\b(?:pr[ée]par\w*|g[ée]n[èe]r\w*|[ée]cri\w*|r[ée]pon\w*)\b",
    re.IGNORECASE,
)
REFORMULATE_RE = re.compile(r"\breformul\w*\b", re.IGNORECASE)
DESCRIBE_OFFER_RE = re.compile(r"\bd[ée]cri\w*\b|\bd[ée]taill\w*\b", re.IGNORECASE)
# "prépare-moi un CV/une lettre de motivation pour cette offre" :
# interceptés AVANT `_try_draft` (qui capterait "rédige" en pensant à un
# brouillon de mail) et avant le routage LLM (pas de commande dédiée dans
# `Intent`, il improviserait vers `chercher_offres`).
PREPARE_CV_RE = re.compile(r"\b(cv|curriculum)\b", re.IGNORECASE)
PREPARE_LM_RE = re.compile(
    r"\blettre\w*\s+de\s+motivation\b|\bcandidature\b", re.IGNORECASE
)
# "affine/améliore/retravaille cette lettre de motivation" : interceptée
# AVANT `_try_prepare_lm` (qui matche aussi "lettre de motivation" et
# régénérerait une lettre entièrement neuve au lieu de partir de celle
# déjà produite).
REFINE_LM_RE = re.compile(r"\b(affin\w*|am[ée]lior\w*|retravaill\w*|corrig\w*)\b", re.IGNORECASE)

# Réponse au "veux-tu que je..." posé par `_try_draft`/`_try_prepare_cv`/
# `_try_prepare_lm`/`_try_refine_lm` avant d'exécuter (cf. `_pending_action`) :
# volontairement LARGE plutôt qu'un simple "oui"/"non" exact (`_is_yes`,
# pensé pour un prompt CLI explicite `[o/N]`, trop strict pour une réponse
# vocale naturelle). Variantes courantes à l'oral comme au clavier.
_CONFIRM_RE = re.compile(
    r"\b(oui|ouais|ouaip|yes|yep|ok|okay|d['\s]?accord|vas[\s-]?y|"
    r"carr[ée]ment|bien\s*s[uû]r|[ée]videmment|allez|go|affirmatif|"
    r"confirme\w*|exact)\b",
    re.IGNORECASE,
)
_DECLINE_RE = re.compile(
    r"\b(non|nan|annul\w*|laisse\s*tomber|pas\s*maintenant|pas\s*la\s*peine|"
    r"stop|arr[êe]t\w*|jamais)\b",
    re.IGNORECASE,
)

# Mots à ignorer lors de l'extraction de mots-clés pour retrouver UN mail
# précis parmi les derniers affichés (sinon "le", "mail", "pour" etc.
# matcheraient n'importe quelle entrée). Formes normalisées (sans accent).
_REFERENCE_STOPWORDS = {
    "lis", "relis", "repete", "lire",
    "resume", "resumer", "resumez", "resumes", "resumez-moi",
    "brouillon", "redige", "rediger", "redigez", "draft",
    "reformule", "reformuler", "reformulez",
    "decris", "decrire", "decrivez", "detaille", "detailler", "detaillez",
    "mail", "mails", "email", "emails", "offre", "offres", "pour", "avec", "dans", "moi",
    # Mots-cadres de "prépare-moi un CV"/"rédige une lettre de motivation" :
    # sans eux, "cette offre" dans "rédige une LM pour cette offre" laisse
    # "lettre"/"motivation" comme mots-clés (aucun ne matchant jamais une
    # vraie offre), qui bloquaient le repli sur la dernière offre évoquée.
    "cv", "curriculum", "lettre", "motivation", "candidature",
    "prepare", "preparer", "preparez", "preparez-moi",
    # Mots-cadres ajoutés avec `DRAFT_RE` ("prépare un mail"/"réponds à ce
    # mail") : même raison que "prepare" ci-dessus.
    "genere", "generer", "generez", "ecris", "ecrire", "ecrivez",
    "reponds", "repondre", "repondez", "reponse",
    "affine", "affiner", "affinez", "ameliore", "ameliorer", "ameliorez",
    "retravaille", "retravailler", "retravaillez", "corrige", "corriger", "corrigez",
    # Articles/prépositions courts : nécessaires maintenant que le filtre de
    # longueur des mots-clés est descendu à 2 caractères (pour laisser
    # passer des noms d'entreprise courts comme "EDF", "IBM", "BNP"), sans
    # ça, "de"/"le"/"la" matcheraient n'importe quel mail ou offre.
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "ce", "cet", "cette",
    "ca", "chez",
}

# Repère "cette offre"/"ce mail" quel que soit le verbe qui les précède.
# `_REFERENCE_STOPWORDS` ne peut jamais couvrir tous les verbes de cadrage
# possibles ("prépare", "fais", "génère", "crée"...) : un nouveau mot pas
# encore recensé y reste un mot-clé, empêche le repli sur `_offer_focus`/
# `_mail_focus`, et la phrase échoue ("je ne sais pas de quelle offre tu
# parles") alors que l'offre était déjà connue (observé deux fois avec
# deux verbes différents). Un déterminant démonstratif est un signal bien
# plus fiable que "aucun mot-clé ne matche" : il n'y a besoin d'aucune
# liste à maintenir.
_DEMONSTRATIVE_RE = re.compile(r"\b(cette|cet|ce|ca)\b", re.IGNORECASE)


def _is_demonstrative_reference(phrase: str) -> bool:
    return bool(_DEMONSTRATIVE_RE.search(_normalize(phrase).lower()))

# "on va bavarder", "je veux causer", "discutons" : bascule en conversation
# continue (cf. `_run_conversation`) plutôt qu'en routage de commande.
CONVERSATION_TRIGGER_RE = re.compile(r"\b(bavard\w*|caus\w*|convers\w*|discut\w*)\b", re.IGNORECASE)


# Rendu "bulles SMS" : toi à droite, AELYN à gauche, juste de la mise en
# forme (Rich), aucun changement de logique de conversation.
_console = Console()
_BUBBLE_WIDTH = 60


def _print_bubble(text: str, *, align: str, style: str) -> None:
    panel = Panel(text, border_style=style, width=min(_BUBBLE_WIDTH, _console.width))
    _console.print(Align.right(panel) if align == "right" else Align.left(panel))


def _print_user_bubble(text: str) -> None:
    _print_bubble(text, align="right", style="cyan")


def _print_agent_bubble(text: str) -> None:
    _print_bubble(text, align="left", style="green")


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            current.append(min(previous[j] + 1, current[-1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def _contains_wake_word(text: str) -> bool:
    """« Éline » se fait souvent tronquer d'une lettre par la reconnaissance
    vocale (ex. "Elin" au lieu de "Eline") : une correspondance exacte
    ratait ces variantes à un caractère près, obligeant à répéter le mot
    d'activation. Distance de Levenshtein <= 1 les absorbe sans pour
    autant déclencher sur un mot sans rapport."""
    words = re.findall(r"\w+", _normalize(text).lower())
    return any(any(_levenshtein(w, wake) <= 1 for wake in WAKE_WORDS) for w in words if len(w) >= 3)


def _is_yes(text: str) -> bool:
    words = text.strip().lower().split()
    return any(w in {"o", "oui", "y", "yes"} for w in words)


class _StreamSink:
    """File d'attente thread-safe utilisée par `handle_message_stream`
    (`POST /chat/message/stream`, SSE) : `_dispatch_phrase` tourne dans un
    thread à part (il bloque sur le LLM/IMAP/France Travail), pendant que
    le générateur consommé par l'API lit cette file au fil de l'eau dans
    le thread appelant (la boucle ASGI), sans jamais dupliquer le routage
    lui-même (`_dispatch_phrase` reste le seul endroit qui décide quoi
    faire d'une phrase, CLI/API bloquante/API en flux y passent toutes
    les trois). `None` signale la fin du tour."""

    def __init__(self) -> None:
        self.queue: "queue.Queue[str | None]" = queue.Queue()

    def push(self, fragment: str) -> None:
        if fragment:
            self.queue.put(fragment)

    def close(self) -> None:
        self.queue.put(None)


class _Heartbeat:
    """Sentinelle produite par `handle_message_stream` quand aucun
    fragment réel n'est arrivé depuis `_HEARTBEAT_INTERVAL_SECONDS` :
    un rechargement de modèle Ollama forcé par la contention VRAM (cf.
    `ConversationalAgent.__init__`) peut prendre plusieurs dizaines de
    secondes SANS produire le moindre texte, avant même le premier token
    du LLM. Sans un minimum d'octets transmis pendant ce silence, un
    timeout d'INACTIVITÉ côté client/proxy (distinct du timeout de durée
    TOTALE déjà résolu par le simple fait de streamer) pourrait encore se
    déclencher. Pas un fragment de texte : l'appelant (cf.
    `aelyn_api.routers.chat`) le traduit en commentaire SSE, ignoré par
    `EventSource`, jamais affiché côté client."""


_HEARTBEAT = _Heartbeat()
_HEARTBEAT_INTERVAL_SECONDS = 15.0


class ConversationalAgent:
    def __init__(self, voice: bool = False) -> None:
        self.llm = LLMClient()
        # Routage d'intention : escalade vers le modèle plus costaud
        # (settings.llm_model_heavy) SEULEMENT s'il est déjà disponible
        # localement, jamais de téléchargement à la volée, jamais un
        # changement de comportement sur du matériel contraint (Raspberry
        # Pi) qui n'a que le modèle léger. Sinon on reste sur `self.llm`.
        #
        # `keep_alive` COURT (`_KEEP_ALIVE_OCCASIONAL`) : mesuré sur un GPU
        # 6 Go (RTX 3060 Laptop) que `self.llm` (léger) et ce modèle
        # d'escalade ne coexistent JAMAIS en VRAM dès qu'ils diffèrent
        # (confirmé via `ollama ps` : charger l'un ÉVINCE ENTIÈREMENT
        # l'autre, pas un simple ralentissement). Comme l'escalade se
        # déclenche à CHAQUE tour non capté par `fast_router.py`, un
        # `keep_alive` long (30 min, par défaut pour `self.llm`) le
        # laisserait occuper la VRAM bien après son usage, forçant
        # `self.llm` à se recharger pour la toute PROCHAINE action
        # (triage, résumé, conversation...) même des minutes plus tard.
        # Un délai court n'évite pas le premier rechargement (inévitable
        # tant que les deux modèles diffèrent sur ce GPU), mais rend à
        # `self.llm` la VRAM bien plus vite entre deux usages espacés.
        self.intent_llm = self.llm
        if is_model_available(settings.llm_model_heavy):
            self.intent_llm = LLMClient(
                model=settings.llm_model_heavy, keep_alive=KEEP_ALIVE_OCCASIONAL
            )
        # Un seul EmailAgent (et donc un seul client Ollama sous-jacent)
        # pour toute la session, au lieu d'en recréer un à chaque tour.
        self.email_agent = EmailAgent(llm=self.llm)
        # Même principe côté carrière : un seul FTOffers, pour réutiliser
        # l'access_token au lieu de se reconnecter à chaque recherche.
        self.offers_agent = FTOffers()
        # Rédaction CV/lettre de motivation : un seul writer, pour réutiliser
        # son ProfilManager/LLMClient au lieu d'en recréer un par candidature.
        self.application_writer = ApplicationWriter()
        # Créé au premier usage seulement (pas ici) : se connecter à la TV
        # ouvre un thread/event loop dédié et peut déclencher un appairage
        # interactif, inutile de payer ce coût pour une session qui ne
        # parle jamais de la télé.
        self.media_controller: MediaController | None = None

        # Derniers résultats affichés (verifier/triage) : la version
        # texte pour "lis le premier", les `Mail` d'origine pour
        # "résume le mail de X" / "brouillon pour ce mail".
        self._last_results: list[str] = []
        self._last_mails: list[Mail] = []
        # Même principe pour "décris l'offre de X" après `chercher_offres`.
        self._last_offers: list[dict] = []
        # Nature + contenu structuré de la DERNIÈRE liste affichée (mails
        # ou offres), pour "affiche les offres"/"montre tous les mails"
        # (cf. `_try_read_back` et `_SHOW_ALL_RE`) : distinct de
        # `_last_results` (les LIGNES texte) : ceci garde la donnée
        # structurée d'origine, pour qu'un appelant API puisse la
        # renvoyer en JSON plutôt qu'en phrase.
        self._last_list_type: str | None = None
        self._last_list_payload: list[dict] | None = None
        # Résultat structuré du TOUR EN COURS uniquement (remis à zéro à
        # chaque phrase par `_dispatch_phrase`), ce que `handle_message()`
        # (point d'entrée API) renvoie comme `TurnResult.result_type`/
        # `.results`. Distinct de `_last_list_*` ci-dessus, qui PERSISTE
        # entre les tours (nécessaire pour qu'un futur "affiche les"
        # retrouve la liste même si le tour courant n'en produit aucune).
        self._turn_result_type: str | None = None
        self._turn_result_payload: list[dict] | None = None
        # Dernier mail/offre effectivement résolu par `_find_mail`/
        # `_find_offer`, sert de repère pour une référence purement
        # démonstrative sans autre mot distinctif ("cette offre", "ce
        # mail"), qui sinon ne matcherait rien (cf. ces méthodes).
        self._mail_focus: Mail | None = None
        self._offer_focus: dict | None = None
        # Lequel des deux a été résolu le plus récemment, utilisé par
        # `_try_summarize`, seule action ambiguë entre mail et offre
        # ("résume ça" peut viser l'un ou l'autre), pour savoir lequel
        # essayer en premier plutôt que de toujours privilégier le mail.
        self._last_focus_kind: str | None = None
        # Dernière lettre de motivation générée + l'offre correspondante,
        # pour "affiner cette lettre de motivation" (cf. `_try_refine_lm`).
        self._last_lm: str | None = None
        self._last_lm_offer: dict | None = None
        # Action LENTE/CONSÉQUENTE en attente de confirmation ("veux-tu que
        # je... ?"), posée par `_try_draft`/`_try_prepare_cv`/
        # `_try_prepare_lm`/`_try_refine_lm` AVANT d'exécuter quoi que ce
        # soit (cf. `_try_pending_confirmation`) : un brouillon de mail ou
        # un CV/une lettre engagent du contenu qui représente l'utilisateur
        # et coûtent un appel LLM potentiellement long, contrairement à une
        # simple lecture/affichage, d'où la confirmation PROACTIVE plutôt
        # que l'exécution immédiate ou l'échec sec sur une référence
        # ambiguë. `None` = rien en attente (cas normal). Remis à `None`
        # dès que le tour SUIVANT répond (confirmation, refus, ou même une
        # phrase sans rapport, cf. `_dispatch_phrase`) : jamais exécutée
        # "en retard" sur un tour ultérieur sans lien, même des minutes
        # plus tard.
        self._pending_action: dict | None = None
        # Dernière chose dite par AELYN, pour "reformule ça".
        self._last_said: str = ""
        # Non-`None` UNIQUEMENT pendant un tour de `handle_message_stream`
        # (cf. plus bas) : `_say`/`_say_stream`/`_ack_processing` y
        # poussent leurs fragments de texte en plus de leur comportement
        # habituel (bulle Rich, mémoire, voix), pour que l'appelant (le
        # thread qui consomme ce générateur) les reçoive au fil de l'eau.
        # `None` en dehors d'un tour en flux (CLI, `handle_message`
        # bloquant) : ces méthodes ne font alors rien de plus qu'avant.
        self._stream_sink: _StreamSink | None = None
        # Historique de la conversation libre (`_converse`), borné pour
        # ne pas grossir indéfiniment : sans lui, chaque tour oubliait
        # instantanément le sujet dont on venait de parler.
        self._conversation_history: list[dict[str, str]] = []
        # Mémoire LONG terme (SQLite, survit au redémarrage), contrairement
        # à `_conversation_history` ci-dessus (en mémoire, bornée, pour le
        # contexte du prompt) : sert à exposer GET /chat/history côté
        # aelyn-api. Écriture au fil de l'eau via `_remember()`.
        self.chat_history = ChatHistory(settings.chat_history_path)
        # Vrai "Bonjour" seulement à la toute première activation de la
        # session ; les suivantes n'ont droit qu'à un accusé bref.
        self._greeted = False
        # Compteur d'échecs voix consécutifs (silence/incompris), remis à
        # zéro dès qu'une phrase est comprise, voir `_report_voice_error`.
        self._silence_streak = 0

        self.voice_mod = None
        if voice:
            from aelyn.core import voice as voice_mod

            self.voice_mod = voice_mod

    def reload_llm_clients(self) -> None:
        """Reconstruit `self.llm`/`self.intent_llm`/`self.email_agent.llm`
        depuis `settings.llm_model`/`settings.llm_model_heavy` COURANTS,
        même logique que la construction dans `__init__` ci-dessus.

        Nécessaire car `ConversationalAgent` est un singleton de longue
        durée côté API (`aelyn_api.deps.get_conversational_agent`) : ses
        `LLMClient` sont construits UNE SEULE FOIS au démarrage, un
        `PATCH /settings` qui change `llm_model`/`llm_model_heavy` ne s'y
        refléterait donc jamais tout seul. Appelée par le routeur settings
        juste après avoir persisté le nouveau modèle.

        `self.email_agent.llm` est réassigné explicitement : `EmailAgent`
        garde sa PROPRE référence vers l'ancien `LLMClient` (passée par
        valeur à sa construction), la remplacer ici évite qu'il continue
        de parler à l'ancien modèle après ce rechargement."""
        self.llm = LLMClient()
        self.intent_llm = self.llm
        if is_model_available(settings.llm_model_heavy):
            self.intent_llm = LLMClient(
                model=settings.llm_model_heavy, keep_alive=KEEP_ALIVE_OCCASIONAL
            )
        self.email_agent.llm = self.llm

    # ---------------------------------------------------------------- E/S

    def _remember(self, role: str, content: str) -> None:
        """Écrit un tour dans la mémoire longue (SQLite), jamais fatal :
        un problème d'écriture disque ne doit jamais casser la conversation
        elle-même, seulement priver `/chat/history` de ce tour."""
        if not content or not content.strip():
            return
        try:
            self.chat_history.append(role, content)
        except Exception:
            logger.exception("Écriture de l'historique de conversation impossible")

    def _finish_say(
        self, text: str, *, spoken: str | None = None, _already_streamed: bool = False
    ) -> None:
        """Partie commune à `_say()` et `_say_stream()` : mémoriser + parler.
        Séparée de l'affichage écrit, qui diffère entre les deux (bulle
        Rich d'un bloc vs texte déjà imprimé au fil de l'eau).

        `spoken`, si fourni, remplace `text` UNIQUEMENT pour la synthèse
        vocale (ex. un accusé bref "Voilà" plutôt qu'une liste de mails
        potentiellement longue) ; `text` reste dans tous les cas ce qui
        est mémorisé (`_last_said`, historique, retour API).

        `_already_streamed=True` (passé par `_say_stream` uniquement) :
        `text` a déjà été poussé fragment par fragment dans
        `_stream_sink`, ne pas le pousser une seconde fois ici d'un bloc."""
        self._last_said = text
        self._remember("assistant", text)
        if self._stream_sink is not None and not _already_streamed:
            self._stream_sink.push(text)
        if self.voice_mod:
            try:
                # Spinner "comme Siri" pendant que Kokoro/Edge TTS parle :
                # sans lui, le terminal reste figé le temps de la synthèse,
                # indiscernable d'un plantage.
                with Spinner("AELYN parle…"):
                    self.voice_mod.speak(spoken if spoken is not None else text)
            except self.voice_mod.VoiceError as exc:
                print(f"(voix indisponible : {exc})", file=sys.stderr)

    def _say(self, text: str) -> None:
        _print_agent_bubble(text)
        self._finish_say(text)

    def _say_stream(self, chunks) -> str:
        """Comme `_say()`, mais pour un texte produit fragment par
        fragment par le LLM (cf. `LLMClient.text_stream`) : imprime
        chaque fragment dès qu'il arrive au lieu d'attendre la réponse
        complète : sur une tâche longue (lettre de motivation, résumé,
        conversation libre), la latence PERÇUE chute radicalement même
        si le temps total ne change pas (plus de "je m'en occupe" suivi
        d'un silence de plusieurs dizaines de secondes).

        Contrepartie assumée : pas de bulle Rich ici (elle ne peut pas se
        redessiner incrémentalement) : un simple flux de texte brut,
        préfixé une fois. La voix (si activée) reste jouée à la fin, une
        fois le texte complet connu ; impossible de synthétiser un
        fragment isolé de façon naturelle.

        Retourne le texte complet assemblé, pour les appelants qui en
        ont besoin ensuite (ex. `_last_lm` côté lettre de motivation).

        Si `_stream_sink` est renseigné (tour de `handle_message_stream`,
        cf. plus bas), chaque fragment y est aussi poussé dès qu'il
        arrive : c'est le chemin qui profite réellement du streaming côté
        API (SSE), exactement le même texte que ce qui s'imprime ici au
        fil de l'eau côté CLI.
        """
        print("AELYN  ", end="", flush=True)
        parts: list[str] = []
        for fragment in chunks:
            print(fragment, end="", flush=True)
            parts.append(fragment)
            if self._stream_sink is not None:
                self._stream_sink.push(fragment)
        print()
        text = "".join(parts)
        self._finish_say(text, _already_streamed=True)
        return text

    def _listen(self, prompt: str = "> ") -> str:
        if not self.voice_mod:
            return input(prompt).strip()
        with Spinner("Je t'écoute…"):
            return self.voice_mod.transcribe()

    def _ack_processing(self) -> None:
        """Signale qu'une tâche (appel LLM) est en cours, à l'écrit ET à
        l'oral : sans quoi un résumé/brouillon qui prend quelques secondes
        laisse l'utilisateur sans aucun retour pendant l'attente.

        En flux (`_stream_sink` renseigné), cet accusé est aussi poussé
        comme TOUT PREMIER fragment, avant même que le LLM n'ait produit
        un seul token : côté API, c'est ce qui élimine le "gel" perçu
        pendant un rechargement de modèle (plusieurs dizaines de secondes
        possibles, cf. contention VRAM) ou le simple temps avant le
        premier token, pas seulement la génération elle-même."""
        ack = random.choice(ACK_STARTING)
        _print_agent_bubble(ack)
        if self._stream_sink is not None:
            self._stream_sink.push(ack + "\n\n")
        if self.voice_mod:
            self.voice_mod.speak_async(ack)

    def _run_long_task(self, fn, *args, heartbeat_every: float = 20.0, **kwargs):
        """Exécute `fn` en restant visiblement présent pendant l'attente :
        une tâche comme un CV ou une lettre de motivation (~1-2 min, LLM
        lourd) laissait sinon l'utilisateur sans aucun signe entre le "je
        m'en occupe" initial et le résultat final, indiscernable d'un
        plantage. Le signal de vie est seulement ÉCRIT (pas parlé) : le
        redire à voix haute toutes les 20s serait plus gênant qu'utile."""
        done = threading.Event()

        def _heartbeat() -> None:
            elapsed = 0.0
            while not done.wait(heartbeat_every):
                elapsed += heartbeat_every
                print(f"… toujours en cours ({int(elapsed)}s)")

        thread = threading.Thread(target=_heartbeat, daemon=True)
        thread.start()
        try:
            return fn(*args, **kwargs)
        finally:
            done.set()
            thread.join(timeout=1)

    def _report_voice_error(self, exc: Exception) -> None:
        """Le silence et l'incompréhension se SIGNALENT à voix haute, mais
        pas à CHAQUE fois : un bruit ambiant anodin (souris, chaise) peut
        déclencher plusieurs faux "je n'ai pas compris" d'affilée, et les
        dire tous rend l'assistant pénible. On ne parle qu'au 1er essai
        raté, puis silencieusement toutes les deux tentatives suivantes."""
        self._silence_streak += 1
        should_speak = self._silence_streak == 1 or self._silence_streak % 3 == 0

        if self.voice_mod and isinstance(exc, self.voice_mod.VoiceTimeout):
            if should_speak:
                self._say(random.choice(SILENCE))
        elif self.voice_mod and isinstance(exc, self.voice_mod.VoiceNotUnderstood):
            if should_speak:
                self._say(random.choice(NOT_UNDERSTOOD))
        else:
            print(f"Erreur : {exc}", file=sys.stderr)

    # --------------------------------------------------------------- run

    def run(self) -> int:
        return self._run_voice() if self.voice_mod else self._run_text()

    def _run_text(self) -> int:
        """Mode clavier : chaque ligne tapée est une phrase à traiter directement."""
        print("AELYN, mode conversationnel. Tape une phrase, ou 'quitter' pour sortir.")
        print(
            "Exemples : « qu'est-ce qu'il y a de nouveau ? », « valide la 3 », "
            "« raconte-moi ta journée »"
        )

        while True:
            try:
                phrase = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0

            if not phrase:
                continue
            _print_user_bubble(phrase)
            if not self._handle_phrase(phrase):
                return 0

    def _run_voice(self) -> int:
        """Mode voix : veille jusqu'au mot d'activation, puis traite les commandes
        qui suivent (cf. `_activate`) tant qu'il n'y a pas plus de
        `settings.wake_timeout_seconds` de silence, puis re-veille.

        Limite assumée : faute d'un moteur de mot d'activation local
        dédié, la veille réécoute via la même reconnaissance cloud que
        le reste (Google), donc des requêtes réseau en continu tant
        qu'on n'a pas dit « Éline », pas un vrai capteur local passif.
        """
        print("AELYN, mode vocal. Dis « Éline » pour m'activer, ou Ctrl+C pour quitter.")

        while True:
            try:
                # calibrate=False : la veille tourne en boucle serrée,
                # recalibrer le bruit ambiant à chaque cycle n'ajoute
                # que de la latence pour détecter un mot très court.
                phrase = self.voice_mod.transcribe(
                    timeout=5.0, phrase_time_limit=4.0, quiet=True, calibrate=False
                )
            except self.voice_mod.VoiceTimeout:
                continue  # silence pendant la veille : rien à signaler, on continue d'attendre
            except self.voice_mod.VoiceNotUnderstood:
                continue  # bruit non reconnu pendant la veille : ignoré silencieusement
            except self.voice_mod.VoiceError as exc:
                print(f"Erreur : {exc}", file=sys.stderr)
                return 1
            except KeyboardInterrupt:
                print()
                return 0

            if not _contains_wake_word(phrase):
                continue

            if not self._activate():
                return 0
            # On retourne en veille : pas de "je t'écoute" tant que
            # "Éline" n'est pas redit.

    def _activate(self) -> bool:
        """Après le mot d'activation : accuse réception, écoute, agit,
        et continue d'écouter après chaque réponse, sans redire "Éline".

        Le premier tour attend normalement (silence/incompréhension ne
        renvoient pas en veille, avec un accusé parlé à chaque relance).
        Après une commande traitée, AELYN reste active et réécoute la
        suite en silence pendant `settings.wake_timeout_seconds` : un
        silence prolongé au-delà de ce délai renvoie en veille (il faudra
        redire "Éline"). Une bascule en conversation continue (cf.
        `_run_conversation`) revient ici directement dès qu'on en sort.

        Retourne `False` si l'utilisateur a demandé à quitter.
        """
        if not self._greeted:
            self._say(random.choice(GREETINGS))
            self._greeted = True
        else:
            self._say(random.choice(WAKE_ACK))

        first_turn = True
        while True:
            phrase = ""
            while not phrase:
                try:
                    # Spinner pendant l'écoute active (post-activation) :
                    # contrairement à la veille (`_run_voice`, silencieuse
                    # par choix), on est ici en plein échange, l'absence de
                    # tout signal serait indiscernable d'un blocage.
                    with Spinner("Je t'écoute…"):
                        if first_turn:
                            phrase = self.voice_mod.transcribe()
                        else:
                            # Toujours active après une réponse : on patiente
                            # en silence, pas de relance parlée à chaque essai
                            # (ce n'est plus une attente après activation).
                            phrase = self.voice_mod.transcribe(
                                timeout=settings.wake_timeout_seconds, quiet=True
                            )
                except self.voice_mod.VoiceTimeout as exc:
                    if first_turn:
                        self._report_voice_error(exc)
                        continue
                    # Silence prolongé après une réponse : retour en veille.
                    return True
                except self.voice_mod.VoiceNotUnderstood as exc:
                    self._report_voice_error(exc)
                except self.voice_mod.VoiceError as exc:
                    print(f"Erreur : {exc}", file=sys.stderr)
                    return True
                except KeyboardInterrupt:
                    print()
                    return False

            first_turn = False
            self._silence_streak = 0

            if CONVERSATION_TRIGGER_RE.search(_normalize(phrase)):
                if not self._run_conversation():
                    return False
                # "Éline" a mis fin à la conversation : on ré-accuse
                # réception et on continue d'écouter une commande, sans
                # repasser par la veille silencieuse.
                self._say(random.choice(WAKE_ACK))
                continue

            if not self._handle_phrase(phrase):
                return False
            # Reste active : on reboucle pour écouter la suite au lieu de
            # retourner en veille après une seule commande.

    def _run_conversation(self) -> bool:
        """Conversation continue : plus besoin de redire "Éline" entre les tours.

        Le dire à nouveau met fin à la conversation (l'appelant enchaîne
        alors sur une activation normale). Retourne `False` si
        l'utilisateur a demandé à quitter le programme.
        """
        self._say("D'accord, je t'écoute.")
        while True:
            try:
                with Spinner("Je t'écoute…"):
                    phrase = self.voice_mod.transcribe()
            except self.voice_mod.VoiceTimeout as exc:
                self._report_voice_error(exc)
                continue
            except self.voice_mod.VoiceNotUnderstood as exc:
                self._report_voice_error(exc)
                continue
            except self.voice_mod.VoiceError as exc:
                print(f"Erreur : {exc}", file=sys.stderr)
                return True
            except KeyboardInterrupt:
                print()
                return False

            self._silence_streak = 0

            if phrase.lower() in {"quitter", "exit", "quit"}:
                return False
            if _contains_wake_word(phrase):
                return True

            self._remember("user", phrase)
            self._converse(phrase)

    # ------------------------------------------------------------ phrase

    def _handle_phrase(self, phrase: str) -> bool:
        """Traite une phrase déjà transcrite/tapée. `False` signifie : quitter.

        Mince wrapper CLI autour de `_dispatch_phrase` (partagé avec
        `handle_message`, l'entrée API), seule la gestion du mot
        "quitter" (propre à une boucle interactive) reste ici."""
        if phrase.lower() in {"quitter", "exit", "quit"}:
            return False

        self._remember("user", phrase)
        self._dispatch_phrase(phrase, confirm=True)
        return True

    def handle_message(self, phrase: str) -> TurnResult:
        """Point d'entrée NON interactif (`POST /chat/message` côté
        aelyn-api) : MÊME routage que `_handle_phrase` (fast router, LLM
        `SYSTEM_INTENT`, résolution de référence, follow-ups "affiche
        les offres"...), `_dispatch_phrase` est le seul endroit qui
        décide quoi faire d'une phrase, CLI et API y passent tous deux.
        Seule la présentation diffère :

        - rien n'est imprimé sur un vrai terminal (stdout redirigé,
          `_print_agent_bubble`/`_say_stream` écrivent dedans sans
          effet visible, exactement comme `_run_command` capture déjà la
          sortie de `run_command`/`career_run_command` pour ses propres
          besoins) ;
        - rien n'est synthétisé à voix haute (l'agent utilisé par l'API
          est construit avec `voice=False`, cf. `aelyn_api.deps`) ;
        - AUCUNE commande qui modifie un état (valider/rejeter) ne
          s'exécute : elle nécessiterait une confirmation interactive
          qui n'a pas de sens pour un appel HTTP sans terminal en face
          (cf. `confirm=False` plus bas) : le texte renvoyé l'explique
          plutôt que de bloquer sur une entrée clavier qui ne viendra
          jamais.

        Retourne un `TurnResult` : `text` (toujours), et `result_type`/
        `results` quand la réponse de CE tour est une LISTE structurée
        (offres/mails) plutôt qu'une simple phrase.
        """
        self._turn_result_type = None
        self._turn_result_payload = None
        with contextlib.redirect_stdout(io.StringIO()):
            self._remember("user", phrase)
            self._dispatch_phrase(phrase, confirm=False)
        return TurnResult(
            text=self._last_said,
            result_type=self._turn_result_type,
            results=self._turn_result_payload,
        )

    def handle_message_stream(self, phrase: str):
        """Variante EN FLUX de `handle_message`, pour `POST
        /chat/message/stream` (SSE) : bug réel remonté en usage, une
        réponse lente (rechargement de modèle Ollama forcé par la
        contention VRAM qwen3:4b/mistral:7b sur ce GPU 6 Go, PLUS le temps
        de génération lui-même) pouvait dépasser le timeout du client
        avant que `handle_message` (bloquant, qui attend la réponse
        COMPLÈTE) ne renvoie quoi que ce soit. Deux bénéfices en un :
        la connexion reste active et produit du texte au lieu d'être
        bloquée (plus aucun risque de timeout, peu importe la durée
        réelle), et AELYN paraît répondre immédiatement au lieu de
        "geler" (plainte utilisateur réelle, "fluide comme JARVIS").

        MÊME routage que `handle_message`/`_handle_phrase` : ce générateur
        ne contient AUCUNE logique de décision propre, seulement de la
        plomberie pour exposer au fil de l'eau ce que `_dispatch_phrase`
        produit déjà (`_say`/`_say_stream`/`_ack_processing`, cf.
        `_stream_sink` ci-dessus). `_dispatch_phrase` s'exécute dans un
        thread à part (il bloque sur le LLM/IMAP/France Travail) pendant
        que ce générateur relit la file au fil de l'eau dans le thread
        appelant.

        Générateur : produit des `str` (fragments de texte, dans l'ordre
        d'émission, à concaténer côté appelant pour obtenir le texte
        affiché au fur et à mesure), parfois une `_Heartbeat` (aucun
        contenu réel depuis `_HEARTBEAT_INTERVAL_SECONDS`, à ignorer/
        traduire en simple battement, cf. `_Heartbeat`), puis EN TOUT
        DERNIER un seul `TurnResult` (texte complet + `result_type`/
        `results`, identiques à ce que renverrait `handle_message` pour la
        même phrase). Ce dernier élément n'a pas besoin d'arriver au fil
        de l'eau : une liste d'offres/mails est déjà connue d'un coup à la
        fin du routage, seul le texte libre profite réellement du flux ;
        il sert aussi de source de vérité pour le texte complet, au cas où
        l'appelant préfère s'y fier plutôt qu'à sa propre concaténation.

        Lève `RuntimeError` si un tour en flux est déjà en cours sur CETTE
        instance : AELYN est un assistant mono-utilisateur sans isolement
        par session (cf. `aelyn_api.deps.get_conversational_agent`, une
        seule instance pour tout le process API) ; deux flux concurrents
        mélangeraient leurs fragments respectifs dans la même file.
        """
        if self._stream_sink is not None:
            raise RuntimeError(
                "Un autre message est déjà en cours de traitement, réessaie dans un instant."
            )

        sink = _StreamSink()
        self._stream_sink = sink
        self._turn_result_type = None
        self._turn_result_payload = None
        # Capturée ici plutôt que simplement journalisée dans `_worker` :
        # `_dispatch_phrase` avale déjà ses erreurs ATTENDUES (LLMError,
        # IMAP...) en texte de réponse normal (même garantie que pour
        # `handle_message`) ; une exception qui s'échappe malgré tout est
        # un vrai bug, et doit remonter à l'appelant (le routeur API) au
        # lieu de finir le flux en silence comme si tout s'était bien
        # passé.
        worker_error: list[BaseException] = []

        def _worker() -> None:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    self._remember("user", phrase)
                    self._dispatch_phrase(phrase, confirm=False)
            except BaseException as exc:  # noqa: BLE001 - relevé ci-dessous
                worker_error.append(exc)
            finally:
                # Dans TOUS les cas (y compris une exception imprévue) :
                # sans ce `finally`, un bug dans `_dispatch_phrase` bloquerait
                # le générateur indéfiniment sur `sink.queue.get()` plutôt
                # que de remonter proprement.
                sink.close()

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        try:
            while True:
                try:
                    fragment = sink.queue.get(timeout=_HEARTBEAT_INTERVAL_SECONDS)
                except queue.Empty:
                    # Rien de réel depuis `_HEARTBEAT_INTERVAL_SECONDS` (ex.
                    # rechargement de modèle Ollama en cours) : un battement
                    # plutôt que de laisser la connexion totalement muette.
                    yield _HEARTBEAT
                    continue
                if fragment is None:
                    break
                yield fragment
            thread.join()
            if worker_error:
                raise worker_error[0]
            yield TurnResult(
                text=self._last_said,
                result_type=self._turn_result_type,
                results=self._turn_result_payload,
            )
        finally:
            self._stream_sink = None

    def _dispatch_phrase(self, phrase: str, *, confirm: bool) -> None:
        """Logique de routage PARTAGÉE entre `_handle_phrase` (CLI) et
        `handle_message` (API) : interception des tournures spéciales
        (lecture arrière, CV/LM, résumé...), puis routage LLM/fast-router
        vers une `Intent`, puis exécution (directe pour les commandes en
        lecture seule, confirmée sinon).

        `confirm` distingue le SEUL point qui ne peut pas être partagé
        tel quel : une commande qui modifie un état (valider/rejeter) ne
        peut être confirmée par un `input()` bloquant que depuis un vrai
        terminal (CLI, `confirm=True`), jamais depuis un appel HTTP sans
        session interactive (API, `confirm=False`), où on se contente
        d'expliquer que ce n'est pas encore possible par ce biais.
        """
        if self._pending_action is not None:
            if self._try_pending_confirmation(phrase):
                return
            # Ni confirmation ni refus reconnu dans CETTE phrase : on
            # abandonne silencieusement l'action en attente plutôt que de
            # la laisser traîner et se déclencher plus tard sur un tour
            # sans aucun rapport (ex. l'utilisateur a changé de sujet sans
            # répondre à "veux-tu que je..."), puis on laisse cette phrase
            # suivre son propre routage normal ci-dessous, EXACTEMENT comme
            # si rien n'était en attente.
            self._pending_action = None

        if self._try_greet(phrase):
            return
        if self._try_tell_time(phrase):
            return
        if self._try_read_back(phrase):
            return
        # AVANT `_try_draft` : "rédige une lettre de motivation" contient
        # "rédige" (le déclencheur de `_try_draft`, pensé pour un brouillon
        # de MAIL), sans cet ordre, cette phrase serait mal aiguillée.
        if self._try_prepare_cv(phrase):
            return
        # AVANT `_try_prepare_lm` : "affine cette lettre de motivation"
        # contient aussi "lettre de motivation" (le déclencheur de
        # `_try_prepare_lm`), sans cet ordre, une demande d'affinage
        # régénérerait une lettre neuve au lieu de partir de celle déjà
        # produite.
        if self._try_refine_lm(phrase):
            return
        if self._try_prepare_lm(phrase):
            return
        if self._try_summarize(phrase):
            return
        if self._try_draft(phrase):
            return
        if self._try_reformulate(phrase):
            return
        if self._try_describe_offer(phrase):
            return

        intent = fast_intent(phrase)
        if intent is None:
            try:
                intent = self.intent_llm.structured(schema=Intent, system=SYSTEM_INTENT, user=phrase)
            except LLMError as exc:
                print(f"Erreur : {exc}", file=sys.stderr)
                self._say("Je n'ai pas pu comprendre cette phrase (LLM indisponible).")
                return

        if intent.commande == "chercher_offres":
            # Filet de sécurité déterministe : constaté en direct, même
            # avec une consigne explicite dans SYSTEM_INTENT ET une
            # description portée par le champ lui-même, mistral:7b laissait
            # `limit` vide pour "cherche 20 offres de data scientist" —
            # Ollama n'utilise la description d'un champ JSON Schema que
            # pour la VALIDATION de structure, jamais comme texte lu par le
            # modèle. Un nombre explicite dans une phrase de recherche
            # d'offres n'a qu'une lecture possible (combien de résultats),
            # inutile de laisser ça à l'appréciation (variable) du LLM.
            match = _OFFERS_LIMIT_RE.search(_normalize(phrase))
            if match and intent.limit != int(match.group(1)):
                intent = intent.model_copy(update={"limit": int(match.group(1))})

        if intent.commande == "chercher_offres":
            match = _OFFERS_KEYWORDS_RE.search(phrase)
            if match:
                keywords = _TRAILING_CONTRACT_RE.sub("", match.group(1)).strip(" ?!.")
                if keywords and keywords != intent.mots_cles:
                    intent = intent.model_copy(update={"mots_cles": keywords})

        if intent.commande in {"valider", "rejeter"} and intent.action_id is None:
            self._say(intent.reformulation or "Il me manque un numéro d'action.")
            return

        if intent.commande == "inconnu":
            self._converse(phrase)
            return

        self._say(intent.reformulation)

        if intent.commande in READ_ONLY_COMMANDS:
            # Rien à confirmer : ces commandes ne changent jamais l'état
            # de la boîte mail (triage ne fait que proposer).
            self._run_command(intent)
            return

        if not confirm:
            # API/non-interactif : jamais de confirmation bloquante sur
            # une entrée clavier qui ne viendra jamais. Les actions qui
            # modifient un état restent réservées à une interaction
            # confirmée (CLI) ou à de futures routes dédiées côté API.
            self._say(
                f"« {intent.commande} » modifie quelque chose et doit être "
                "confirmé avant d'être exécuté. Pas encore possible depuis "
                "ce chat, utilise le CLI (`aelyn chat`) pour l'instant."
            )
            return

        voice_errors = (self.voice_mod.VoiceError,) if self.voice_mod else ()
        try:
            reponse = self._listen("Confirmer ? [o/N] ")
        except voice_errors as exc:
            self._report_voice_error(exc)
            return

        if not _is_yes(reponse):
            self._say(random.choice(ACK_CANCEL))
            return

        self._run_command(intent)

    def _try_pending_confirmation(self, phrase: str) -> bool:
        """Répond à CETTE phrase comme la suite d'un "veux-tu que je... ?"
        posé au tour précédent (cf. `_pending_action`, posé par
        `_try_draft`/`_try_prepare_cv`/`_try_prepare_lm`/`_try_refine_lm`).

        Reconnaissance VOLONTAIREMENT large (cf. `_CONFIRM_RE`/
        `_DECLINE_RE`) : un "oui"/"non" exact serait trop strict pour une
        réponse vocale naturelle ("vas-y", "d'accord", "laisse tomber"...).

        Retourne `True` si la phrase a été comprise comme une confirmation
        ou un refus (dans les deux cas, l'action en attente est consommée
        et le tour s'arrête là). Retourne `False` si la phrase ne ressemble
        ni à l'un ni à l'autre (ex. l'utilisateur a changé de sujet sans
        répondre) : l'appelant (`_dispatch_phrase`) abandonne alors
        l'action en attente et laisse cette phrase suivre son propre
        routage, plutôt que de l'exécuter plus tard sur un tour sans
        rapport ou de bloquer toute autre demande tant qu'on n'a pas
        explicitement répondu à la question.
        """
        normalized = _normalize(phrase).lower()

        if _DECLINE_RE.search(normalized):
            self._pending_action = None
            self._say(random.choice(ACK_CANCEL))
            return True

        if _CONFIRM_RE.search(normalized):
            action = self._pending_action
            self._pending_action = None
            kind = action["kind"]
            if kind == "draft_mail":
                self._run_draft(action["mail"])
            elif kind == "prepare_cv":
                self._run_prepare_cv(action["offre"])
            elif kind == "prepare_lm":
                self._run_prepare_lm(action["offre"])
            elif kind == "refine_lm":
                self._run_refine_lm()
            return True

        return False

    def _converse(self, phrase: str) -> None:
        """Conversation libre (pas une commande mail) : réponse naturelle, sans confirmation ni action.

        Seul cas où on appelle le LLM pour PARLER plutôt que pour classer,
        via `SYSTEM_PERSONA`, sans contrainte de schéma JSON. Garde un
        historique borné pour ne pas oublier le sujet d'un tour à l'autre.
        """
        try:
            # Diffusé (cf. `_say_stream`) plutôt qu'attendu d'un bloc :
            # c'est le chemin le plus emprunté de toute la conversation
            # (chaque phrase hors commande y passe), donc celui où la
            # latence perçue compte le plus.
            reponse = self._say_stream(
                self.llm.text_stream(
                    system=SYSTEM_PERSONA, user=phrase, history=self._conversation_history
                )
            )
        except LLMError as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            self._say("Le modèle local n'a pas pu répondre. Réessaie dans un instant.")
            return

        self._conversation_history.append({"role": "user", "content": phrase})
        self._conversation_history.append({"role": "assistant", "content": reponse})
        del self._conversation_history[:-_MAX_CONVERSATION_HISTORY]
        # (déjà affiché/parlé/mémorisé au fil de l'eau par `_say_stream` ci-dessus)

    # -------------------------------------------------- mail précis / reformulation

    @staticmethod
    def _best_keyword_match(keywords: list[str], haystacks: list[str]):
        """Retourne l'INDEX du haystack qui partage le PLUS de mots-clés
        (mots entiers, pas de sous-chaîne), pas juste le premier qui
        matche ne serait-ce qu'un seul mot-clé. Sans ce classement, un
        mot-clé court comme "en" matchait "sci-EN-tist" par sous-chaîne et
        faisait remonter la première offre venue, avant même d'atteindre
        celle qui matchait vraiment tous les mots-clés demandés (ex.
        "Collective.Work" retournait "U-Logistique" à cause de "en" dans
        "scientist"). Retourne `None` si aucun mot-clé ne matche."""
        if not keywords:
            return None
        best_index, best_score = None, 0
        for i, haystack in enumerate(haystacks):
            words = set(re.findall(r"\w+", haystack))
            score = sum(1 for kw in keywords if kw in words)
            if score > best_score:
                best_index, best_score = i, score
        if best_index is not None:
            return best_index
        # Repli : un nom de marque dit/tapé avec un espace ("France
        # Travail") redevient UN SEUL mot dans une adresse mail/un domaine
        # ("francetravail.io") : chaque mot-clé pris isolément ("france",
        # "travail") ne correspond alors jamais à un mot ENTIER du
        # haystack, même s'ils en forment un bout à bout (observé en
        # direct : "résume le mail de France Travail" échouait alors que
        # l'expéditeur réel était francetravail.io). On retente en collant
        # les mots-clés et en cherchant cette chaîne dans le haystack
        # brut. Seuil de 4 caractères pour éviter qu'un collage de
        # mots-clés très courts ("de"+"la") ne matche n'importe quoi.
        squashed = "".join(keywords)
        if len(squashed) >= 4:
            for i, haystack in enumerate(haystacks):
                if squashed in haystack.replace(" ", ""):
                    return i
        return None

    def _find_mail(self, phrase: str) -> Mail | None:
        """Retrouve UN mail parmi les derniers affichés : par position
        (« le premier », « le dernier », « le numéro 2 ») ou, sinon, par
        mot-clé (expéditeur/sujet) : la voix déforme souvent un nom
        d'entreprise, la position reste fiable dans ce cas."""
        if not self._last_mails:
            return None

        index = self._index_from_phrase(phrase, len(self._last_mails))
        if index is not None:
            self._mail_focus = self._last_mails[index]
            self._last_focus_kind = "mail"
            return self._mail_focus

        text = _normalize(phrase).lower()
        # `\w+` plutôt que `.split()` : une élision ("d'IBM", "l'offre")
        # colle sinon l'apostrophe au mot suivant dans un seul token, qui
        # ne matche alors plus jamais le nom recherché ("d'ibm" != "ibm").
        keywords = [w for w in re.findall(r"\w+", text) if len(w) >= 2 and w not in _REFERENCE_STOPWORDS]
        haystacks = [
            _normalize(f"{mail.sender} {mail.sender_email} {mail.subject}").lower()
            for mail in self._last_mails
        ]
        match = self._best_keyword_match(keywords, haystacks)
        if match is not None:
            self._mail_focus = self._last_mails[match]
            self._last_focus_kind = "mail"
            return self._mail_focus
        # Référence démonstrative ("ce mail") : soit aucun mot-clé n'a
        # survécu aux stopwords, soit un verbe de cadrage pas encore
        # recensé y survit mais ne matche rien de toute façon, dans les
        # deux cas la présence de "ce"/"cette" est un signal bien plus
        # fiable qu'un mot-clé isolé et non reconnu : on retombe sur le
        # dernier mail évoqué plutôt que d'échouer sur un verbe imprévu.
        if (not keywords or _is_demonstrative_reference(phrase)) and self._mail_focus in self._last_mails:
            self._last_focus_kind = "mail"
            return self._mail_focus
        return None

    def _find_offer(self, phrase: str) -> dict | None:
        """Retrouve UNE offre parmi les dernières affichées, par position
        ou par mot-clé (intitulé/entreprise), même principe que `_find_mail`."""
        if not self._last_offers:
            return None

        index = self._index_from_phrase(phrase, len(self._last_offers))
        if index is not None:
            self._offer_focus = self._last_offers[index]
            self._last_focus_kind = "offer"
            return self._offer_focus

        text = _normalize(phrase).lower()
        # `\w+` plutôt que `.split()` : une élision ("d'IBM", "l'offre")
        # colle sinon l'apostrophe au mot suivant dans un seul token, qui
        # ne matche alors plus jamais le nom recherché ("d'ibm" != "ibm").
        keywords = [w for w in re.findall(r"\w+", text) if len(w) >= 2 and w not in _REFERENCE_STOPWORDS]
        haystacks = [
            _normalize(f"{offre.get('intitule', '')} {offre.get('entreprise', {}).get('nom', '')}").lower()
            for offre in self._last_offers
        ]
        match = self._best_keyword_match(keywords, haystacks)
        if match is not None:
            self._offer_focus = self._last_offers[match]
            self._last_focus_kind = "offer"
            return self._offer_focus
        # Référence démonstrative ("cette offre") : soit aucun mot-clé n'a
        # survécu aux stopwords, soit un verbe de cadrage pas encore
        # recensé y survit ("prépare", "fais"... observé avec deux verbes
        # différents) mais ne matche aucune offre de toute façon, dans les
        # deux cas la présence de "ce"/"cette" est un signal bien plus
        # fiable qu'un mot-clé isolé et non reconnu : on retombe sur la
        # dernière offre évoquée plutôt que d'échouer sur un verbe
        # imprévu.
        if (not keywords or _is_demonstrative_reference(phrase)) and self._offer_focus in self._last_offers:
            self._last_focus_kind = "offer"
            return self._offer_focus
        return None

    def _try_describe_offer(self, phrase: str) -> bool:
        """« décris l'offre de EDF » : description complète à l'écrit.

        Une offre fait souvent plusieurs centaines de mots : la lire en
        entier à voix haute serait inutilisable en mode voix (constaté :
        l'utilisateur ne veut PAS entendre tout le texte). Même principe
        que le CV/la lettre de motivation : confirmation courte parlée,
        contenu complet affiché à l'écrit seulement. Pour un vrai résumé
        condensé (pas juste "affiché à l'écran"), voir `_try_summarize`
        ("résume cette offre")."""
        if not DESCRIBE_OFFER_RE.search(_normalize(phrase)):
            return False

        offre = self._find_offer(phrase)
        if offre is None:
            self._say(
                "Je ne sais pas de quelle offre tu parles. Cherche d'abord des offres."
            )
            return True

        description = offre.get("description", "").strip()
        if not description:
            self._say("Cette offre n'a pas de description.")
            return True

        # `_say()` (pas `_finish_say` seul) pour l'accroche COURTE, à
        # l'écrit ET à l'oral ; puis la description complète à l'écrit
        # seulement (bulle séparée) mais quand même mémorisée dans
        # `_last_said` via `_finish_say(description, spoken=...)` : sans
        # ce second appel, le texte réel renvoyé par `handle_message`
        # (API web) restait l'accroche COURTE, jamais la description —
        # un `_print_agent_bubble` seul n'est visible que dans un vrai
        # terminal (CLI), jamais via `POST /chat/message` (bug réel,
        # observé en direct : le frontend web n'affichait jamais aucune
        # description d'offre, seulement "Voici la description de X.").
        # `spoken` reprend l'accroche courte pour ne pas lire toute la
        # description à voix haute (déjà dite une fois, pas la peine de
        # la répéter dans l'accusé vocal).
        intro = f"Voici la description de {offre.get('intitule') or 'cette offre'}."
        _print_agent_bubble(intro)
        _print_agent_bubble(description)
        question = self._offer_pending_cv(offre)
        full_text = f"{description}\n\n{question}" if question else description
        self._finish_say(full_text, spoken=intro)
        return True

    def _offer_pending_cv(self, offre: dict) -> str:
        """Après avoir décrit/résumé une offre, propose spontanément de
        préparer le CV correspondant plutôt que d'attendre une demande
        explicite (comportement proactif demandé) : même mécanique que
        `_try_prepare_cv` (`_pending_action`), un simple "oui" au tour
        suivant suffit.

        Retourne la question SANS l'enregistrer elle-même (ni `_say` ni
        `_finish_say` ici) : l'appelant la combine avec son propre
        contenu (description/résumé) dans UN SEUL `_finish_say` final.
        `handle_message`/`TurnResult.text` (API web) ne porte qu'UN
        texte par tour (`_last_said`) ; appeler `_say` ici écraserait le
        contenu principal déjà produit par l'appelant, qui ne serait
        alors plus jamais visible côté web (bug réel corrigé avec celui-ci :
        appeler cette méthode via `self._say(...)` faisait disparaître la
        description/le résumé de la réponse API, ne laissant que cette
        question). Chaîne vide si une action est déjà en attente (ne
        devrait pas arriver ici, mais protège un futur appel ajouté par
        erreur après une confirmation déjà posée)."""
        if self._pending_action is not None:
            return ""
        self._pending_action = {"kind": "prepare_cv", "offre": offre}
        question = f"Veux-tu que je prépare ton CV pour {offre.get('intitule') or 'cette offre'} ?"
        _print_agent_bubble(question)
        return question

    def _try_prepare_cv(self, phrase: str) -> bool:
        """« prépare-moi un CV pour cette offre » : CV adapté et priorisé
        pour CETTE offre (pas un CV générique), via `ApplicationWriter`.

        N'EXÉCUTE RIEN directement : pose une confirmation ("veux-tu que
        je...") et mémorise l'offre dans `_pending_action` (cf.
        `_try_pending_confirmation`, qui appelle `_run_prepare_cv` sur
        confirmation du tour suivant). Génération LLM potentiellement
        longue (dizaines de secondes à quelques minutes) qui produit du
        contenu représentant l'utilisateur : une confirmation proactive
        avant de la lancer, plutôt qu'une exécution immédiate ou un échec
        sec sur une offre ambiguë (demande utilisateur réelle)."""
        if not PREPARE_CV_RE.search(_normalize(phrase)):
            return False

        offre = self._find_offer(phrase)
        if offre is None:
            self._say(
                "Je ne sais pas de quelle offre tu parles. Cherche d'abord des offres."
            )
            return True

        self._pending_action = {"kind": "prepare_cv", "offre": offre}
        self._say(f"Veux-tu que je prépare ton CV pour {offre.get('intitule') or 'cette offre'} ?")
        return True

    def _run_prepare_cv(self, offre: dict) -> None:
        self._ack_processing()
        try:
            cv = self._run_long_task(self.application_writer.draft_cv, offer_text(offre))
        except LLMError as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            self._say(
                "Je n'ai pas pu préparer le CV : le modèle local s'est arrêté. "
                "Réessaie."
            )
            return

        # Un CV complet est illisible à l'oral (structure, pas prose) :
        # confirmation courte parlée, contenu détaillé à l'écrit seulement.
        # `_finish_say(cv_text, spoken=intro)` (pas `_say` seul) : le CV
        # complet doit être dans `_last_said` pour que l'API web le
        # renvoie réellement (bug réel corrigé avec celui-ci : un
        # `_print_agent_bubble` isolé n'est visible qu'en CLI, jamais via
        # `POST /chat/message`, le frontend web n'affichait donc JAMAIS
        # le CV généré, seulement "Voici ton CV pour X.")."""
        intro = f"Voici ton CV pour {offre.get('intitule') or 'cette offre'}."
        cv_text = format_cv_text(cv)
        _print_agent_bubble(intro)
        _print_agent_bubble(cv_text)
        self._finish_say(cv_text, spoken=intro)

    def _try_prepare_lm(self, phrase: str) -> bool:
        """« prépare ma candidature / lettre de motivation pour cette offre ».

        Même principe que `_try_prepare_cv` : pose une confirmation au lieu
        de générer directement (cf. `_pending_action`/`_run_prepare_lm`)."""
        if not PREPARE_LM_RE.search(_normalize(phrase)):
            return False

        offre = self._find_offer(phrase)
        if offre is None:
            self._say(
                "Je ne sais pas de quelle offre tu parles. Cherche d'abord des offres."
            )
            return True

        self._pending_action = {"kind": "prepare_lm", "offre": offre}
        self._say(
            "Veux-tu que je prépare une lettre de motivation pour "
            f"{offre.get('intitule') or 'cette offre'} ?"
        )
        return True

    def _run_prepare_lm(self, offre: dict) -> None:
        self._ack_processing()
        # L'en-tête (nom, téléphone, email...) ne se lit pas à voix haute :
        # affiché à l'écrit AVANT de lancer la génération (immédiat), le
        # corps de la lettre arrive ensuite au fil de l'eau (cf.
        # `_say_stream`) : c'est le call le plus lent d'AELYN (LLM lourd,
        # gros contexte), donc celui où le streaming compte le plus.
        header = self.application_writer.contact_header()
        if header:
            _print_agent_bubble(header)
        try:
            corps = self._say_stream(
                self.application_writer.draft_cover_letter_stream(offer_text(offre))
            )
        except LLMError as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            self._say(
                "Je n'ai pas pu générer la lettre : le modèle local s'est arrêté. "
                "Réessaie."
            )
            return

        # Gardé pour « affine cette lettre de motivation » (`_try_refine_lm`).
        full_text = f"{header}\n\n{corps}" if header else corps
        self._last_lm = full_text
        self._last_lm_offer = offre
        # `_say_stream` a déjà mémorisé `corps` SEUL dans `_last_said`
        # (son `_finish_say` interne, avant que l'en-tête ne soit connu
        # du côté API) : sans cette ligne, l'en-tête (nom/téléphone/
        # email/ville) n'apparaissait jamais dans la réponse `POST
        # /chat/message`, uniquement dans la bulle CLI ci-dessus.
        if header:
            self._last_said = full_text

    def _try_refine_lm(self, phrase: str) -> bool:
        """« affine/améliore cette lettre de motivation » : reprend la
        DERNIÈRE lettre générée et demande au LLM de l'améliorer, plutôt
        que d'en repartir de zéro comme le ferait `_try_prepare_lm`.

        Même principe de confirmation proactive que `_try_prepare_cv`/
        `_try_prepare_lm` (cf. `_pending_action`/`_run_refine_lm`)."""
        normalized = _normalize(phrase)
        if not REFINE_LM_RE.search(normalized) or "lettre" not in normalized.lower():
            return False

        if self._last_lm is None or self._last_lm_offer is None:
            self._say(
                "Je n'ai pas encore de lettre de motivation à affiner. "
                "Fais d'abord en générer une."
            )
            return True

        self._pending_action = {"kind": "refine_lm"}
        self._say("Veux-tu que j'affine cette lettre de motivation ?")
        return True

    def _run_refine_lm(self) -> None:
        # `_last_lm`/`_last_lm_offer` ont pu changer entre la question et
        # la confirmation (ex. une nouvelle lettre générée entre-temps) :
        # on relit l'état COURANT plutôt que de figer une copie dans
        # `_pending_action`, le comportement attendu reste "affine la
        # DERNIÈRE lettre", quelle qu'elle soit au moment de confirmer.
        if self._last_lm is None or self._last_lm_offer is None:
            self._say(
                "Je n'ai plus de lettre de motivation à affiner. "
                "Fais d'abord en générer une."
            )
            return

        self._ack_processing()
        header = self.application_writer.contact_header()
        if header:
            _print_agent_bubble(header)
        try:
            corps = self._say_stream(
                self.application_writer.refine_cover_letter_stream(
                    self._last_lm, offer_text(self._last_lm_offer)
                )
            )
        except LLMError as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            self._say(
                "Je n'ai pas pu affiner la lettre : le modèle local s'est arrêté. "
                "Réessaie."
            )
            return

        # Même correctif que `_run_prepare_lm` : sans réaffecter
        # `_last_said`, l'en-tête n'apparaissait jamais dans la réponse
        # `POST /chat/message`.
        full_text = f"{header}\n\n{corps}" if header else corps
        self._last_lm = full_text
        if header:
            self._last_said = full_text

    def _try_summarize(self, phrase: str) -> bool:
        """« résume le mail de Conforama » / « résume cette offre » : résumé
        du CONTENU visé, pas du journal. Seule action ambiguë entre mail et
        offre ("résume ça" peut viser l'un ou l'autre), on essaie d'abord
        le type le plus récemment évoqué (`_last_focus_kind`), sinon
        l'autre, plutôt que de ne jamais considérer l'offre (bug réel :
        "résume cette offre" juste après avoir décrit une offre répondait
        "je ne sais pas de quel MAIL tu parles", car seul `_find_mail`
        était essayé).

        Le mot explicite "mail"/"offre" dans LA PHRASE prime sur
        `_last_focus_kind` : bug réel observé en direct, "résume LE MAIL
        de France Travail" juste après avoir manipulé une offre
        choisissait quand même `_find_offer` en premier (focus "offer"),
        qui matchait par erreur une offre sans rapport (mots-clés
        "france"/"travail" trouvés ailleurs) au lieu du mail demandé,
        explicitement nommé par l'utilisateur."""
        if not SUMMARIZE_RE.search(_normalize(phrase)):
            return False

        normalized_phrase = _normalize(phrase).lower()
        mentions_mail = bool(re.search(r"\bmails?\b|\bemails?\b", normalized_phrase))
        mentions_offer = bool(re.search(r"\boffres?\b", normalized_phrase))

        lookups = [("mail", self._find_mail), ("offer", self._find_offer)]
        if mentions_offer and not mentions_mail:
            lookups.reverse()
        elif not mentions_mail and not mentions_offer and self._last_focus_kind == "offer":
            lookups.reverse()

        for kind, find in lookups:
            target = find(phrase)
            if target is None:
                continue
            user_text = target.for_llm() if kind == "mail" else offer_text(target)
            self._ack_processing()
            try:
                summary = self._say_stream(self.llm.text_stream(system=SYSTEM_SUMMARY, user=user_text))
            except LLMError as exc:
                print(f"Erreur : {exc}", file=sys.stderr)
                self._say(
                    "Je n'ai pas pu faire le résumé : le modèle local s'est arrêté. "
                    "Réessaie."
                )
                return True
            if kind == "offer":
                # `_say_stream` a déjà mémorisé `summary` seul (son propre
                # `_finish_say` interne) : un second `_finish_say` ici,
                # avec le résumé ET la question combinés, laisse une
                # entrée d'historique un peu redondante (compromis
                # accepté), mais c'est la seule façon pour que
                # `TurnResult.text` (API web) porte la question en plus
                # du résumé plutôt que l'un OU l'autre.
                question = self._offer_pending_cv(target)
                if question:
                    self._finish_say(f"{summary}\n\n{question}")
            return True

        self._say(
            "Je ne sais pas de quoi tu parles. Fais d'abord vérifier tes "
            "mails ou chercher des offres."
        )
        return True

    def _try_draft(self, phrase: str) -> bool:
        """« fais un brouillon pour le mail de Conforama »/« prépare un
        mail pour Conforama »/« réponds à ce mail » : rédaction, hors
        flux `triage` (cf. `DRAFT_RE` pour la liste des formulations
        acceptées).

        Même principe de confirmation proactive que `_try_prepare_cv`/
        `_try_prepare_lm` : pose "veux-tu que je réponde au mail de X ?"
        au lieu de rédiger directement (cf. `_pending_action`/
        `_run_draft`) : un brouillon reste un texte qui engage
        l'utilisateur (même non envoyé), mieux vaut confirmer avant de
        lancer l'appel LLM que de surprendre avec un texte tout prêt."""
        if not DRAFT_RE.search(_normalize(phrase)):
            return False

        mail = self._find_mail(phrase)
        if mail is None:
            self._say(
                "Je ne sais pas de quel mail tu parles. Fais d'abord vérifier ou trier tes mails."
            )
            return True

        self._pending_action = {"kind": "draft_mail", "mail": mail}
        self._say(f"Veux-tu que je réponde au mail de {mail.sender} ?")
        return True

    def _run_draft(self, mail: Mail) -> None:
        self._ack_processing()
        try:
            self._say_stream(
                self.llm.text_stream(
                    system=SYSTEM_DRAFT.format(user_name=settings.user_name),
                    user=mail.for_llm(),
                )
            )
        except LLMError as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            self._say(
                "Je n'ai pas pu rédiger le brouillon : le modèle local s'est arrêté. "
                "Réessaie."
            )

    def _try_reformulate(self, phrase: str) -> bool:
        """« reformule ça » : redit la DERNIÈRE chose dite par AELYN, autrement."""
        if not REFORMULATE_RE.search(_normalize(phrase)):
            return False

        if not self._last_said:
            self._say("Je n'ai encore rien dit à reformuler.")
            return True

        self._ack_processing()
        try:
            self._say_stream(
                self.llm.text_stream(system=SYSTEM_REFORMULATE, user=self._last_said)
            )
        except LLMError as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            self._say(
                "Je n'ai pas pu reformuler : le modèle local s'est arrêté. Réessaie."
            )
            return True
        return True

    def _try_greet(self, phrase: str) -> bool:
        """« bonjour »/« salut », SEUL : un simple salut, jamais le LLM
        (cf. `GREETING_RE`)."""
        if not GREETING_RE.match(_normalize(phrase).lower()):
            return False
        self._say(random.choice(GREETING_REPLIES))
        return True

    def _try_tell_time(self, phrase: str) -> bool:
        """« quelle heure est-il »/« on est le combien » : horloge système
        directement, jamais le LLM (cf. `TIME_RE`/`DATE_RE`)."""
        normalized = _normalize(phrase)
        now = datetime.now()
        if TIME_RE.search(normalized):
            self._say(f"Il est {now.strftime('%Hh%M')}.")
            return True
        if DATE_RE.search(normalized):
            self._say(f"Nous sommes le {_JOURS_FR[now.weekday()]} {now.day} {_MOIS_FR[now.month - 1]}.")
            return True
        return False

    # ------------------------------------------------------- lecture arrière

    def _try_read_back(self, phrase: str) -> bool:
        """« lis le premier »/« lis le résultat 3 »/« lis le mail de LinkedIn »
        /« affiche les offres »/« montre tous les mails ».

        Relit un résultat déjà affiché par `verifier`/`triage`/
        `chercher_offres`, sans rien relancer. Retourne `False` si la
        phrase n'est pas une demande de lecture (l'appelant continue son
        propre routage).
        """
        if not READ_BACK_RE.search(phrase):
            return False

        normalized = _normalize(phrase).lower()
        if "camera" in normalized or "webcam" in normalized:
            # "montre la caméra de l'entrée" : une commande caméra, pas
            # une relecture, même si "montre" matche READ_BACK_RE, laisse
            # la phrase continuer vers son propre routage (fast_router.py
            # /SYSTEM_INTENT) plutôt que de l'intercepter ici.
            return False

        if self._last_results and _SHOW_ALL_RE.search(normalized):
            # La LISTE ENTIÈRE ("les"/"tous"/"toutes"), pas un item précis,
            # cf. `_SHOW_ALL_RE`. AVANT `_resolve_reference` : celle-ci
            # est pensée pour UN seul élément et ne matcherait jamais rien
            # sur "affiche les offres" (aucun mot-clé propre à une offre
            # précise), tombant sinon sur `_last_said` (juste "6 offres
            # trouvées", pas la liste elle-même) : le bug concret rapporté.
            self._turn_result_type = self._last_list_type
            self._turn_result_payload = self._last_list_payload
            self._say("\n".join(self._last_results))
            return True

        item = self._resolve_reference(phrase) if self._last_results else None
        if item is not None:
            self._say(item)
        elif self._last_said:
            # Rien dans les résultats mail/offres (ex. "lis l'histoire à
            # haute voix" après une conversation libre) : on relit plutôt
            # la dernière chose dite, plus utile qu'un échec sec.
            self._say(self._last_said)
        else:
            self._say("Je n'ai rien à te relire pour l'instant.")
        return True

    @staticmethod
    def _index_from_phrase(phrase: str, count: int) -> int | None:
        """« le premier »/« le dernier »/« le numéro 3 » -> un index dans
        une liste de `count` éléments, ou `None` si la phrase n'en
        contient pas (l'appelant retombe alors sur une recherche par
        mot-clé)."""
        if count == 0:
            return None

        text = _normalize(phrase).lower()

        for word, index in _INDEX_WORDS.items():
            if word in text:
                resolved = index if index >= 0 else count + index
                # "la quatrième" alors qu'il n'y a que 3 résultats : mieux
                # vaut retomber sur la recherche par mot-clé qu'un crash
                # (`IndexError` sur `self._last_offers[index]` chez l'appelant).
                return resolved if 0 <= resolved < count else None

        match = re.search(r"\b(?:numero|resultat|le)\s+(\d+)\b", text)
        if match:
            index = int(match.group(1)) - 1
            return index if 0 <= index < count else None

        return None

    def _resolve_reference(self, phrase: str) -> str | None:
        index = self._index_from_phrase(phrase, len(self._last_results))
        if index is not None:
            return self._last_results[index]

        # Recherche par mot-clé (ex. "lis le mail de linkedin") : on ne
        # garde que les mots un peu significatifs pour éviter qu'un "le"
        # ou un "de" ne matche n'importe quelle ligne.
        text = _normalize(phrase).lower()
        # `\w+` plutôt que `.split()` : une élision ("d'IBM", "l'offre")
        # colle sinon l'apostrophe au mot suivant dans un seul token, qui
        # ne matche alors plus jamais le nom recherché ("d'ibm" != "ibm").
        keywords = [w for w in re.findall(r"\w+", text) if len(w) >= 2 and w not in _REFERENCE_STOPWORDS]
        for item in self._last_results:
            item_norm = _normalize(item).lower()
            if any(kw in item_norm for kw in keywords):
                return item
        return None

    def _run_command(self, intent: Intent) -> None:
        # Accusé de réception pour les commandes lentes (LLM/API) : imprimé
        # dans TOUS les cas (texte comme voix, l'utilisateur doit voir
        # qu'une tâche tourne, pas juste l'entendre), et en plus parlé en
        # mode voix SANS attendre que ce soit fini de dire avant de lancer
        # l'action, sinon le TTS ajoute sa propre latence devant celle du
        # triage/LLM/IMAP qui suit.
        if intent.commande in {"triage", "rapport", "chercher_offres", "media", "camera"}:
            self._ack_processing()

        buffer = io.StringIO()
        mails: list[Mail] = []
        offres: list[dict] = []
        triage_info: list[dict] | None = None
        with contextlib.redirect_stdout(buffer):
            if intent.commande in MEDIA_COMMANDS:
                if intent.media_action is None:
                    print("Je ne sais pas quelle action TV effectuer.")
                    code = 1
                else:
                    if self.media_controller is None:
                        self.media_controller = MediaController()
                    try:
                        code = self.media_controller.dispatch(
                            intent.media_action, intent.media_query, intent.media_amount
                        )
                    except Exception as exc:
                        # La TV peut être éteinte/injoignable à tout moment
                        # (veille, coupure réseau) : jamais une raison de
                        # planter toute la session de chat pour autant.
                        print(f"La télé semble injoignable : {exc}")
                        code = 1
            elif intent.commande in CAMERA_COMMANDS:
                if intent.camera_name is None:
                    print("Je ne sais pas quelle caméra afficher.")
                    code = 1
                else:
                    try:
                        code = show_camera(intent.camera_name)
                    except Exception as exc:
                        # Une webcam peut être absente/déjà utilisée par une
                        # autre appli à tout moment : jamais une raison de
                        # planter toute la session de chat pour autant (même
                        # principe que la TV injoignable ci-dessus).
                        print(f"La caméra semble inaccessible : {exc}")
                        code = 1
            elif intent.commande in CAREER_COMMANDS:
                try:
                    code, offres = career_run_command(
                        intent.commande,
                        offers_agent=self.offers_agent,
                        mots_cles=intent.mots_cles,
                        contract_type=intent.contract_type,
                        limit=intent.limit,
                    )
                except Exception:
                    logger.exception("Recherche d'offres échouée")
                    print(
                        "La recherche d'offres a échoué : le service d'emploi ou "
                        "le modèle local est indisponible. Réessaie dans un instant."
                    )
                    code, offres = 1, []
            else:
                kwargs = dict(
                    limit=intent.limit,
                    action_id=intent.action_id,
                    hours=intent.hours or 24,
                    agent=self.email_agent,
                    # Tableau Rich réservé à la CLI directe : ses bordures
                    # casseraient `_group_result_lines` ci-dessous.
                    plain=True,
                )
                code, mails, triage_info = run_command(intent.commande, **kwargs)
        output = buffer.getvalue()
        if output.strip():
            _print_agent_bubble(output.rstrip("\n"))

        if intent.commande in {"verifier", "triage"}:
            # `triage_info` (uid -> action_proposee/urgence/resume/action_id)
            # vient de `run_command` UNIQUEMENT pour `triage` : sans ce
            # merge, le tableau "mails" rendu côté frontend était identique
            # pour verifier ET triage, l'action proposée par le LLM
            # n'existant alors que dans le texte imprimé, jamais dans les
            # données structurées (`TurnResult.results`).
            triage_by_uid = {t["uid"]: t for t in triage_info} if triage_info else {}
            mail_dicts = [_mail_to_dict(m, triage_by_uid.get(m.uid)) for m in mails]
            self._last_results = _group_result_lines(output)
            self._last_mails = mails
            self._last_list_type = "mails"
            self._last_list_payload = mail_dicts
            self._turn_result_type = "mails"
            self._turn_result_payload = mail_dicts
        if intent.commande == "chercher_offres":
            # `_last_results` (lignes texte) manquait pour les offres avant
            # ce correctif : "affiche les offres" (ou "lis la première
            # offre") n'avait alors RIEN à relire et retombait sur
            # `_last_said` (juste "X offres trouvées", pas la liste),
            # cf. `_try_read_back`/`_SHOW_ALL_RE`.
            self._last_offers = offres
            self._last_results = [_offer_line(o) for o in offres]
            self._last_list_type = "offers"
            self._last_list_payload = offres
            self._turn_result_type = "offers"
            self._turn_result_payload = offres

        # Texte "complet" pour la mémoire longue/l'API (`_last_said`,
        # `/chat/history`, `TurnResult.text`) : TOUJOURS la sortie réelle de
        # la commande quand il y en a une (jamais juste la reformulation
        # courte déjà dite avant `_run_command`), pour qu'un appelant texte
        # (API, chat web) obtienne une réponse utile plutôt qu'un accusé
        # vague. Distinct de ce qui est effectivement PARLÉ (`spoken`
        # ci-dessous) : une liste de mails/offres reste écran+API
        # seulement, jamais lue intégralement à voix haute.
        if intent.commande == "rapport":
            full_text = output.replace("Un instant, je m'en charge…", "").strip()
            self._finish_say(full_text)
        else:
            full_text = output.strip() or (
                random.choice(ACK_DONE) if code == 0 else random.choice(ACK_ERROR)
            )
            short_ack = random.choice(ACK_DONE) if code == 0 else random.choice(ACK_ERROR)
            self._finish_say(full_text, spoken=short_ack)


def _mail_to_dict(mail: Mail, triage: dict | None = None) -> dict:
    """Même forme que `MailOut` côté aelyn-api (cf.
    aelyn-api/src/aelyn_api/routers/email.py), pour qu'un résultat
    "mails" renvoyé par `handle_message()` se comporte, côté frontend,
    comme celui de `GET /email` : un seul contrat JSON pour "une liste
    de mails", peu importe par quelle route elle est arrivée.

    `triage` (uniquement pour une commande `triage`, cf. appelant) ajoute
    `action_proposee`/`urgence`/`resume`/`action_id` : ce que le LLM a
    proposé pour CE mail, pour que le frontend puisse l'afficher dans le
    tableau au lieu de ne l'avoir que dans le texte libre de la réponse."""
    lignes = [line.strip() for line in mail.body.splitlines() if line.strip()]
    preview = " ".join(lignes)[:160]
    result = {
        "uid": mail.uid,
        "sender": mail.sender,
        "sender_email": mail.sender_email,
        "subject": mail.subject,
        "date": mail.date.isoformat() if mail.date else None,
        "preview": preview,
        "has_attachments": mail.has_attachments,
    }
    if triage is not None:
        result["action_proposee"] = triage["action_proposee"]
        result["urgence"] = triage["urgence"]
        result["resume"] = triage["resume"]
        result["action_id"] = triage["action_id"]
    return result


def _offer_line(offre: dict) -> str:
    """Une ligne lisible pour UNE offre, même format que
    `aelyn_career.agent.run_command`, pour que `_last_results` (relu par
    `_try_read_back`) ressemble à ce qui a été affiché au moment de la
    recherche."""
    entreprise = offre.get("entreprise", {}).get("nom", "?")
    lieu = offre.get("lieuTravail", {}).get("libelle", "?")
    contrat = offre.get("typeContrat", "?")
    return f"- {offre.get('intitule')} | {entreprise} | {lieu} | {contrat}"


def _group_result_lines(output: str) -> list[str]:
    """Regroupe la sortie de `verifier`/`triage` en une chaîne par mail.

    `triage` imprime deux lignes par mail (l'action, puis le résumé
    indenté) ; `verifier` une seule. Les deux formats redeviennent une
    entrée par mail, adressable par `_resolve_reference`.
    """
    entries: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("Un instant", "Aucun")):
            continue
        if line.startswith("#") or line.startswith("["):
            entries.append(line)
        elif entries:
            entries[-1] += " ; " + line
    return entries

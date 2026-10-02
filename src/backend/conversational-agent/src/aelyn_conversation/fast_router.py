"""Court-circuite le LLM pour les phrases sans ambiguïté.

Le principal gain de latence en mode vocal, où chaque aller-retour au
modèle coûte plusieurs secondes : "valide la 3" ou "vérifie mes mails"
n'ont besoin d'aucune interprétation, une regex suffit. Le LLM ne sert
plus qu'aux phrases qui ne matchent aucun de ces patterns.
"""

from __future__ import annotations

import re
import unicodedata

from aelyn_conversation.models import Intent

_FAST_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(v[ée]rifie|regarde)\b.*\bmails?\b"), "verifier"),
    (re.compile(r"\bquoi de neuf\b|\bnouveaux? mails?\b"), "verifier"),
    (re.compile(r"\b(tri|trie|analyse)\b.*\bmails?\b"), "triage"),
    (re.compile(r"\brapport\b|\bta journ[ée]e\b|\bqu'est-ce que tu as fait\b"), "rapport"),
]
# Pas de raccourci rapide pour "chercher_offres" : contrairement aux autres
# commandes, la phrase peut contenir des mots-clés ou un type de contrat à
# extraire (ex. "des offres chez EDF", "cherche des stages") : ça passe
# toujours par le LLM pour ne pas perdre cette nuance.
_FAST_ID_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bvalide(?:r)?\s+(?:la\s+|le\s+)?(\d+)\b"), "valider"),
    (re.compile(r"\brejet(?:te|er)\s+(?:la\s+|le\s+)?(\d+)\b"), "rejeter"),
]

# Accents retirés dans les patterns eux-mêmes (comparés à du texte déjà
# normalisé par `_strip_accents`), "televison"/"chaine" au lieu de
# "télévision"/"chaîne".
_MEDIA_FAST_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bnetflix\b"), "netflix"),
    (re.compile(r"\byoutube\b"), "youtube"),
    (re.compile(r"\ballume\b.*\b(tele|television|tv)\b"), "tv_power"),
    (re.compile(r"\b(accueil|home)\b"), "home"),
    (re.compile(r"\b(retour|arriere)\b"), "back"),
    (re.compile(r"\bpause\b|\breprends?\b|\blecture\b"), "play_pause"),
    (re.compile(r"\bsuivante?\b"), "next"),
    (re.compile(r"\bprecedente?\b"), "previous"),
    (re.compile(r"\b(monte|augmente)\b.*\b(son|volume)\b"), "volume_up"),
    (re.compile(r"\b(baisse|diminue)\b.*\b(son|volume)\b"), "volume_down"),
    (re.compile(r"\bmuet\b|\bcoupe\s+le\s+son\b"), "mute"),
]
# Syntaxe propre uniquement : toute phrase plus ambiguë (STT déformée,
# "sur" manquant...) part au LLM, qui sait désormais gérer ces cas
# (cf. SYSTEM_INTENT) mais coûte plusieurs secondes de plus.
_MEDIA_SEARCH_RE = re.compile(r"^cherche\s+(.+?)\s+sur\s+(youtube|netflix)$")

# "montre la caméra de l'entrée/du salon", "montre toute la pièce" :
# "salon" couvre aussi "la pièce" en général (une seule caméra filme
# tout le salon, cf. camera.py), d'où le pattern "piece" séparé, sans
# exiger le mot "salon" pour autant.
_CAMERA_FAST_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(camera|webcam)\b.*\bentree\b"), "entree"),
    (re.compile(r"\bentree\b.*\b(camera|webcam)\b"), "entree"),
    (re.compile(r"\b(camera|webcam)\b.*\bsalon\b"), "salon"),
    (re.compile(r"\bsalon\b.*\b(camera|webcam)\b"), "salon"),
    (re.compile(r"\btoute\s+la\s+piece\b"), "salon"),
]

_FAST_REFORMULATIONS = {
    "verifier": "Je vérifie tes mails.",
    "triage": "Je lance le triage.",
    "rapport": "Je te fais un rapport.",
    "chercher_offres": "Je cherche des offres.",
    "valider": "Je valide la proposition {id}.",
    "rejeter": "Je rejette la proposition {id}.",
    "netflix": "Je lance Netflix.",
    "tv_power": "J'allume la télé.",
    "youtube": "Je lance YouTube.",
    "home": "Je reviens à l'accueil.",
    "back": "Je reviens en arrière.",
    "play_pause": "Je mets en pause.",
    "next": "Je passe à la suite.",
    "previous": "Je reviens en arrière.",
    "volume_up": "Je monte le son.",
    "volume_down": "Je baisse le son.",
    "mute": "Je coupe le son.",
    "search_youtube": "Je cherche ça sur YouTube.",
    "search_netflix": "Je cherche ça sur Netflix.",
    "camera_entree": "Je montre la caméra de l'entrée.",
    "camera_salon": "Je montre la caméra du salon.",
}


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def fast_intent(phrase: str) -> Intent | None:
    """Reconnaît localement les phrases sans ambiguïté, sans appeler le LLM."""
    text = _strip_accents(phrase.strip().lower())

    for pattern, commande in _FAST_ID_PATTERNS:
        match = pattern.search(text)
        if match:
            action_id = int(match.group(1))
            return Intent(
                commande=commande,  # type: ignore[arg-type]
                action_id=action_id,
                reformulation=_FAST_REFORMULATIONS[commande].format(id=action_id),
            )

    for pattern, commande in _FAST_PATTERNS:
        if pattern.search(text):
            return Intent(commande=commande, reformulation=_FAST_REFORMULATIONS[commande])  # type: ignore[arg-type]

    search_match = _MEDIA_SEARCH_RE.match(text)
    if search_match:
        query, service = search_match.groups()
        action = f"search_{service}"
        return Intent(
            commande="media",
            media_action=action,  # type: ignore[arg-type]
            media_query=query,
            reformulation=_FAST_REFORMULATIONS[action],
        )

    # "caméra"/"webcam" est un mot-clé sans ambiguïté avec le média (TV) :
    # testé avant le filtre de longueur ci-dessous, une phrase comme
    # "montre-moi la caméra du salon" dépasse 5 mots sans être pour
    # autant une commande complexe à laisser au LLM.
    for pattern, camera_name in _CAMERA_FAST_PATTERNS:
        if pattern.search(text):
            action = f"camera_{camera_name}"
            return Intent(
                commande="camera",
                camera_name=camera_name,  # type: ignore[arg-type]
                reformulation=_FAST_REFORMULATIONS[action],
            )

    # "cherche" : on laisse la phrase entière au LLM même si un mot-clé
    # media (ex. "netflix") apparaît aussi dedans : un raccourci ici
    # perdrait la requête de recherche (cf. `search_netflix`/`search_youtube`).
    # Limite de longueur : une phrase courte ("lance netflix") ne peut être
    # qu'une commande simple, mais une plus longue qui contient "netflix"
    # peut être une recherche déformée par la reconnaissance vocale (ex.
    # "Mais, The Cleaning Ladies, Netflix, s'il te plaît" pour "cherche
    # The Cleaning Lady sur Netflix"), dans le doute, on laisse le LLM
    # trancher plutôt que de lancer juste l'appli en perdant la requête.
    if "cherche" not in text and len(text.split()) <= 5:
        for pattern, action in _MEDIA_FAST_PATTERNS:
            if pattern.search(text):
                return Intent(
                    commande="media",
                    media_action=action,  # type: ignore[arg-type]
                    reformulation=_FAST_REFORMULATIONS[action],
                )

    return None

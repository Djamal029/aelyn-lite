"""Rédaction de candidatures (CV, lettre de motivation, email d'envoi).

Prompt direct avec le profil COMPLET (pas de RAG) : contrairement au
matching d'offres (`pipeline.py`), qui a besoin des chunks les plus
proches, une candidature a besoin de cohérence d'ensemble : le LLM doit
voir tout le profil pour choisir quoi mettre en avant pour une offre
donnée, pas juste les fragments les mieux notés.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Iterator

import dotenv

from aelyn.core.config import settings
from aelyn.core.llm import KEEP_ALIVE_OCCASIONAL, LLMClient
from aelyn_career.models import CVContent, CVExperience, CVProjet
from aelyn_career.profil_manager import ProfilManager, load_profil_json
from aelyn_career.prompts import (
    SYSTEM_CV,
    SYSTEM_EMAIL_ENVOI,
    SYSTEM_LM,
    SYSTEM_LM_COURT,
    SYSTEM_LM_REFINE,
)

dotenv.load_dotenv()
# Ollama plafonne le contexte à 4096 tokens par défaut quel que soit le
# modèle : le profil complet + une offre dépasse déjà cette limite
# (~5800 tokens mesurés), d'où un budget dédié à la rédaction.
#
# 16384 (valeur d'origine, unique pour tout ce module) était bien plus
# que nécessaire pour une LETTRE et provoquait un dépassement de VRAM sur
# un GPU 6 Go (RTX 3060 Laptop) : `ollama ps` montrait un modèle "8b"
# chargé à ~7.8 Go, dont ~46% recalculé sur CPU ("46%/54% CPU/GPU"),
# nettement plus lent et variable qu'une inférence 100% GPU. Mesuré en
# conditions réelles (même offre France Travail, même profil, lettre de
# motivation `SYSTEM_LM_COURT`) :
#   deepseek-r1:8b, num_ctx=16384 : 173s  (46%/54% CPU/GPU, ~7.8 Go)
#   deepseek-r1:8b, num_ctx=8192  : 389s  (36%/64% CPU/GPU, ~6.6 Go,
#                                    PIRE malgré moins de VRAM : un modèle
#                                    de raisonnement "pense" une durée
#                                    très variable avant de répondre,
#                                    cf. LLM_MODEL_FOR_OFFERS ci-dessus)
#   mistral:7b,     num_ctx=16384 : 62s   (37%/63% CPU/GPU, ~6.7 Go)
#   mistral:7b,     num_ctx=8192  : 41s   (26%/74% CPU/GPU, ~5.6 Go)
# -> 8192 adopté pour la LETTRE (`_NUM_CTX_TEXT`, texte libre `.text()`).
#
# Le CV (`draft_cv`, JSON contraint par schéma via `.structured()`) est
# un cas À PART, découvert en testant CE MÊME changement sur mistral:7b :
# réduire son num_ctx à 8192 a fait passer sa durée de ~200s (à 16384) à
# 1873s (31 MINUTES) sur un run. Revenu à 16384 pour le CV uniquement
# (`_NUM_CTX_CV`), mais MÊME à 16384, deux runs mesurés dans les mêmes
# conditions donnent 200s puis 691s : le CV reste nettement plus VARIABLE
# que la lettre, quel que soit num_ctx dans la plage testée. Hypothèse
# (non confirmée dans le détail) : le décodage contraint par schéma JSON
# (listes `max_length`, objets imbriqués) subit occasionnellement des
# retours en arrière coûteux quand la sortie générée manque de satisfaire
# le schéma du premier coup, un phénomène distinct du "raisonnement" des
# modèles comme deepseek-r1, et qui ne semble pas réglé par num_ctx seul.
# `_NUM_CTX_CV = 16384` évite le pire cas observé (1873s) sans éliminer
# cette variabilité résiduelle ; investigation à poursuivre si le CV
# reste un point de friction perçu (ex. instrumenter le nombre de
# tentatives dans `LLMClient.structured()`, ou comparer un modèle dédié
# pour CE seul appel).
_NUM_CTX_TEXT = 8192
_NUM_CTX_CV = 16384

_NUMBER_RE = re.compile(r"\d[\d\s.,]*\d|\d")
_MONTHS = {
    "jan": 1, "january": 1, "janvier": 1,
    "feb": 2, "february": 2, "fevrier": 2,
    "mar": 3, "march": 3, "mars": 3,
    "apr": 4, "april": 4, "avril": 4,
    "may": 5, "mai": 5,
    "jun": 6, "june": 6, "juin": 6,
    "jul": 7, "july": 7, "juillet": 7,
    "aug": 8, "august": 8, "aout": 8,
    "sep": 9, "september": 9, "septembre": 9,
    "oct": 10, "october": 10, "octobre": 10,
    "nov": 11, "november": 11, "novembre": 11,
    "dec": 12, "december": 12, "decembre": 12,
}


def _fold(text: str) -> str:
    """Casse et accents neutralisés, pour comparer un nom d'entreprise tel
    que reformulé par le LLM à celui du profil sans faux négatif trivial."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _numbers_in(text: str) -> set[str]:
    """Chiffres présents dans `text`, espaces/virgules de milliers retirés
    (« 217 000 » et « 217000 » doivent compter comme le même nombre)."""
    return {re.sub(r"[\s.,]", "", n) for n in _NUMBER_RE.findall(text)} - {""}


def _period_signature(period: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Normalise une période en années/mois même si le LLM traduit les mois."""
    words = re.findall(r"[a-z]+|\d{4}", _fold(period))
    years = tuple(int(word) for word in words if re.fullmatch(r"\d{4}", word))
    months = tuple(_MONTHS[word] for word in words if word in _MONTHS)
    return years, months


def _experience_identity(meta: dict) -> tuple[str, str, str]:
    return (
        _fold(meta.get("company", "")),
        _fold(meta.get("period", "")),
        _fold(meta.get("role", "")),
    )


def _experience_order(period: str) -> tuple[int, int]:
    years, months = _period_signature(period)
    return (years[0] if years else 0, months[0] if months else 0)


def offer_text(offre: dict) -> str:
    """Texte envoyé au LLM pour UNE offre France Travail, même
    construction que `pipeline._offer_text`, exposée ici pour que
    l'agent conversationnel n'ait pas à connaître ce détail."""
    return f"{offre.get('intitule', '')}\n{offre.get('description', '')}"


def format_cv_text(cv: CVContent) -> str:
    """Rendu texte lisible d'un `CVContent`, pour l'affichage/lecture en
    chat, pas un vrai document mis en page (voir le skill docx pour un
    CV final à envoyer)."""
    lignes = [cv.profil, "", "EXPÉRIENCES"]
    for e in cv.experiences:
        lignes.append(f"  {e.role} chez {e.entreprise} ({e.periode})")
        lignes.extend(f"    • {p}" for p in e.puces)
    if cv.projets:
        lignes += ["", "PROJETS"]
        lignes.extend(f"  {p.titre} : {p.description}" for p in cv.projets)
    lignes += ["", "COMPÉTENCES"]
    for categorie, items in cv.competences.items():
        lignes.append(f"  {categorie} : {', '.join(items)}")
    lignes += ["", "FORMATION"]
    lignes.extend(f"  {f}" for f in cv.formation)
    if cv.certifications:
        lignes += ["", "CERTIFICATIONS"]
        lignes.extend(f"  {c}" for c in cv.certifications)
    if cv.langues:
        lignes += ["", "LANGUES : " + ", ".join(cv.langues)]
    if cv.centres_interet:
        lignes += ["CENTRES D'INTÉRÊT : " + ", ".join(cv.centres_interet)]
    return "\n".join(lignes)


class ApplicationWriter:
    def __init__(
        self,
        profil_manager: ProfilManager | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.profil_manager = profil_manager or ProfilManager()
        # `keep_alive` COURT (`KEEP_ALIVE_OCCASIONAL`) : CV/LM sont des
        # usages BURSTY et peu fréquents (une candidature de temps en
        # temps, pas en continu), contrairement au modèle léger utilisé
        # pour presque tout le reste de la conversation. Mesuré sur un
        # GPU 6 Go (RTX 3060 Laptop) que ce modèle et le modèle léger ne
        # coexistent JAMAIS en VRAM (`ollama ps` confirme une éviction
        # complète, pas juste un ralentissement) : un `keep_alive` long
        # (30 min, par défaut) laisserait ce modèle lourd occuper la
        # VRAM bien après la rédaction, forçant le modèle léger à se
        # recharger pour la toute PROCHAINE action côté chat.
        self.llm = llm or LLMClient(model=settings.llm_model_career, keep_alive=KEEP_ALIVE_OCCASIONAL)

    def reload_llm(self) -> None:
        """Reconstruit `self.llm` depuis `settings.llm_model_career`
        COURANT. Nécessaire car `ApplicationWriter` est un singleton de
        longue durée côté API (`aelyn_api.deps.get_application_writer`,
        `ConversationalAgent.application_writer`) : son `LLMClient` est
        construit UNE SEULE FOIS avec le modèle d'alors, un `PATCH
        /settings` qui change `llm_model_career` ne s'y refléterait donc
        jamais tout seul. Appelée par le routeur settings juste après avoir
        persisté le nouveau modèle, sur CHAQUE instance vivante, pour un
        changement effectif immédiatement plutôt qu'au prochain
        redémarrage de l'API. Pas d'appel réseau ici : construire un
        `LLMClient` ne fait que préparer le client Ollama, le modèle n'est
        sollicité qu'au prochain `draft_cv`/`draft_cover_letter_stream`."""
        self.llm = LLMClient(model=settings.llm_model_career, keep_alive=KEEP_ALIVE_OCCASIONAL)

    def reload_profile(self) -> None:
        """Recharge `self.profil_manager` depuis `profil.json` sur disque.

        Même raison que `reload_llm` ci-dessus : `ProfilManager` lit le
        fichier une seule fois, à l'import du module `profil_manager`
        (`profil_json` global) ET à la construction de `ApplicationWriter`
        (singleton). Après `PUT /career/profile` (aelyn-api) a validé et
        écrit un nouveau `profil.json`, cette méthode est appelée sur
        CHAQUE instance vivante pour que CV/lettre de motivation reflètent
        le nouveau profil dès la prochaine génération, sans redémarrage."""
        self.profil_manager = ProfilManager(load_profil_json())

    def _profile_text(self) -> str:
        chunks = self.profil_manager.parse_profile()
        return "\n\n".join(c["text"] for c in chunks)

    def _user_input(self, offer_text: str) -> str:
        return f"PROFIL COMPLET :\n{self._profile_text()}\n\nOFFRE :\n{offer_text}"

    def _real_project_description(self, titre: str) -> str | None:
        """Description réelle du profil pour ce titre de projet exact, ou
        `None` si le titre ne correspond à aucun projet du profil."""
        for chunk in self.profil_manager.parse_profile():
            if chunk["type"] == "project" and chunk["title"].strip().lower() == titre.strip().lower():
                return chunk["metadata"].get("description", "").strip()
        return None

    def _real_experience_metadata(
        self,
        entreprise: str,
        periode: str = "",
        role: str = "",
        used: set[tuple[str, str, str]] | None = None,
    ) -> dict | None:
        """Métadonnées réelles du profil pour cette entreprise, ou `None`
        si aucune expérience du profil ne correspond. Comparaison par
        sous-chaîne dans les deux sens (accents/casse neutralisés) pour
        tolérer une légère reformulation du nom par le LLM, sans jamais
        faire confiance à sa paraphrase pour le contenu lui-même."""
        cible = _fold(entreprise)
        candidates = [
            chunk["metadata"]
            for chunk in self.profil_manager.parse_profile()
            if chunk["type"] == "experience"
            and (reelle := _fold(chunk["metadata"].get("company", "")))
            and (cible in reelle or reelle in cible)
        ]
        if not candidates:
            return None

        signature = _period_signature(periode)
        if any(signature):
            exact_period = [
                meta for meta in candidates
                if _period_signature(meta.get("period", "")) == signature
            ]
            if exact_period:
                candidates = exact_period

        role_key = _fold(role)
        exact_role = [
            meta for meta in candidates
            if _fold(meta.get("role", "")) == role_key
        ]
        if role_key and exact_role:
            candidates = exact_role

        for meta in candidates:
            if used is None or _experience_identity(meta) not in used:
                return meta
        return None

    def _validate_experiences(
        self, experiences: list[CVExperience]
    ) -> list[CVExperience]:
        """Une expérience réelle n'implique pas que CHAQUE chiffre placé
        dedans par le LLM lui appartienne vraiment : observé en pratique,
        un chiffre réel du profil (« 217 000 publications, 43 000
        comptes »), mais tiré d'un projet académique sans rapport, recopié
        dans une puce de l'expérience « Les Vieilles Charrues ». On ne
        fait plus confiance à la paraphrase pour les chiffres : toute
        puce contenant un chiffre absent du texte RÉEL de CETTE expérience
        précise est supprimée plutôt que gardée avec un chiffre
        possiblement mal attribué. Une expérience qui ne correspond à
        AUCUNE entreprise du profil est exclue en entier (même principe
        que `_validate_projets` pour les titres de projet inventés)."""
        validated: list[CVExperience] = []
        used: set[tuple[str, str, str]] = set()
        for exp in experiences:
            meta = self._real_experience_metadata(
                exp.entreprise, exp.periode, exp.role, used
            )
            if meta is None:
                continue
            used.add(_experience_identity(meta))
            highlights = meta.get("highlights", [])
            result_values = [str(value) for value in meta.get("results", {}).values()]
            texte_reel = " ".join(
                [meta.get("description", ""), *highlights, *result_values]
            )
            chiffres_reels = _numbers_in(texte_reel)
            puces = [p for p in exp.puces if _numbers_in(p) <= chiffres_reels]
            if not puces:
                # Toutes les puces contenaient un chiffre non vérifiable
                # pour cette expérience : on retombe sur les
                # highlights RÉELS du profil (déjà du texte source, pas
                # une paraphrase) plutôt que de supprimer l'expérience
                # entière : l'utilisateur a bien fait ce stage.
                puces = self._fallback_experience_bullets(meta)
            validated.append(
                CVExperience(
                    role=meta.get("role", exp.role),
                    # Nom réel du profil, jamais celui rendu par le LLM :
                    # un modèle plus petit peut retourner "Servier France
                    # chez Servier France" (le mot "chez" déjà inclus dans
                    # le champ), qui s'affiche ensuite en double une fois
                    # que le code ajoute son propre "chez {entreprise}".
                    entreprise=meta.get("company", exp.entreprise),
                    periode=meta.get("period", exp.periode),
                    puces=puces[:3],
                )
            )

        source_experiences = [
            chunk["metadata"]
            for chunk in self.profil_manager.parse_profile()
            if chunk["type"] == "experience"
        ]
        if len(source_experiences) <= 4:
            for meta in source_experiences:
                identity = _experience_identity(meta)
                if identity in used:
                    continue
                validated.append(
                    CVExperience(
                        role=meta.get("role", ""),
                        entreprise=meta.get("company", ""),
                        periode=meta.get("period", ""),
                        puces=self._fallback_experience_bullets(meta),
                    )
                )
                used.add(identity)

        validated.sort(key=lambda item: _experience_order(item.periode), reverse=True)
        return validated

    @staticmethod
    def _fallback_experience_bullets(meta: dict) -> list[str]:
        """Utilise les faits du profil pour préserver une expérience omise."""
        highlights = list(meta.get("highlights", []))
        results = [str(value) for value in meta.get("results", {}).values()]
        description = meta.get("description", "").strip()
        bullets = highlights[:2] if results else highlights[:3]
        bullets.extend(results[: 3 - len(bullets)])
        if not bullets and description:
            bullets = [description[:200]]
        return bullets[:3]

    def _validate_projets(self, projets: list[CVProjet]) -> list[CVProjet]:
        """Un titre de projet correct n'implique pas une description
        correcte : observé en pratique, le LLM peut reprendre un vrai
        titre du profil mais lui coller une description recopiée d'une
        autre section (ex. une expérience) au lieu du vrai texte du
        projet. On ne fait plus confiance à sa paraphrase : la description
        est remplacée par le texte réel du profil (tronqué à une ligne),
        et un titre qui ne correspond à AUCUN projet réel est exclu plutôt
        que gardé avec une description fabriquée."""
        validated = []
        for p in projets:
            reelle = self._real_project_description(p.titre)
            if reelle is None:
                continue
            if len(reelle) > 220:
                reelle = reelle[:220].rsplit(" ", 1)[0] + "…"
            validated.append(CVProjet(titre=p.titre, description=reelle))
        return validated

    def _real_formation(self) -> list[str]:
        """Reprend la formation directement du profil réel, jamais la
        paraphrase du LLM pour `cv.formation` (simple `list[str]`, sans
        validation jusqu'ici contrairement à `experiences`/`projets`) :
        malgré le prompt ("reprends l'établissement et le diplôme
        EXACTEMENT...") et le chunk RAG dédié déjà ajouté pour lui donner
        la vraie donnée (cf. le commentaire dans
        `profil_manager.parse_profile`), le LLM peut encore la reformuler
        ou en omettre une. Contrairement à l'expérience/aux projets, il
        n'y a aucune raison de filtrer la formation par pertinence à
        l'offre (le profil en compte typiquement 1 à 3 entrées, toutes
        attendues dans n'importe quel CV) : on reconstruit la liste en
        entier depuis le profil plutôt que de valider/filtrer la sortie
        du LLM."""
        return [
            f"{chunk['metadata']['degree']} en {chunk['metadata']['field']}, "
            f"{chunk['metadata']['institution']} ({chunk['metadata'].get('period', '?')})"
            for chunk in self.profil_manager.parse_profile()
            if chunk["type"] == "education"
        ]

    def draft_cv(self, offer_text: str) -> CVContent:
        cv = self.llm.structured(
            schema=CVContent,
            system=SYSTEM_CV.format(user_name=settings.user_name),
            user=self._user_input(offer_text),
            num_ctx=_NUM_CTX_CV,
        )
        cv.experiences = self._validate_experiences(cv.experiences)
        cv.projets = self._validate_projets(cv.projets)
        cv.formation = self._real_formation()
        return cv

    @staticmethod
    def contact_header() -> str:
        """En-tête assemblé à partir de `settings`, jamais généré par le
        LLM (une identité inventée est un risque bien plus grave qu'un
        champ manquant). Un champ non renseigné dans `.env` est
        simplement omis, pas remplacé par un espace réservé."""
        lignes = [
            settings.user_full_name,
            settings.user_city,
            settings.user_phone,
            settings.user_contact_email,
            f"LinkedIn : {settings.user_linkedin}" if settings.user_linkedin else None,
        ]
        return "\n".join(l for l in lignes if l)

    def draft_cover_letter(self, offer_text: str, *, short: bool = False) -> str:
        system = SYSTEM_LM_COURT if short else SYSTEM_LM
        corps = self.llm.text(
            system=system.format(user_name=settings.user_name),
            user=self._user_input(offer_text),
            num_ctx=_NUM_CTX_TEXT,
        )
        if short:
            return corps
        header = self.contact_header()
        return f"{header}\n\n{corps}" if header else corps

    def draft_cover_letter_stream(self, offer_text: str, *, short: bool = False) -> Iterator[str]:
        """Comme `draft_cover_letter()`, mais diffuse le CORPS au fur et
        à mesure (cf. `LLMClient.text_stream`), pour l'affichage
        progressif côté chat (CLI/API). Ne yield JAMAIS l'en-tête
        (`contact_header()`) : celui-ci n'est pas généré par le LLM et ne
        se lit pas à voix haute (cf. `contact_header`), c'est à l'appelant
        de l'afficher séparément, comme il le fait déjà pour
        `draft_cover_letter()`."""
        system = SYSTEM_LM_COURT if short else SYSTEM_LM
        yield from self.llm.text_stream(
            system=system.format(user_name=settings.user_name),
            user=self._user_input(offer_text),
            num_ctx=_NUM_CTX_TEXT,
        )

    def refine_cover_letter(self, previous_letter: str, offer_text: str) -> str:
        """« affine cette lettre de motivation » : améliore la forme d'une
        lettre déjà générée (via `draft_cover_letter`) sans repartir de
        zéro et sans changer les faits : `SYSTEM_LM_REFINE` l'interdit
        explicitement."""
        header = self.contact_header()
        corps_precedent = (
            previous_letter[len(header):].lstrip("\n")
            if header and previous_letter.startswith(header)
            else previous_letter
        )
        corps = self.llm.text(
            system=SYSTEM_LM_REFINE.format(user_name=settings.user_name),
            user=f"LETTRE ACTUELLE :\n{corps_precedent}\n\nOFFRE :\n{offer_text}",
            num_ctx=_NUM_CTX_TEXT,
        )
        return f"{header}\n\n{corps}" if header else corps

    def refine_cover_letter_stream(self, previous_letter: str, offer_text: str) -> Iterator[str]:
        """Version diffusée de `refine_cover_letter()`, ne yield que le
        corps, même contrat que `draft_cover_letter_stream()`."""
        header = self.contact_header()
        corps_precedent = (
            previous_letter[len(header):].lstrip("\n")
            if header and previous_letter.startswith(header)
            else previous_letter
        )
        yield from self.llm.text_stream(
            system=SYSTEM_LM_REFINE.format(user_name=settings.user_name),
            user=f"LETTRE ACTUELLE :\n{corps_precedent}\n\nOFFRE :\n{offer_text}",
            num_ctx=_NUM_CTX_TEXT,
        )

    def draft_email_envoi(self, offer_name: str) -> str:
        return self.llm.text(
            system=SYSTEM_EMAIL_ENVOI.format(user_name=settings.user_name),
            user=offer_name,
        )

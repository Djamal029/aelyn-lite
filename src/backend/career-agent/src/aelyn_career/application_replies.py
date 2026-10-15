"""Détecte, parmi des mails récents, les réponses à des candidatures déjà
suivies (`ApplicationsStore`), et met à jour leur statut avec les détails
extraits (ex. date/heure d'entretien, contact recruteur).

Lecture seule côté boîte mail : ce module ne touche jamais un flag IMAP
(pas de `\\Seen`, pas d'archivage) - c'est un enrichissement du suivi des
candidatures, pas un agent mail de plus. Les mails à examiner viennent de
`aelyn_email.client.list_recent_or_flagged` (lus OU non lus, cf. son
docstring) plutôt que de `list_unread` : une réponse de recruteur déjà
consultée sur le téléphone, par exemple, doit quand même être détectée.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from aelyn.core.journal import ActionStatus, Journal
from aelyn.core.llm import LLMClient, LLMError
from aelyn_career.applications import Application, ApplicationsStore, ApplicationStatus
from aelyn_career.prompts import (
    SYSTEM_APPLICATION_CONFIRMATION,
    SYSTEM_APPLICATION_REPLY,
    SYSTEM_INTERVIEW_DATE_EXTRACTION,
)
from aelyn_email.models import Mail

logger = logging.getLogger(__name__)

AGENT_NAME = "career"
_REPLY_ACTION = "reponse_candidature"
_CONFIRMATION_ACTION = "candidature_detectee"


class ReplyOutcome(StrEnum):
    ENTRETIEN = "entretien"
    REFUS = "refus"
    ACCUSE_RECEPTION = "accuse_reception"
    RELANCE_DEMANDEE = "relance_demandee"
    AUTRE = "autre"
    NON_PERTINENT = "non_pertinent"


# Seules les issues sans ambiguïté font avancer le statut suivi : un
# "accusé de réception" ou une "relance demandée" ne doit pas écraser un
# statut déjà plus avancé (ex. déjà en "entretien"), donc ne déclenche
# aucune mise à jour automatique de `status` (seulement une note, cf.
# `check_application_replies`).
_OUTCOME_TO_STATUS: dict[ReplyOutcome, ApplicationStatus] = {
    ReplyOutcome.ENTRETIEN: ApplicationStatus.ENTRETIEN,
    ReplyOutcome.REFUS: ApplicationStatus.REFUSE,
}


class ReplyAnalysis(BaseModel):
    """Ce que le LLM doit produire pour UN mail candidat."""

    est_reponse_candidature: bool
    issue: ReplyOutcome
    resume: str = Field(max_length=300)
    details_entretien: str | None = None


@dataclass(slots=True, frozen=True)
class ApplicationReplyResult:
    mail: Mail
    application: Application
    analysis: ReplyAnalysis
    status_changed: bool


# Mots trop courants pour servir de signal de correspondance à eux seuls
# (un mot de 4+ lettres partagé par hasard entre deux offres sans rapport
# ne doit pas déclencher un faux rapprochement).
_GENERIC_WORDS = {
    "stage", "stagiaire", "data", "science", "scientist", "analyst",
    "analyste", "poste", "pour", "avec", "dans", "sous", "chez", "votre",
    "notre", "equipe", "team", "the", "and", "pour", "une", "des",
}


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _distinctive_words(text: str, min_len: int = 4) -> set[str]:
    words = re.findall(r"\w+", _strip_accents(text.lower()))
    return {w for w in words if len(w) >= min_len and w not in _GENERIC_WORDS}


def _find_by_title_overlap(store: ApplicationsStore, title: str, *, min_overlap: int = 3) -> Application | None:
    """Retrouve une candidature déjà suivie via son INTITULÉ seul, en
    tolérant les variations d'accentuation/reformulation entre deux
    extractions LLM du même intitulé (bug réel observé : un intitulé
    stocké sans accents - "Modelisation..." - ne matchait jamais le même
    intitulé ré-extrait avec accents - "Modélisation..." - via
    `find_by_text`, qui exige un match exact mot-à-mot). Un recoupement
    de plusieurs mots DISTINCTIFS (pas un seul, pour éviter un faux
    positif sur un mot générique de stage) suffit, sans exiger l'entreprise."""
    title_words = _distinctive_words(title)
    if len(title_words) < min_overlap:
        return None
    for app in store.list():
        if len(title_words & _distinctive_words(app.title)) >= min_overlap:
            return app
    return None


def match_application(
    store: ApplicationsStore, *, subject: str, sender: str, sender_email: str, body: str = ""
) -> Application | None:
    """Associe un mail à une candidature suivie. Trois signaux, du plus
    au moins fiable :
    1. un mot distinctif du nom d'ENTREPRISE suivi apparaît dans le mail
       (objet, expéditeur ou corps) - fonctionne même pour un mail
       AUTO-TRANSFÉRÉ par l'utilisateur lui-même (expéditeur = sa propre
       adresse, pas celle du recruteur : bug réel observé, le domaine de
       l'expéditeur était alors inexploitable) ;
    2. le domaine de l'expéditeur correspond à l'entreprise suivie (ex.
       "laura.couepel@phosphea.com" -> "Phosphea") ;
    3. `find_by_text` (correspondance stricte mot-à-mot) en dernier
       repli, surtout utile pour un objet très court et propre.
    Le TITRE n'est volontairement jamais utilisé seul : un intitulé de
    stage générique ("Data Scientist") se retrouve dans trop d'offres
    sans rapport pour être un signal fiable à lui seul."""
    haystack = f"{subject} {sender} {sender_email} {body}".lower()

    for app in store.list():
        company_words = _distinctive_words(app.company or "")
        if company_words and any(word in haystack for word in company_words):
            return app

    domain = sender_email.rsplit("@", 1)[-1].split(".")[0] if "@" in sender_email else ""
    if len(domain) >= 3:
        candidate = store.find_by_text(domain)
        if candidate is not None:
            return candidate

    return store.find_by_text(f"{subject} {sender}")


def analyze_reply(llm: LLMClient, mail: Mail) -> ReplyAnalysis | None:
    """`None` si le LLM est indisponible : une erreur de classification
    sur UN mail ne doit jamais interrompre l'examen des autres."""
    try:
        return llm.structured(
            schema=ReplyAnalysis,
            system=SYSTEM_APPLICATION_REPLY,
            user=mail.for_llm(max_chars=2500),
        )
    except LLMError:
        logger.exception("Analyse de réponse candidature impossible pour %s", mail.uid)
        return None


def _blank_placeholder_to_none(value: str | None) -> str | None:
    """Un LLM écrit parfois le mot "null"/"none" en texte plutôt que la
    valeur JSON `null` elle-même (observé en direct : un mail de
    confirmation qui ne nomme jamais l'employeur réel a produit
    `entreprise="null"`, une chaîne non vide donc jamais filtrée par un
    simple `if not ...` - qui a fini par créer un doublon de candidature
    avec une entreprise "null" affichée). Réutilisé par tout modèle
    d'extraction LLM de ce module, pas seulement `ApplicationConfirmation`."""
    if isinstance(value, str) and value.strip().lower() in {"null", "none", "n/a", ""}:
        return None
    return value


class ApplicationConfirmation(BaseModel):
    """Ce que le LLM doit produire pour un mail candidat à une NOUVELLE
    candidature (par opposition à `ReplyAnalysis`, qui suppose une
    candidature déjà suivie)."""

    est_confirmation_candidature: bool
    entreprise: str | None = None
    intitule_poste: str | None = None

    @field_validator("entreprise", "intitule_poste", mode="before")
    @classmethod
    def _validate_placeholders(cls, value: str | None) -> str | None:
        return _blank_placeholder_to_none(value)


# Garde-fou déterministe en plus du LLM (même esprit que
# `_blank_placeholder_to_none`) : observé en direct, le LLM extrait
# parfois un simple RAPPEL du contexte ("second entretien", "prochain
# entretien") comme `date_entretien`, même en l'absence de toute
# date/heure réelle dans la phrase (ex. "on me demande ma disponibilité
# pour le second entretien" - aucune date proposée) - ce qui écrasait une
# date déjà enregistrée avec un texte inutile. Exige un vrai signal de
# date/heure dans la valeur elle-même (chiffre, mois, jour de semaine,
# "demain"...) plutôt que de faire confiance au jugement du LLM seul.
_CONCRETE_DATE_RE = re.compile(
    r"\d|janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|"
    r"octobre|novembre|d[ée]cembre|"
    r"lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|"
    r"demain|aujourd|ce soir|matin|apr[èe]s.midi",
    re.IGNORECASE,
)


class InterviewDateProposal(BaseModel):
    """Ce que le LLM doit extraire d'une phrase dite en chat/voix à propos
    d'un entretien (ex. "mon entretien chez Phosphea est le 20/10 à
    14h") : quelle candidature suivie est concernée, et la date/heure
    proposée telle que formulée par l'utilisateur."""

    entreprise: str | None = None
    date_entretien: str | None = None

    @field_validator("entreprise", mode="before")
    @classmethod
    def _validate_entreprise(cls, value: str | None) -> str | None:
        return _blank_placeholder_to_none(value)

    @field_validator("date_entretien", mode="before")
    @classmethod
    def _validate_date_entretien(cls, value: str | None) -> str | None:
        value = _blank_placeholder_to_none(value)
        if value is not None and not _CONCRETE_DATE_RE.search(value):
            return None
        return value


# Préfiltre bon marché AVANT tout appel LLM : la grande majorité des
# mails (newsletters, personnel, administratif...) n'ont évidemment rien
# à voir avec une candidature, les analyser tous coûterait un appel LLM
# par mail pour rien. Volontairement large (mieux vaut un faux positif
# ici, éliminé ensuite par le LLM, qu'un vrai accusé de réception raté).
_CONFIRMATION_KEYWORDS = (
    "candidature", "application", "postul", "a bien été reçue",
    "has been received", "was sent to", "application received",
)


def _looks_like_application_confirmation(mail: Mail) -> bool:
    haystack = f"{mail.subject} {mail.body[:1000]}".lower()
    return any(keyword in haystack for keyword in _CONFIRMATION_KEYWORDS)


def detect_application_confirmation(
    llm: LLMClient, mail: Mail
) -> ApplicationConfirmation | None:
    """`None` si le LLM est indisponible (même logique que
    `analyze_reply` : jamais laissé interrompre l'examen des autres
    mails)."""
    try:
        return llm.structured(
            schema=ApplicationConfirmation,
            system=SYSTEM_APPLICATION_CONFIRMATION,
            user=mail.for_llm(max_chars=2500),
        )
    except LLMError:
        logger.exception("Détection de confirmation de candidature impossible pour %s", mail.uid)
        return None


def extract_interview_date(llm: LLMClient, phrase: str) -> InterviewDateProposal | None:
    """`None` si le LLM est indisponible (même logique que
    `analyze_reply`/`detect_application_confirmation`)."""
    try:
        return llm.structured(
            schema=InterviewDateProposal,
            system=SYSTEM_INTERVIEW_DATE_EXTRACTION,
            user=phrase,
        )
    except LLMError:
        logger.exception("Extraction de date d'entretien impossible pour : %s", phrase)
        return None


# Fenêtre large plutôt qu'un vrai "depuis toujours" : `Journal.since` ne
# prend qu'un nombre d'heures, pas de borne infinie. 5 ans couvre tout
# usage réel sans alourdir la requête.
_DEDUP_WINDOW_HOURS = 24 * 365 * 5


def _already_processed_uids(journal: Journal) -> set[str]:
    """UID des mails déjà passés par `check_application_replies` (qu'ils
    aient matché une candidature ou non n'a pas d'importance ici, cf.
    appelant) : sans ce filtre, rappeler la fonction (ex. bouton
    "actualiser" du suivi) réanalyserait et re-noterait les MÊMES mails
    à chaque fois, en plus de refaire un appel LLM inutile par mail déjà
    vu."""
    return {
        action.payload["mail_uid"]
        for action in journal.since(hours=_DEDUP_WINDOW_HOURS, agent=AGENT_NAME)
        if action.action in (_REPLY_ACTION, _CONFIRMATION_ACTION) and "mail_uid" in action.payload
    }


def _slugify(*parts: str) -> str:
    raw = "-".join(p for p in parts if p).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return (slug or "offre")[:80]


def _try_detect_new_application(
    store: ApplicationsStore, llm: LLMClient, mail: Mail, *, journal: Journal | None
) -> ApplicationReplyResult | None:
    """Repli quand `mail` ne matche AUCUNE candidature déjà suivie :
    peut-être s'agit-il d'une candidature envoyée HORS d'AELYN (portail,
    plateforme type HelloWork/LinkedIn...) et donc jamais trackée. Un
    accusé de réception la révèle, cf. `ApplicationConfirmation`.
    Préfiltre par mots-clés avant tout appel LLM (cf.
    `_looks_like_application_confirmation`) : la quasi-totalité des mails
    non matchés n'ont évidemment aucun rapport avec une candidature."""
    if not _looks_like_application_confirmation(mail):
        return None

    confirmation = detect_application_confirmation(llm, mail)
    if confirmation is None:
        return None  # échec LLM transitoire, jamais marqué vu

    if not confirmation.est_confirmation_candidature or not confirmation.intitule_poste:
        if journal is not None:
            journal.record(
                agent=AGENT_NAME,
                action=_CONFIRMATION_ACTION,
                target=None,
                summary=f"{mail.subject} : non pertinent",
                status=ActionStatus.EXECUTED,
                payload={"mail_uid": mail.uid},
            )
        return None

    # Peut-être déjà suivie sous un autre offer_id (ex. trackée
    # manuellement avant ce mail, ou l'entreprise n'est pas nommée dans
    # CE mail-ci mais l'intitulé recoupe une candidature déjà connue) :
    # ne jamais créer de doublon. Le recoupement par intitulé seul (donc
    # SANS exiger l'entreprise) est volontairement vérifié en premier :
    # une plateforme comme un portail d'école confirme souvent l'envoi
    # sans jamais nommer l'employeur réel, cf. `_find_by_title_overlap`.
    existing = _find_by_title_overlap(store, confirmation.intitule_poste)
    if existing is None and confirmation.entreprise:
        existing = store.find_by_text(f"{confirmation.entreprise} {confirmation.intitule_poste}")
    if existing is not None:
        if journal is not None:
            journal.record(
                agent=AGENT_NAME,
                action=_CONFIRMATION_ACTION,
                target=existing.company,
                summary=f"{existing.title} : déjà suivie",
                status=ActionStatus.EXECUTED,
                payload={"mail_uid": mail.uid, "offer_id": existing.offer_id},
            )
        return None

    title = confirmation.intitule_poste
    offer_id = _slugify(confirmation.entreprise or "", title)
    application = store.record(offer_id=offer_id, title=title, company=confirmation.entreprise)

    if journal is not None:
        cible = f" chez {application.company}" if application.company else ""
        journal.record(
            agent=AGENT_NAME,
            action=_CONFIRMATION_ACTION,
            target=application.company,
            summary=f"Nouvelle candidature détectée : {application.title}{cible}",
            status=ActionStatus.EXECUTED,
            payload={"mail_uid": mail.uid, "offer_id": application.offer_id},
        )

    return ApplicationReplyResult(
        mail=mail,
        application=application,
        analysis=ReplyAnalysis(
            est_reponse_candidature=True,
            issue=ReplyOutcome.AUTRE,
            resume="Candidature détectée automatiquement dans les mails (envoyée hors AELYN).",
        ),
        status_changed=True,
    )


def check_application_replies(
    store: ApplicationsStore,
    llm: LLMClient,
    mails: list[Mail],
    *,
    journal: Journal | None = None,
) -> list[ApplicationReplyResult]:
    """Examine `mails`, ne garde que ceux qui matchent une candidature
    suivie, les fait classifier, et met à jour `store` + journalise
    chaque résultat retenu. Ne modifie jamais `mails` lui-même ni la
    boîte mail - purement un enrichissement du suivi.

    `journal`, s'il est fourni, sert aussi à ÉVITER de retraiter un mail
    déjà vu lors d'un appel précédent (cf. `_already_processed_uids`) :
    sans lui, chaque appel (ex. "actualiser" côté interface) repart de
    zéro sur TOUS les mails rendus par `list_recent_or_flagged`."""
    already_seen = _already_processed_uids(journal) if journal is not None else set()
    results: list[ApplicationReplyResult] = []

    for mail in mails:
        if mail.uid in already_seen:
            continue

        application = match_application(
            store, subject=mail.subject, sender=mail.sender,
            sender_email=mail.sender_email, body=mail.body,
        )
        if application is None:
            new_result = _try_detect_new_application(store, llm, mail, journal=journal)
            if new_result is not None:
                results.append(new_result)
            continue

        analysis = analyze_reply(llm, mail)
        if analysis is None:
            # Échec LLM (transitoire) : jamais marqué comme vu, pour
            # retenter au prochain appel plutôt que d'abandonner ce mail
            # silencieusement pour toujours.
            continue

        if not analysis.est_reponse_candidature:
            # Classé non pertinent : marqué comme vu quand même (sinon
            # un "actualiser" répété refacturerait le même appel LLM
            # indéfiniment sur ce mail), mais rien à rapporter.
            if journal is not None:
                journal.record(
                    agent=AGENT_NAME,
                    action="reponse_candidature",
                    target=application.company or application.title,
                    summary=f"{mail.subject} : non pertinent",
                    status=ActionStatus.EXECUTED,
                    payload={
                        "offer_id": application.offer_id,
                        "mail_uid": mail.uid,
                        "issue": analysis.issue.value,
                    },
                )
            continue

        new_status = _OUTCOME_TO_STATUS.get(analysis.issue)
        note_parts = [analysis.resume]
        if analysis.details_entretien:
            note_parts.append(f"Entretien : {analysis.details_entretien}")
        note_parts.append(f"(mail du {mail.sender}, objet « {mail.subject} »)")
        note = " ".join(note_parts)

        if new_status is not None:
            updated = store.update_status(application.offer_id, new_status, note=note)
            status_changed = updated is not None and updated.status != application.status
            application = updated or application
        else:
            # `accuse_reception`/`relance_demandee`/`autre` : statut
            # inchangé (jamais écrasé par une issue moins avancée qu'un
            # entretien déjà enregistré), mais la note reste utile.
            updated = store.update_status(application.offer_id, application.status, note=note)
            application = updated or application
            status_changed = False

        if journal is not None:
            journal.record(
                agent=AGENT_NAME,
                action="reponse_candidature",
                target=application.company or application.title,
                summary=f"{application.title} : {analysis.resume}",
                status=ActionStatus.EXECUTED,
                payload={
                    "offer_id": application.offer_id,
                    "mail_uid": mail.uid,
                    "issue": analysis.issue.value,
                    "nouveau_statut": application.status.value,
                },
            )

        results.append(
            ApplicationReplyResult(
                mail=mail,
                application=application,
                analysis=analysis,
                status_changed=status_changed,
            )
        )

    return results

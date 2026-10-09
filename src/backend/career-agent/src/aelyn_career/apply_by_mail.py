"""Génère CV + lettre de motivation pour une offre, les rend en PDF
(polis via LLM, cf. `ApplicationWriter.polish_cv_with_llm`/
`polish_cover_letter_with_llm`) et les envoie par mail à l'utilisateur
lui-même (jamais à l'employeur : aucune source d'offres de ce projet ne
fournit d'email de contact direct, seulement une URL de candidature, cf.
`source_adapters.py`).

Partagé entre `aelyn_api.routers.career` (bouton "M'envoyer par mail")
et `aelyn_conversation.agent` (commande vocale/texte "envoie le CV et la
lettre par mail") : avant ce module, cette logique n'existait que dans
la route HTTP, inatteignable depuis le chat/la voix.
"""

from __future__ import annotations

from aelyn.core.config import settings
from aelyn.core.llm import LLMError
from aelyn_career.application_writer import ApplicationWriter, offer_text
from aelyn_career.pdf_export import cover_letter_to_pdf_bytes, cv_to_pdf_bytes
from aelyn_email.client import send_mail_with_attachments


class ApplyByMailError(RuntimeError):
    """Échec clair (config manquante, LLM indisponible, envoi impossible)
    à traduire par l'appelant (HTTPException côté API, message parlé
    côté agent conversationnel) - jamais une exception brute."""


def send_application_by_mail(writer: ApplicationWriter, offre: dict) -> str:
    """Génère, met en forme et envoie CV + lettre pour `offre`. Renvoie
    l'adresse de destination en cas de succès."""
    dest = settings.user_contact_email or settings.email_user
    if not dest:
        raise ApplyByMailError(
            "Aucune adresse mail configurée (USER_CONTACT_EMAIL ou EMAIL_USER)."
        )

    titre = offre.get("intitule") or offre.get("title") or "cette offre"
    try:
        cv = writer.draft_cv(offer_text(offre))
        lettre = writer.draft_cover_letter(offer_text(offre))
    except LLMError as exc:
        raise ApplyByMailError(f"LLM indisponible : {exc}") from exc

    # Document final envoyé à un vrai employeur : on investit le temps
    # LLM ici pour le style (verbes d'action forts, prose moins
    # mécanique), contrairement à l'aperçu rapide dans le chat (CV/LM
    # restent déterministes là-bas). Chaque polish retombe
    # silencieusement sur la version déterministe en cas d'échec (LLM
    # indisponible, ou faits altérés) : jamais d'erreur ici pour un
    # simple échec de style.
    cv = writer.polish_cv_with_llm(cv)
    lettre = writer.polish_cover_letter_with_llm(lettre)

    cv_pdf = cv_to_pdf_bytes(cv, header_lines=writer.contact_header().split("\n"))
    lm_pdf = cover_letter_to_pdf_bytes(lettre)

    try:
        send_mail_with_attachments(
            to=dest,
            subject=f"Candidature prête : {titre}",
            body=(
                f"Voici le CV et la lettre de motivation générés pour "
                f"« {titre} », prêts à joindre sur le site de l'offre."
            ),
            attachments=[
                ("CV.pdf", cv_pdf, "pdf"),
                ("Lettre_de_motivation.pdf", lm_pdf, "pdf"),
            ],
        )
    except Exception as exc:
        raise ApplyByMailError(f"Envoi du mail impossible : {exc}") from exc

    return dest

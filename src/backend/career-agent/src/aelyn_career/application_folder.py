"""Dossier de candidature local : un sous-dossier par offre, avec la
description de l'offre, le CV et la lettre de motivation en Word ET PDF.

Complète `apply_by_mail.py` (qui envoie les PDF par mail) sans le
remplacer : un mail peut être archivé/perdu, un dossier local réutilisable
(pour relire, corriger à la main, joindre à un formulaire de candidature
qui n'accepte pas d'email direct) ne dépend pas de la boîte mail. Les deux
peuvent être appelés l'un après l'autre sans regénérer deux fois le
contenu, en se passant le même `cv`/`lettre` déjà polis.
"""

from __future__ import annotations

import re
from pathlib import Path

from aelyn.core.config import settings
from aelyn.core.llm import LLMError
from aelyn_career.application_writer import ApplicationWriter, offer_text
from aelyn_career.docx_export import cover_letter_to_docx_bytes, cv_to_docx_bytes
from aelyn_career.models import CVContent
from aelyn_career.pdf_export import cover_letter_to_pdf_bytes, cv_to_pdf_bytes

_INVALID_FOLDER_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ApplicationFolderError(RuntimeError):
    """Échec clair (LLM indisponible, écriture disque impossible) à
    traduire par l'appelant plutôt qu'une exception brute."""


def _offer_company_and_title(offre: dict) -> tuple[str, str]:
    """Même extraction que `apply_by_mail.send_application_by_mail` (deux
    formats possibles selon la source : France Travail `intitule`/
    `entreprise.nom`, ou le format canonique `title`/`company`) - gardée
    cohérente entre les deux modules plutôt que dupliquée différemment."""
    titre = offre.get("intitule") or offre.get("title") or "Offre"
    entreprise = offre.get("entreprise")
    company = (
        entreprise.get("nom") if isinstance(entreprise, dict) else entreprise
    ) or offre.get("company") or ""
    return str(company).strip(), str(titre).strip()


def _folder_name(company: str, titre: str) -> str:
    """"Entreprise - Intitulé", nettoyé des caractères invalides sur un
    nom de dossier Windows. Tronqué à 120 caractères : largement assez
    pour rester lisible, et NTFS/Windows plafonne un chemin complet bien
    avant la limite par composant (255) de toute façon."""
    raw = f"{company} - {titre}" if company else titre
    cleaned = _INVALID_FOLDER_CHARS.sub("", raw).strip(" .")
    return cleaned[:120] or "Offre"


def _offer_folder(company: str, titre: str) -> Path:
    return settings.applications_export_dir_resolved / _folder_name(company, titre)


def save_application_folder(
    writer: ApplicationWriter,
    offre: dict,
    *,
    cv: CVContent | None = None,
    lettre: str | None = None,
) -> Path:
    """Écrit (ou réécrit) le dossier de candidature pour `offre` : crée le
    sous-dossier s'il n'existe pas encore, puis (ré)écrit description,
    CV et lettre dedans - jamais d'accumulation de versions numérotées,
    une candidature a UN dossier qui reflète toujours son dernier état.

    `cv`/`lettre` : réutilise un brouillon déjà généré/poli par
    l'appelant (ex. `send_application_by_mail`) si fourni, pour ne jamais
    payer deux fois le coût LLM du polish pour la même candidature ;
    sinon en génère un nouveau (déterministe, sans LLM, comme l'aperçu
    chat) - jamais de LLM appelé implicitement ici sans que l'appelant
    l'ait demandé."""
    text = offer_text(offre)
    try:
        if cv is None:
            cv = writer.draft_cv(text)
        if lettre is None:
            lettre = writer.draft_cover_letter(text)
    except LLMError as exc:
        raise ApplicationFolderError(f"LLM indisponible : {exc}") from exc

    company, titre = _offer_company_and_title(offre)
    folder = _offer_folder(company, titre)
    try:
        folder.mkdir(parents=True, exist_ok=True)

        # `text` (= `offer_text(offre)`) contient déjà titre/entreprise/
        # lieu/description en tête : pas de ré-en-tête ici, ça ne ferait
        # que dupliquer les deux premières lignes.
        (folder / "description.md").write_text(f"{text}\n", encoding="utf-8")

        header_lines = writer.contact_header().split("\n")
        (folder / "CV.docx").write_bytes(
            cv_to_docx_bytes(cv, header_lines=header_lines)
        )
        (folder / "CV.pdf").write_bytes(
            cv_to_pdf_bytes(cv, header_lines=header_lines)
        )
        (folder / "Lettre_de_motivation.docx").write_bytes(
            cover_letter_to_docx_bytes(lettre)
        )
        (folder / "Lettre_de_motivation.pdf").write_bytes(
            cover_letter_to_pdf_bytes(lettre)
        )
    except OSError as exc:
        raise ApplicationFolderError(
            f"Écriture du dossier impossible : {exc}"
        ) from exc

    return folder

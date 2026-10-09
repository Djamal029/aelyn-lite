"""Rendu PDF du CV et de la lettre de motivation.

`application_writer.format_cv_text` ne produit que du texte brut, pour
l'affichage en chat. Ce module construit un vrai PDF à partir des mêmes
données (`CVContent`) et du même texte de lettre, pour la pièce jointe
envoyée par `POST /career/{id}/apply-by-mail` (aelyn-api).
"""

from __future__ import annotations

import io

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from aelyn_career.models import CVContent

_ACCENT = HexColor("#1F4E79")
_MUTED = HexColor("#555555")


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "name": ParagraphStyle("name", parent=base["Title"], fontSize=20, textColor=_ACCENT, alignment=TA_LEFT, spaceAfter=2),
        "contact": ParagraphStyle("contact", parent=base["Normal"], fontSize=9, textColor=_MUTED, spaceAfter=10),
        "section": ParagraphStyle("section", parent=base["Heading2"], fontSize=12, textColor=_ACCENT, spaceBefore=12, spaceAfter=4),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=9.5, leading=13),
        "entry_title": ParagraphStyle("entry_title", parent=base["Normal"], fontSize=10, leading=13, spaceBefore=6),
        "bullet": ParagraphStyle("bullet", parent=base["Normal"], fontSize=9.5, leading=13),
        "letter_body": ParagraphStyle("letter_body", parent=base["Normal"], fontSize=10.5, leading=15, spaceAfter=10),
    }


def cv_to_pdf_bytes(cv: CVContent, *, header_lines: list[str]) -> bytes:
    """Rend un `CVContent` en PDF une page (A4), même contenu que
    `format_cv_text` mais mis en page. `header_lines` : nom/ville/
    téléphone/email/LinkedIn déjà assemblés par l'appelant (cf.
    `ApplicationWriter.contact_header`, jamais régénérés ici)."""
    s = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=16 * mm, bottomMargin=16 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )
    story: list = []
    if header_lines:
        story.append(Paragraph(header_lines[0], s["name"]))
        if len(header_lines) > 1:
            story.append(Paragraph(" · ".join(header_lines[1:]), s["contact"]))

    story.append(Paragraph("Profil", s["section"]))
    story.append(HRFlowable(width="100%", color=_ACCENT, thickness=1))
    story.append(Paragraph(cv.profil, s["body"]))

    story.append(Paragraph("Expériences", s["section"]))
    story.append(HRFlowable(width="100%", color=_ACCENT, thickness=1))
    for e in cv.experiences:
        story.append(Paragraph(f"<b>{e.role}</b> · {e.entreprise} &mdash; {e.periode}".replace("&mdash;", "/"), s["entry_title"]))
        story.append(ListFlowable(
            [ListItem(Paragraph(p, s["bullet"]), leftIndent=10) for p in e.puces],
            bulletType="bullet", start="circle", leftIndent=12,
        ))

    if cv.projets:
        story.append(Paragraph("Projets", s["section"]))
        story.append(HRFlowable(width="100%", color=_ACCENT, thickness=1))
        for p in cv.projets:
            story.append(Paragraph(f"<b>{p.titre}</b> : {p.description}", s["body"]))

    story.append(Paragraph("Compétences", s["section"]))
    story.append(HRFlowable(width="100%", color=_ACCENT, thickness=1))
    for categorie, items in cv.competences.items():
        story.append(Paragraph(f"<b>{categorie} :</b> {', '.join(items)}", s["body"]))

    story.append(Paragraph("Formation", s["section"]))
    story.append(HRFlowable(width="100%", color=_ACCENT, thickness=1))
    for f in cv.formation:
        story.append(Paragraph(f, s["body"]))

    if cv.certifications:
        story.append(Paragraph("Certifications", s["section"]))
        story.append(HRFlowable(width="100%", color=_ACCENT, thickness=1))
        for c in cv.certifications:
            story.append(Paragraph(c, s["body"]))

    if cv.langues:
        story.append(Paragraph("Langues", s["section"]))
        story.append(HRFlowable(width="100%", color=_ACCENT, thickness=1))
        story.append(Paragraph(" · ".join(cv.langues), s["body"]))

    if cv.centres_interet:
        story.append(Paragraph("Centres d'intérêt", s["section"]))
        story.append(HRFlowable(width="100%", color=_ACCENT, thickness=1))
        story.append(Paragraph(" · ".join(cv.centres_interet), s["body"]))

    doc.build(story)
    return buf.getvalue()


def cover_letter_to_pdf_bytes(text: str) -> bytes:
    """Rend une lettre de motivation (texte brut, paragraphes séparés par
    des lignes vides) en PDF A4 simple."""
    s = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=22 * mm, bottomMargin=22 * mm, leftMargin=24 * mm, rightMargin=24 * mm,
    )
    story: list = [Spacer(1, 0)]
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        html_block = block.replace("\n", "<br/>")
        story.append(Paragraph(html_block, s["letter_body"]))
    doc.build(story)
    return buf.getvalue()

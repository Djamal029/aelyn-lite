"""Rendu PDF du CV et de la lettre de motivation.

`application_writer.format_cv_text` ne produit que du texte brut, pour
l'affichage en chat. Ce module construit un vrai PDF à partir des mêmes
données (`CVContent`) et du même texte de lettre, pour la pièce jointe
envoyée par `POST /career/{id}/apply-by-mail` (aelyn-api). Même style que
le template CV de référence de l'utilisateur : accent teal, police
Calibri, en-tête centré, titres de section soulignés.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Table, TableStyle

from aelyn_career.models import CVContent

_ACCENT = HexColor("#00868C")
_MUTED = HexColor("#595959")
_INK = HexColor("#1A1A1A")

# Même police que le template de référence (Calibri) quand le fichier
# système est disponible (présent par défaut sur Windows/Office) ; repli
# silencieux sur Helvetica (toujours livré avec reportlab) sinon, plutôt
# que de planter l'export PDF pour une question de police.
_FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
try:
    pdfmetrics.registerFont(TTFont("Calibri", str(_FONT_DIR / "calibri.ttf")))
    pdfmetrics.registerFont(TTFont("Calibri-Bold", str(_FONT_DIR / "calibrib.ttf")))
    pdfmetrics.registerFont(TTFont("Calibri-Italic", str(_FONT_DIR / "calibrii.ttf")))
    _FONT, _FONT_BOLD, _FONT_ITALIC = "Calibri", "Calibri-Bold", "Calibri-Italic"
except Exception:
    _FONT, _FONT_BOLD, _FONT_ITALIC = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


def _styles() -> dict:
    return {
        "name": ParagraphStyle(
            "name", fontName=_FONT_BOLD, fontSize=19, textColor=_ACCENT,
            alignment=TA_CENTER, spaceAfter=2, leading=22,
        ),
        "title": ParagraphStyle(
            "title", fontName=_FONT, fontSize=10, textColor=_ACCENT,
            alignment=TA_CENTER, spaceAfter=3,
        ),
        "contact": ParagraphStyle(
            "contact", fontName=_FONT, fontSize=8.3, textColor=_MUTED,
            alignment=TA_CENTER, spaceAfter=1,
        ),
        "links": ParagraphStyle(
            "links", fontName=_FONT, fontSize=8.3, textColor=_MUTED,
            alignment=TA_CENTER, spaceAfter=6,
        ),
        "section": ParagraphStyle(
            "section", fontName=_FONT_BOLD, fontSize=10.3, textColor=_ACCENT,
            spaceBefore=8, spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "body", fontName=_FONT, fontSize=8.6, leading=11,
            textColor=_INK, spaceAfter=2,
        ),
        "entry": ParagraphStyle(
            "entry", fontName=_FONT_BOLD, fontSize=8.8, leading=11, textColor=_INK,
        ),
        "date": ParagraphStyle(
            "date", fontName=_FONT_ITALIC, fontSize=7.8,
            textColor=_MUTED, alignment=TA_LEFT,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontName=_FONT, fontSize=8.3, leading=10.6, textColor=_INK,
            spaceAfter=2, leftIndent=12, firstLineIndent=-12, bulletIndent=0,
        ),
        "letter_body": ParagraphStyle(
            "letter_body", fontName=_FONT, fontSize=10.5, leading=15,
            spaceAfter=10, textColor=_INK,
        ),
    }


def _rule() -> HRFlowable:
    return HRFlowable(width="100%", color=_ACCENT, thickness=0.8, spaceAfter=3)


def _section(title: str, s: dict) -> list:
    return [Paragraph(title.upper(), s["section"]), _rule()]


def _entry_row(title_line: str, dates: str, s: dict) -> Table:
    t = Table(
        [[Paragraph(title_line, s["entry"]), Paragraph(dates, s["date"])]],
        colWidths=[130 * mm, 40 * mm],
    )
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _bullets(items: list[str], s: dict) -> list[Paragraph]:
    # Puce littérale en tête de texte (retrait en crochet via
    # leftIndent/firstLineIndent) plutôt que ListFlowable/ListItem : ce
    # dernier produisait par moments une puce isolée seule sur sa ligne,
    # suivie du texte à la ligne d'en dessous (bug visuel réel observé,
    # dépendant de la hauteur du bloc précédent). Un Paragraph unique par
    # puce est beaucoup plus prévisible.
    return [Paragraph(f"•  {item}", s["bullet"]) for item in items]


def cv_to_pdf_bytes(cv: CVContent, *, header_lines: list[str]) -> bytes:
    """Rend un `CVContent` en PDF une page (A4), style du template de
    référence (teal, Calibri, en-tête centré). `header_lines` :
    nom/ville/téléphone/email/LinkedIn déjà assemblés par l'appelant (cf.
    `ApplicationWriter.contact_header`, jamais régénérés ici)."""
    s = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=12 * mm, bottomMargin=12 * mm,
        leftMargin=16 * mm, rightMargin=16 * mm,
    )
    story: list = []
    if header_lines:
        story.append(Paragraph(header_lines[0], s["name"]))
        if len(header_lines) > 1:
            story.append(Paragraph(" · ".join(header_lines[1:]), s["contact"]))
        story.append(HRFlowable(
            width="100%", color=_ACCENT, thickness=1, spaceBefore=4, spaceAfter=10,
        ))

    story.append(Paragraph("Profil", s["section"]))
    story.append(_rule())
    story.append(Paragraph(cv.profil, s["body"]))

    story += _section("Expériences", s)
    for e in cv.experiences:
        story.append(_entry_row(f"{e.role} · {e.entreprise}", e.periode, s))
        story.extend(_bullets(e.puces, s))

    if cv.projets:
        story += _section("Projets", s)
        for p in cv.projets:
            story.append(Paragraph(f"<b>{p.titre}</b> : {p.description}", s["body"]))

    story += _section("Compétences", s)
    for categorie, items in cv.competences.items():
        story.append(Paragraph(f"<b>{categorie} :</b> {', '.join(items)}", s["body"]))

    story += _section("Formation", s)
    for f in cv.formation:
        story.append(Paragraph(f, s["body"]))

    if cv.certifications:
        story += _section("Certifications", s)
        for c in cv.certifications:
            story.append(Paragraph(c, s["body"]))

    if cv.langues:
        story += _section("Langues", s)
        story.append(Paragraph(" · ".join(cv.langues), s["body"]))

    if cv.centres_interet:
        story += _section("Centres d'intérêt", s)
        story.append(Paragraph(" · ".join(cv.centres_interet), s["body"]))

    doc.build(story)
    return buf.getvalue()


def cover_letter_to_pdf_bytes(text: str) -> bytes:
    """Rend une lettre de motivation (texte brut, paragraphes séparés par
    des lignes vides) en PDF A4, même police que le CV. `text` contient
    déjà l'en-tête (nom/coordonnées de l'expéditeur, cf.
    `ApplicationWriter.contact_header`) en premier bloc, convention
    standard d'une lettre de motivation française : pas d'en-tête stylé
    séparé ici, ça dupliquerait l'information."""
    s = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm,
        leftMargin=24 * mm, rightMargin=24 * mm,
    )
    story: list = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        html_block = block.replace("\n", "<br/>")
        story.append(Paragraph(html_block, s["letter_body"]))
    doc.build(story)
    return buf.getvalue()

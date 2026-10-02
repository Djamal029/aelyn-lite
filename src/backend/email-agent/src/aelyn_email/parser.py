"""Décodage MIME.

Tout ce qui peut mal tourner dans un mail réel est traité ici :
en-têtes encodés en plusieurs fragments, charsets exotiques, HTML seul,
pièces jointes, corps vide.
"""

from __future__ import annotations

import re
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime

from aelyn_email.models import Mail

_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_RE = re.compile(r"\n{3,}")


def decode_mime_header(raw: str | None) -> str:
    """Un en-tête peut mélanger plusieurs encodages : =?utf-8?...?= =?iso-8859-1?...?=

    `decode_header(...)[0]` ne récupère que le premier fragment et tronque
    silencieusement le reste. `make_header` recolle l'ensemble.
    """
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except (UnicodeDecodeError, LookupError, ValueError):
        return raw


def _decode_payload(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _is_attachment(part: Message) -> bool:
    disposition = str(part.get("Content-Disposition", "")).lower()
    return "attachment" in disposition


def _html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>|</p>", "\n", text)
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return _BLANK_RE.sub("\n\n", text).strip()


def extract_body(msg: Message) -> str:
    """text/plain en priorité, puis repli sur text/html aplati."""
    if not msg.is_multipart():
        body = _decode_payload(msg)
        if msg.get_content_type() == "text/html":
            return _html_to_text(body)
        return body.strip()

    html_fallback = ""
    for part in msg.walk():
        if part.is_multipart() or _is_attachment(part):
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain":
            body = _decode_payload(part).strip()
            if body:
                return body
        elif content_type == "text/html" and not html_fallback:
            html_fallback = _decode_payload(part)

    return _html_to_text(html_fallback) if html_fallback else ""


def has_attachments(msg: Message) -> bool:
    return any(_is_attachment(part) for part in msg.walk())


def parse_mail(uid: str, msg: Message) -> Mail:
    raw_from = decode_mime_header(msg.get("From"))
    display_name, address = parseaddr(raw_from)

    try:
        date = parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None
    except (TypeError, ValueError):
        date = None

    return Mail(
        uid=uid,
        sender=display_name or address or "inconnu",
        sender_email=address,
        subject=decode_mime_header(msg.get("Subject")) or "(sans objet)",
        date=date,
        body=extract_body(msg),
        has_attachments=has_attachments(msg),
    )
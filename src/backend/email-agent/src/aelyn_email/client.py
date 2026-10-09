"""Accès IMAP / SMTP.

Deux principes :

1. On travaille par UID, jamais par numéro de séquence. Les numéros de
   séquence se décalent dès qu'un mail est supprimé d'une autre session.

2. On lit avec BODY.PEEK[] et non RFC822 : RFC822 positionne le flag
   \\Seen, donc un simple triage marquerait tous mes mails comme lus.
"""

from __future__ import annotations

import email
import imaplib
import logging
import smtplib
from contextlib import contextmanager
from email.message import EmailMessage
from typing import Iterator

from aelyn.core.config import settings
from aelyn_email.models import Mail
from aelyn_email.parser import parse_mail

logger = logging.getLogger(__name__)


class MailboxError(RuntimeError):
    pass


@contextmanager
def imap_session(mailbox: str = "INBOX") -> Iterator[imaplib.IMAP4_SSL]:
    """Connexion IMAP à durée de vie explicite.

    Une connexion IMAP expire côté serveur : on ne la garde pas dans un
    singleton, on l'ouvre pour la durée d'une opération.
    """
    try:
        conn = imaplib.IMAP4_SSL(settings.imap_server, settings.imap_port)
    except OSError as exc:
        raise MailboxError(f"Connexion IMAP impossible : {exc}") from exc

    try:
        conn.login(settings.email_user, settings.email_pass)
        status, _ = conn.select(mailbox)
        if status != "OK":
            raise MailboxError(f"Boîte introuvable : {mailbox}")
        yield conn
    except imaplib.IMAP4.error as exc:
        raise MailboxError(f"Erreur IMAP : {exc}") from exc
    finally:
        try:
            conn.close()
        except (imaplib.IMAP4.error, OSError):
            pass
        try:
            conn.logout()
        except (imaplib.IMAP4.error, OSError):
            pass


def list_unread(limit: int | None = None) -> list[Mail]:
    """Les `limit` mails non lus les plus récents, sans les marquer comme lus."""
    limit = limit or settings.max_mails_per_run
    mails: list[Mail] = []

    with imap_session() as conn:
        status, data = conn.uid("SEARCH", None, "UNSEEN")
        if status != "OK" or not data or not data[0]:
            return []

        # Les plus récents sont en fin de liste.
        uids = data[0].split()[-limit:]

        for raw_uid in uids:
            uid = raw_uid.decode()
            status, payload = conn.uid("FETCH", uid, "(BODY.PEEK[])")
            if status != "OK" or not payload:
                logger.warning("Impossible de récupérer le mail %s", uid)
                continue

            for part in payload:
                if not isinstance(part, tuple):
                    continue
                try:
                    msg = email.message_from_bytes(part[1])
                    mails.append(parse_mail(uid, msg))
                except Exception:  # un mail malformé ne doit pas tuer le run
                    logger.exception("Mail %s illisible, ignoré", uid)
                break

    return mails


def mark_seen(uid: str) -> None:
    with imap_session() as conn:
        conn.uid("STORE", uid, "+FLAGS", "(\\Seen)")


def archive(uid: str, folder: str = "Archive") -> None:
    with imap_session() as conn:
        conn.uid("COPY", uid, folder)
        conn.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
        conn.expunge()


def send_reply(*, to: str, subject: str, body: str, in_reply_to: str | None = None) -> None:
    msg = EmailMessage()
    msg["From"] = settings.email_user
    msg["To"] = to
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.email_user, settings.email_pass)
        server.send_message(msg)


def send_mail_with_attachments(
    *, to: str, subject: str, body: str, attachments: list[tuple[str, bytes, str]]
) -> None:
    """Envoie un nouveau mail (pas une réponse à un fil existant, donc pas
    de `In-Reply-To`/préfixe `Re:` comme `send_reply`) avec des pièces
    jointes. `attachments` : liste de `(nom_fichier, contenu, sous_type)`,
    ex. `("CV.pdf", pdf_bytes, "pdf")` ; `maintype` toujours `application`,
    seul cas d'usage actuel (CV/LM en PDF, cf. career.py)."""
    msg = EmailMessage()
    msg["From"] = settings.email_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    for filename, content, subtype in attachments:
        msg.add_attachment(content, maintype="application", subtype=subtype, filename=filename)

    with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.email_user, settings.email_pass)
        server.send_message(msg)
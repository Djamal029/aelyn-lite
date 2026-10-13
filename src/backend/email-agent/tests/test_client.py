from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from aelyn.core.config import settings
from aelyn_email.client import (
    MailboxError,
    imap_session,
    list_recent_or_flagged,
    list_unread,
    search_mails,
    send_mail_with_attachments,
    send_reply,
)


def test_send_reply_fails_clearly_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "email_user", None)
    monkeypatch.setattr(settings, "email_pass", None)

    with pytest.raises(MailboxError, match="non configurée"):
        send_reply(to="a@b.com", subject="Sujet", body="Corps")


def test_send_mail_with_attachments_fails_clearly_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "email_user", None)
    monkeypatch.setattr(settings, "email_pass", "something")

    with pytest.raises(MailboxError, match="non configurée"):
        send_mail_with_attachments(
            to="a@b.com", subject="Sujet", body="Corps", attachments=[]
        )


def test_imap_session_fails_clearly_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "email_user", "a@b.com")
    monkeypatch.setattr(settings, "email_pass", None)

    with pytest.raises(MailboxError, match="non configurée"):
        with imap_session():
            pass


def _fake_conn(search_result: bytes = b""):
    """`imap_session()` renvoie une connexion mock dont `uid("SEARCH", ...)`
    renvoie `search_result` (liste de UID séparés par espace) et dont
    `uid("FETCH", ...)` échoue proprement (pas de mail réel à parser,
    hors sujet pour ces tests) : on vérifie seulement le critère IMAP
    envoyé et l'absence d'écriture (`STORE`), jamais le parsing."""
    conn = MagicMock()

    def fake_uid(command, *args):
        if command == "SEARCH":
            return "OK", [search_result]
        if command == "FETCH":
            return "NO", None
        return "OK", []

    conn.uid.side_effect = fake_uid
    return conn


def test_search_mails_never_marks_seen(monkeypatch):
    """`search_mails` (et donc `list_unread`/`list_recent_or_flagged`) ne
    doit jamais écrire `\\Seen` : c'est `BODY.PEEK[]` qui garantit ça
    (cf. docstring du module), une régression ici marquerait tous les
    mails lus par un simple appel de lecture."""
    conn = _fake_conn(b"101 102")

    @contextmanager
    def fake_session(mailbox="INBOX"):
        yield conn

    monkeypatch.setattr("aelyn_email.client.imap_session", fake_session)
    search_mails("UNSEEN")

    store_calls = [c for c in conn.uid.call_args_list if c.args[0] == "STORE"]
    assert store_calls == []


def test_list_unread_searches_unseen_only(monkeypatch):
    conn = _fake_conn(b"")

    @contextmanager
    def fake_session(mailbox="INBOX"):
        yield conn

    monkeypatch.setattr("aelyn_email.client.imap_session", fake_session)
    list_unread()

    search_call = next(c for c in conn.uid.call_args_list if c.args[0] == "SEARCH")
    assert search_call.args == ("SEARCH", None, "UNSEEN")


def test_list_recent_or_flagged_combines_since_and_flagged(monkeypatch):
    """Doit couvrir a la fois "deja lu mais recent" (SINCE, sans filtre
    \\Seen) et "marque important" (FLAGGED, quel que soit l'age) - les
    deux cas que `list_unread` seul ne peut pas voir."""
    conn = _fake_conn(b"")

    @contextmanager
    def fake_session(mailbox="INBOX"):
        yield conn

    monkeypatch.setattr("aelyn_email.client.imap_session", fake_session)
    list_recent_or_flagged(days=7)

    search_call = next(c for c in conn.uid.call_args_list if c.args[0] == "SEARCH")
    criteria = search_call.args[2]
    assert criteria.startswith("(OR (SINCE ")
    assert criteria.endswith(") FLAGGED)")

import pytest

from aelyn.core.config import settings
from aelyn_email.client import (
    MailboxError,
    imap_session,
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

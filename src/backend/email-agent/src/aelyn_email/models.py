"""Modèles du domaine "mail".

Frontière nette : le protocole IMAP s'arrête ici. Au-delà, plus personne
ne manipule de `email.message.Message` ni de bytes.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

_NO_REPLY_RE = re.compile(
    r"no.?reply|do.?not.?reply|notifications?[-.]|^alert(s|es)?[-.@]",
    re.IGNORECASE,
)


class Mail(BaseModel):
    """Un mail nettoyé, prêt à être lu par un humain ou un LLM."""

    uid: str
    sender: str
    sender_email: str
    subject: str
    date: datetime | None = None
    body: str
    has_attachments: bool = False

    @property
    def is_no_reply(self) -> bool:
        """Adresse d'envoi automatisée : personne ne lira une réponse.

        Un petit modèle suit cette règle de façon inconstante quand elle
        n'est qu'écrite dans le prompt (cf. LinkedIn qui reste classé
        `repondre` malgré la consigne) : on la fait respecter ici, dans
        le code, plutôt que d'espérer que le LLM s'y tienne à chaque fois.
        """
        return bool(_NO_REPLY_RE.search(self.sender_email))

    def for_llm(self, max_chars: int = 2000) -> str:
        """Représentation compacte envoyée au modèle.

        On tronque : un petit modèle noie son jugement dans une signature
        de 40 lignes et un disclaimer juridique.
        """
        body = self.body.strip()
        if len(body) > max_chars:
            body = body[:max_chars] + "\n[…tronqué]"
        return (
            f"De : {self.sender} <{self.sender_email}>\n"
            f"Objet : {self.subject}\n"
            f"Pièces jointes : {'oui' if self.has_attachments else 'non'}\n"
            f"---\n{body}"
        )


class Category(StrEnum):
    CANDIDATURE = "candidature"
    ADMIN = "admin"
    ECOLE = "ecole"
    PERSO = "perso"
    NEWSLETTER = "newsletter"
    SPAM = "spam"
    AUTRE = "autre"


class ProposedAction(StrEnum):
    REPONDRE = "repondre"
    ARCHIVER = "archiver"
    LIRE_PLUS_TARD = "lire_plus_tard"
    IGNORER = "ignorer"
    SIGNALER = "signaler"


class Triage(BaseModel):
    """Ce que le LLM doit produire pour UN mail. Rien de plus."""

    categorie: Category
    urgence: int = Field(ge=1, le=5, description="1 = aucune, 5 = à traiter maintenant")
    resume: str = Field(max_length=200, description="Une phrase, en français")
    action_proposee: ProposedAction
    justification: str = Field(max_length=200)
    brouillon_reponse: str | None = Field(
        default=None,
        description="Rempli uniquement si action_proposee == 'repondre'",
    )
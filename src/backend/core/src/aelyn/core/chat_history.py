"""Historique de conversation persistant d'AELYN.

`ConversationalAgent._conversation_history` (cf. aelyn_conversation.agent)
reste en mémoire, bornée, pour NOURRIR le prompt du tour suivant (contexte
court terme) ; elle disparaît au redémarrage du process. Ce module est
la mémoire LONG terme correspondante : chaque tour "conversation libre"
est aussi écrit ici, dans SQLite, pour que :

- `aelyn-api` puisse exposer GET /chat/history (le futur frontend web n'a
  pas de process AELYN à interroger en mémoire, seulement l'API) ;
- l'historique survive à un redémarrage du chat CLI ou de l'API.

Même moteur que `journal.py` (SQLAlchemy + SQLite, un fichier sous
`settings.data_dir`), pas de nouvelle dépendance : même pattern déjà
éprouvé dans ce projet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Index, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class ChatMessageRow(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("idx_chat_messages_ts", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)


@dataclass(slots=True, frozen=True)
class ChatMessage:
    id: int
    ts: datetime
    role: str
    content: str


class ChatHistory:
    def __init__(self, path: Path) -> None:
        self._engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(self._engine)

    def append(self, role: str, content: str) -> int:
        """Enregistre un tour ("user" ou "assistant"). Ne lève jamais pour
        un contenu vide : appelé après coup, une erreur ici ne doit
        jamais faire échouer la conversation elle-même."""
        with Session(self._engine) as session:
            row = ChatMessageRow(
                ts=datetime.now(timezone.utc).isoformat(),
                role=role,
                content=content,
            )
            session.add(row)
            session.commit()
            return row.id

    def recent(self, limit: int = 50, before_id: int | None = None) -> list[ChatMessage]:
        """Les `limit` derniers tours, dans l'ordre chronologique (le plus
        ancien d'abord), l'ordre naturel de lecture d'une conversation.

        `before_id` : ne renvoie que les tours antérieurs à cet id, pour
        charger la suite plus ancienne d'un historique déjà partiellement
        affiché (sans lui, impossible de remonter au-delà des `limit`
        tours les plus récents : exactement le bug "l'historique ne
        fonctionne pas bien" remonté par l'utilisateur, une conversation
        active dépasse vite 50 tours)."""
        with Session(self._engine) as session:
            stmt = select(ChatMessageRow).order_by(ChatMessageRow.id.desc())
            if before_id is not None:
                stmt = stmt.where(ChatMessageRow.id < before_id)
            stmt = stmt.limit(limit)
            rows = session.scalars(stmt).all()
            return [_to_message(r) for r in reversed(rows)]

    def clear(self) -> None:
        with Session(self._engine) as session:
            session.query(ChatMessageRow).delete()
            session.commit()


def _to_message(row: ChatMessageRow) -> ChatMessage:
    return ChatMessage(
        id=row.id,
        ts=datetime.fromisoformat(row.ts),
        role=row.role,
        content=row.content,
    )

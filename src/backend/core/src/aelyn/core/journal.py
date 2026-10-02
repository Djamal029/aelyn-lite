"""Journal d'actions d'AELYN.

C'est LA pièce qui permet de répondre à "qu'est-ce que tu as fait ?".
Le LLM ne se souvient de rien : il lit cette table et la reformule.

Cycle de vie d'une action :
    PROPOSED  -> l'agent suggère quelque chose, rien n'est fait
    EXECUTED  -> l'action a réellement eu lieu
    REJECTED  -> l'utilisateur a refusé
    FAILED    -> tentative d'exécution en erreur
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from sqlalchemy import Index, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    EXECUTED = "executed"
    REJECTED = "rejected"
    FAILED = "failed"


class Base(DeclarativeBase):
    pass


class ActionRow(Base):
    __tablename__ = "actions"
    __table_args__ = (
        Index("idx_actions_ts", "ts"),
        Index("idx_actions_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[str] = mapped_column(String, nullable=False)
    agent: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    target: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)


@dataclass(slots=True, frozen=True)
class Action:
    id: int
    ts: datetime
    agent: str
    action: str
    target: str | None
    summary: str
    status: ActionStatus
    payload: dict[str, Any]

    def to_line(self) -> str:
        """Ligne compacte, lisible par un LLM comme par un humain."""
        moment = self.ts.astimezone().strftime("%d/%m %H:%M")
        cible = f" [{self.target}]" if self.target else ""
        return f"{moment} | {self.status.value:<8} | {self.action}{cible} : {self.summary}"


class Journal:
    def __init__(self, path: Path) -> None:
        self._engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(self._engine)

    # ------------------------------------------------------------------ write

    def record(
        self,
        *,
        agent: str,
        action: str,
        summary: str,
        status: ActionStatus,
        target: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        with Session(self._engine) as session:
            row = ActionRow(
                ts=datetime.now(timezone.utc).isoformat(),
                agent=agent,
                action=action,
                target=target,
                summary=summary,
                status=status.value,
                payload=json.dumps(payload or {}, ensure_ascii=False),
            )
            session.add(row)
            session.commit()
            return row.id

    def update_status(self, action_id: int, status: ActionStatus) -> None:
        with Session(self._engine) as session:
            row = session.get(ActionRow, action_id)
            if row is not None:
                row.status = status.value
                session.commit()

    # ------------------------------------------------------------------- read

    def get(self, action_id: int) -> Action | None:
        with Session(self._engine) as session:
            row = session.get(ActionRow, action_id)
            return _to_action(row) if row else None

    def find(self, *, agent: str, action: str, target: str) -> Action | None:
        """La dernière action correspondante, ou `None`.

        Sert de cache : avant de retraiter quelque chose (ex. une offre
        déjà structurée par le career-agent), on regarde si une action
        avec ce `target` existe déjà.
        """
        with Session(self._engine) as session:
            stmt = (
                select(ActionRow)
                .where(
                    ActionRow.agent == agent,
                    ActionRow.action == action,
                    ActionRow.target == target,
                )
                .order_by(ActionRow.id.desc())
                .limit(1)
            )
            row = session.scalars(stmt).first()
            return _to_action(row) if row else None

    def pending(self, agent: str | None = None) -> list[Action]:
        """Les propositions en attente de validation."""
        with Session(self._engine) as session:
            stmt = select(ActionRow).where(ActionRow.status == ActionStatus.PROPOSED.value)
            if agent:
                stmt = stmt.where(ActionRow.agent == agent)
            stmt = stmt.order_by(ActionRow.id)
            rows = session.scalars(stmt).all()
            return [_to_action(r) for r in rows]

    def since(self, hours: int = 24, agent: str | None = None) -> list[Action]:
        """Historique récent : ce que lit le LLM pour son compte rendu."""
        floor = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with Session(self._engine) as session:
            stmt = select(ActionRow).where(ActionRow.ts >= floor)
            if agent:
                stmt = stmt.where(ActionRow.agent == agent)
            stmt = stmt.order_by(ActionRow.ts)
            rows = session.scalars(stmt).all()
            return [_to_action(r) for r in rows]


def _to_action(row: ActionRow) -> Action:
    return Action(
        id=row.id,
        ts=datetime.fromisoformat(row.ts),
        agent=row.agent,
        action=row.action,
        target=row.target,
        summary=row.summary,
        status=ActionStatus(row.status),
        payload=json.loads(row.payload or "{}"),
    )

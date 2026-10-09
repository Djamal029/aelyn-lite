"""Offres d'emploi déjà vues par la recherche proactive (career-agent).

Sans ça, une recherche proactive périodique (`aelyn_career.proactive_search`)
rejouerait les MÊMES offres à chaque cycle (France Travail ne garde pas la
trace de ce qu'AELYN a déjà montré) : cette table ne sert qu'à distinguer
"jamais vue" de "déjà signalée", pour ne journaliser que les vraies
nouveautés.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class SeenOfferRow(Base):
    __tablename__ = "seen_offers"

    offer_id: Mapped[str] = mapped_column(String, primary_key=True)
    first_seen_ts: Mapped[str] = mapped_column(String, nullable=False)


class SeenOffers:
    def __init__(self, path: Path) -> None:
        self._engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(self._engine)

    def filter_new(self, offer_ids: list[str]) -> list[str]:
        """Renvoie, dans l'ordre d'entrée, les ids de `offer_ids` jamais
        vus auparavant, et les marque IMMÉDIATEMENT comme vus : un appel
        suivant (même avant que l'appelant n'ait fini de traiter ce
        retour) ne les considérera plus comme nouveaux."""
        if not offer_ids:
            return []
        with Session(self._engine) as session:
            existing = set(
                session.scalars(
                    select(SeenOfferRow.offer_id).where(
                        SeenOfferRow.offer_id.in_(offer_ids)
                    )
                ).all()
            )
            # `dict.fromkeys` : dédoublonne un `offer_id` répété dans la
            # même liste d'entrée tout en gardant le premier ordre de
            # rencontre (un doublon inséré deux fois violerait la clé
            # primaire au commit).
            candidates = (oid for oid in offer_ids if oid not in existing)
            new_ids = list(dict.fromkeys(candidates))
            now = datetime.now(timezone.utc).isoformat()
            for oid in new_ids:
                session.add(SeenOfferRow(offer_id=oid, first_seen_ts=now))
            session.commit()
            return new_ids

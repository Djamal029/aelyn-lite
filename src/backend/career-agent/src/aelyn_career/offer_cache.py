"""Cache local des offres, par hash.

Trois choses qu'on ne veut jamais refaire/reperdre entre deux recherches :
    - repasser une offre au LLM pour la structurer (cf. `Journal` dans
      `llm_structurer.py`, qui l'utilise avec `hash_offer` ci-dessous) ;
    - recalculer son embedding (géré ici, `OfferCache.get_embedding` /
      `save_embedding`) ;
    - savoir qu'on l'a déjà montrée à l'utilisateur dans une recherche
      PASSÉE, pas seulement dédupliquée au sein du même appel (géré ici,
      `OfferCache.mark_seen`/`seen_hashes`) - sans ça, relancer la même
      recherche de mots-clés deux jours plus tard ressort les mêmes
      offres déjà vues comme si elles étaient neuves.

`hash_offer` est LA fonction utilisée partout pour identifier une offre :
mêmes caches, même clé, pour ne jamais les désynchroniser.
"""

from __future__ import annotations

import datetime
import hashlib
import os
from pathlib import Path

import numpy as np
from sqlalchemy import DateTime, Integer, LargeBinary, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


def hash_offer(offer_text: str) -> str:
    """Empreinte stable d'une offre (espaces/casse normalisés)."""
    normalise = " ".join(offer_text.split()).lower()
    return hashlib.sha256(normalise.encode("utf-8")).hexdigest()


def default_offer_cache_path() -> Path:
    """Même convention que `TextEmbbeder` (embbeder.py) : un seul fichier
    SQLite partagé pour tout ce qui concerne les offres (embeddings,
    historique "déjà vues"), jamais deux chemins qui pourraient diverger."""
    return Path(os.getenv("EMBEDDINGS_DIR", "career-agent/src/aelyn_career")) / "offers_cache.db"


class Base(DeclarativeBase):
    pass


class OfferEmbeddingRow(Base):
    __tablename__ = "offer_embeddings"

    hash: Mapped[str] = mapped_column(String, primary_key=True)
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dtype: Mapped[str] = mapped_column(String, nullable=False)
    shape: Mapped[str] = mapped_column(String, nullable=False)


class SeenOfferRow(Base):
    __tablename__ = "seen_offers"

    hash: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=True)
    company: Mapped[str] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=True)
    url: Mapped[str] = mapped_column(String, nullable=True)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)


class SearchLogRow(Base):
    __tablename__ = "search_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(String, nullable=True)
    contract_type: Mapped[str] = mapped_column(String, nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    new_count: Mapped[int] = mapped_column(Integer, nullable=False)
    searched_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)


class OfferCache:
    """Stocke/relit un embedding par hash d'offre, en SQLite (via SQLAlchemy)."""

    def __init__(self, path: str | Path) -> None:
        self._engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(self._engine)

    def get_embedding(self, offer_hash: str) -> np.ndarray | None:
        with Session(self._engine) as session:
            row = session.get(OfferEmbeddingRow, offer_hash)
            if row is None:
                return None
            shape = tuple(int(n) for n in row.shape.split(","))
            return np.frombuffer(row.embedding, dtype=row.dtype).reshape(shape)

    def save_embedding(self, offer_hash: str, embedding: np.ndarray) -> None:
        embedding = np.asarray(embedding)
        with Session(self._engine) as session:
            row = session.get(OfferEmbeddingRow, offer_hash)
            if row is None:
                row = OfferEmbeddingRow(hash=offer_hash)
                session.add(row)
            row.embedding = embedding.tobytes()
            row.dtype = str(embedding.dtype)
            row.shape = ",".join(str(n) for n in embedding.shape)
            session.commit()

    def seen_hashes(self) -> set[str]:
        """Tous les hashs déjà montrés à l'utilisateur, toutes recherches
        passées confondues (pas de fenêtre temporelle : une offre
        redéposée des mois plus tard garde le même hash, donc le même
        statut "déjà vue" - c'est délibéré, cf. `JobSearchService.search`,
        qui ne les exclut jamais, seulement les relègue en second plan)."""
        with Session(self._engine) as session:
            return set(session.scalars(select(SeenOfferRow.hash)))

    def mark_seen(self, offer_hash: str, *, title: str = "", company: str = "", source: str = "", url: str = "") -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        with Session(self._engine) as session:
            row = session.get(SeenOfferRow, offer_hash)
            if row is None:
                session.add(SeenOfferRow(
                    hash=offer_hash, title=title, company=company, source=source,
                    url=url, first_seen_at=now, last_seen_at=now,
                ))
            else:
                row.last_seen_at = now
            session.commit()

    def log_search(self, *, query: str | None, contract_type: str | None, result_count: int, new_count: int) -> None:
        with Session(self._engine) as session:
            session.add(SearchLogRow(
                query=query, contract_type=contract_type, result_count=result_count,
                new_count=new_count, searched_at=datetime.datetime.now(datetime.timezone.utc),
            ))
            session.commit()

    def recent_searches(self, limit: int = 10) -> list[SearchLogRow]:
        with Session(self._engine) as session:
            stmt = select(SearchLogRow).order_by(SearchLogRow.searched_at.desc()).limit(limit)
            return list(session.scalars(stmt))

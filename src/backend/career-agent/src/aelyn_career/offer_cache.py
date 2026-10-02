"""Cache local des offres, par hash.

Deux choses coûteuses qu'on ne veut jamais refaire pour la même offre :
    - la repasser au LLM pour la structurer (cf. `Journal` dans
      `llm_structurer.py`, qui l'utilise avec `hash_offer` ci-dessous) ;
    - recalculer son embedding (géré ici, `OfferCache.get_embedding` /
      `save_embedding`).

`hash_offer` est LA fonction utilisée partout pour identifier une offre :
mêmes deux caches, même clé, pour ne jamais désynchroniser les deux.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from sqlalchemy import LargeBinary, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


def hash_offer(offer_text: str) -> str:
    """Empreinte stable d'une offre (espaces/casse normalisés)."""
    normalise = " ".join(offer_text.split()).lower()
    return hashlib.sha256(normalise.encode("utf-8")).hexdigest()


class Base(DeclarativeBase):
    pass


class OfferEmbeddingRow(Base):
    __tablename__ = "offer_embeddings"

    hash: Mapped[str] = mapped_column(String, primary_key=True)
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dtype: Mapped[str] = mapped_column(String, nullable=False)
    shape: Mapped[str] = mapped_column(String, nullable=False)


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

from pathlib import Path

from sentence_transformers import SentenceTransformer, util
from rank_bm25 import BM25Okapi
import numpy as np
import os
import dotenv

from aelyn.core.config import settings
from aelyn_career.offer_cache import OfferCache, hash_offer

dotenv.load_dotenv()

_NIVEAU_ORDER = ["stage", "junior", "senior", "postdoc"]


def niveau_adequacy(niveau_requis: str, candidate_level: str | None = None) -> float:
    """Facteur multiplicatif dans [0, 1] qui pénalise un écart de niveau
    entre le candidat et l'offre ; jamais codé en dur sur "junior", calculé
    depuis l'écart entre `candidate_level` et `niveau_requis` dans
    `_NIVEAU_ORDER`, pour s'adapter à n'importe quel profil.

    `candidate_level=None` (cas normal, cf. `pipeline.py` qui n'en passe
    jamais) : lit `settings.candidate_level` à CHAQUE appel plutôt qu'un
    défaut figé à l'import (`PATCH /settings`, aelyn-api, doit pouvoir
    changer ce réglage sur le process déjà démarré ; un défaut de fonction
    aurait gardé l'ancienne valeur capturée au chargement du module).

    Une offre qui demande MOINS d'expérience que le candidat n'est jamais
    pénalisée (toujours obtenable techniquement) ; un écart vers le haut
    devient de plus en plus improbable, jusqu'à quasi exclu à partir de
    deux niveaux d'écart (ex. junior -> postdoc).
    """
    candidate_level = candidate_level or settings.candidate_level
    try:
        gap = _NIVEAU_ORDER.index(niveau_requis) - _NIVEAU_ORDER.index(candidate_level)
    except ValueError:
        return 1.0  # valeur de niveau inconnue : ne pas pénaliser à l'aveugle
    if gap <= 0:
        return 1.0
    if gap == 1:
        return 0.8
    if gap == 2:
        return 0.3
    return 0.1


class TextEmbbeder:

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._model = None

        return cls._instance

    def __init__(self):
        if self._model is not None:
            # Singleton déjà initialisé : ne pas recharger le modèle
            # d'embedding à chaque `TextEmbbeder()`, c'est coûteux.
            return

        self.embedding_model = SentenceTransformer(os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-m3"))
        self._model = self.embedding_model
        self.default_where_to_save = os.getenv("EMBEDDINGS_DIR", "career-agent/src/aelyn_career")
        self._offer_cache = OfferCache(Path(self.default_where_to_save) / "offers_cache.db")

    def encode_text(self, text, where_to_save=None):
        if where_to_save:
            self.default_where_to_save = where_to_save

        embeddings = self.embedding_model.encode(text)
        np.save(os.path.join(self.default_where_to_save, "profile_embeddings.npy"), embeddings)
        return embeddings

    def encode_cached(self, text: str) -> np.ndarray:
        """Comme `encode_text`, mais mis en cache par hash (`offers_cache.db`) :
        un texte déjà vectorisé n'est jamais repassé dans le modèle."""
        text_hash = hash_offer(text)

        embedding = self._offer_cache.get_embedding(text_hash)
        if embedding is not None:
            return embedding

        embedding = self.embedding_model.encode(text)
        self._offer_cache.save_embedding(text_hash, embedding)
        return embedding

    def texts_scoring(self, chunks_text, offre_structuree):
        """Score les chunks du profil (cf. `ProfilManager.parse_profile`) par
        pertinence BM25 vis-à-vis des compétences requises par une offre.
        """
        if not isinstance(chunks_text, list):
            chunks_text = [chunks_text]

        # `chunk["text"]` est déjà le texte formaté (description + technologies
        # incluses) construit par ProfilManager.parse_profile ; pas besoin de
        # le reconstruire ici.
        tokenized_corpus = [chunk["text"].lower().split() for chunk in chunks_text]
        bm25 = BM25Okapi(tokenized_corpus)

        competences = offre_structuree["competences_requises"]  # texte ou liste de mots-clés
        if isinstance(competences, list):
            competences = " ".join(competences)
        tokenized_query = competences.lower().split()

        return bm25.get_scores(tokenized_query)

    def similarity(self, chunks_embeddings, offre_embedding):
        """Similarité cosinus entre chaque embedding de chunk et l'embedding
        de l'offre.

        Args:
            chunks_embeddings: un embedding par chunk (n_chunks, dim).
            offre_embedding: l'embedding de l'offre (dim,).
        """
        return util.cos_sim(chunks_embeddings, offre_embedding).squeeze(-1).numpy()

    @staticmethod
    def _squash_bm25(scores: np.ndarray, scale: float = 8.0) -> np.ndarray:
        """Ramène BM25 (non borné, peut dépasser 10-20 selon le corpus) sur
        une échelle FIXE [0, 1[ via `1 - exp(-score/scale)`, jamais un
        min-max PAR APPEL (bug réel corrigé ici) : un min-max par offre
        force TOUJOURS le meilleur chunk de CETTE offre à 1.0, même pour
        une offre hors-sujet dont le meilleur chunk n'a qu'un chevauchement
        lexical faible et accidentel — observé en direct, "hôtesse
        bilingue" ressortait avec un score élevé sur une recherche
        "intelligence artificielle" à cause de ça. Une échelle fixe laisse
        un score lexical réellement faible rester faible, quelle que soit
        la offre comparée. `scale` fixe le score BM25 qui vaut ~63% de 1.0,
        à ajuster seulement si les scores BM25 observés changent d'ordre
        de grandeur (ex. changement de corpus de chunks)."""
        return 1.0 - np.exp(-np.clip(scores, 0, None) / scale)

    def final_score(self, chunks_text, offre_structuree):
        """Score final par chunk : BM25 (correspondance lexicale) et
        similarité cosinus (embeddings), combinés par
        `settings.weight_score_txt_match`/`settings.weight_score_cos`
        (lus ici, PAS en constante de module, pour qu'un changement via
        `PATCH /settings` s'applique à la toute PROCHAINE recherche, sans
        redémarrage).

        Les deux signaux sont ramenés sur [0, 1] par une transformation À
        ÉCHELLE FIXE (jamais relative à l'offre en cours) : le cosinus est
        déjà borné ([-1, 1], donc un simple `(x+1)/2`), et BM25 passe par
        `_squash_bm25`. Un min-max PAR OFFRE (comme avant ce correctif)
        écraserait la différence entre une offre vraiment pertinente et
        une offre hors-sujet qui n'a, par hasard, qu'un très faible
        chevauchement lexical/sémantique : les deux remonteraient à des
        scores comparables, uniquement parce que chacune a "un meilleur
        chunk parmi les siens"."""
        if not isinstance(chunks_text, list):
            chunks_text = [chunks_text]

        word_match = self._squash_bm25(np.asarray(self.texts_scoring(chunks_text, offre_structuree)))

        competences = offre_structuree["competences_requises"]
        if isinstance(competences, list):
            competences = " ".join(competences)

        chunks_embeddings = np.array([self.encode_cached(chunk["text"]) for chunk in chunks_text])
        offre_embedding = self.encode_cached(competences)
        cos_sim_raw = self.similarity(chunks_embeddings, offre_embedding)
        cos_sim = (cos_sim_raw + 1.0) / 2.0

        return settings.weight_score_txt_match * word_match + settings.weight_score_cos * cos_sim

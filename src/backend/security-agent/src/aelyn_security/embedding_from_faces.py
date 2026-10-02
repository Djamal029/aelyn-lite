"""Embeddings faciaux (DeepFace / ArcFace) pour l'agent de sécurité d'AELYN.

Une photo de visage devient un vecteur normalisé ; plusieurs photos
d'une même personne sont agrégées par médiane en UN embedding de
référence, robuste aux variations d'éclairage ou de pose d'une photo
à l'autre.

Ce module ne fait QUE de la reconnaissance faciale (« qui est-ce ? »).
La détection de liveness (« est-ce un vrai visage ? ») est un problème
séparé, traité par `aelyn_security.anti_spoofing.detector` ; à
combiner avant de faire confiance à une identification : ne jamais
authentifier sur la seule ressemblance d'un embedding, une photo ou un
écran peut la produire aussi. (DeepFace propose aussi son propre
`anti_spoofing=True` intégré à `represent()`, si un jour on préfère
unifier les deux plutôt que garder le détecteur YOLO dédié.)

Note technique : le paquet `arcface` (PyPI) a été abandonné au profit
de DeepFace ; son modèle par défaut se télécharge depuis un serveur
d'une université qui ne répond plus (404), sans mirroir officiel.
DeepFace télécharge ses poids ArcFace depuis ses propres releases
GitHub, activement maintenues.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from deepface import DeepFace
from deepface.modules.exceptions import FaceNotDetected
from deepface.modules import verification

from aelyn.core.config import settings
from aelyn.core.journal import ActionStatus, Journal

logger = logging.getLogger(__name__)

AGENT_NAME = "security"
MODEL_NAME = "ArcFace"
DISTANCE_METRIC = "cosine"
# Le détecteur "opencv" par défaut de DeepFace dépend d'un fichier Haar
# cascade absent de certains builds récents d'opencv-python ; mtcnn
# n'a pas ce problème et est déjà une dépendance de DeepFace.
DETECTOR_BACKEND = "mtcnn"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


class FaceEmbeddings:
    def __init__(self, journal: Journal | None = None) -> None:
        self.journal = journal or Journal(settings.journal_path)

    def _embed(self, image: str | Path | np.ndarray) -> np.ndarray | None:
        """Embedding du premier visage détecté dans `image`, ou `None`."""
        try:
            faces = DeepFace.represent(
                img_path=str(image) if isinstance(image, Path) else image,
                model_name=MODEL_NAME,
                detector_backend=DETECTOR_BACKEND,
                enforce_detection=True,
            )
        except FaceNotDetected:
            return None
        return np.asarray(faces[0]["embedding"])

    # ------------------------------------------------------- enrôlement
    def detect_faces(self, img):
        raise NotImplementedError("TODO : détection de visage via YOLO")

    def create_embeddings(self, target_user_name: str) -> np.ndarray:
        """Calcule et enregistre l'embedding de référence d'un utilisateur.

        Toutes les photos exploitables de `faces_dir/<target_user_name>/`
        sont utilisées ; la médiane lisse les écarts d'une photo à l'autre.
        """
        user_dir = settings.faces_dir / target_user_name
        images = (
            sorted(p for p in user_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
            if user_dir.is_dir()
            else []
        )
        if not images:
            raise ValueError(f"Aucune photo trouvée dans {user_dir} pour « {target_user_name} »")

        embeddings = []
        for path in images:
            emb = self._embed(path)
            if emb is None:
                logger.warning("Aucun visage détecté dans %s, photo ignorée", path)
                continue
            embeddings.append(emb)

        if not embeddings:
            raise ValueError(f"Aucun visage détectable dans les {len(images)} photo(s) de {user_dir}")

        reference = np.median(np.asarray(embeddings), axis=0)
        np.save(settings.embeddings_dir / f"{target_user_name}.npy", reference)
        logger.info(
            "Embedding de référence créé pour %s (%d/%d photo(s) exploitée(s))",
            target_user_name,
            len(embeddings),
            len(images),
        )
        return reference

    def _known_embeddings(self) -> dict[str, np.ndarray]:
        """Charge tous les embeddings de référence déjà enregistrés."""
        return {path.stem: np.load(path) for path in settings.embeddings_dir.glob("*.npy")}

    # --------------------------------------------------- identification

    def compare_faces(self, face: str | Path | np.ndarray) -> str | None:
        """Nom de l'utilisateur enregistré le plus proche de `face`, ou `None`.

        `face` est un chemin d'image ou une image cv2. Ne dit rien sur
        la vivacité du visage (cf. docstring du module).
        """
        known = self._known_embeddings()
        if not known:
            return None

        candidate = self._embed(face)
        if candidate is None:
            return None

        distances = {
            name: verification.find_distance(candidate, emb, DISTANCE_METRIC) for name, emb in known.items()
        }
        best_name, best_distance = min(distances.items(), key=lambda item: item[1])

        return best_name if best_distance <= settings.face_match_threshold else None

    # ------------------------------------------------------------ journal

    def log_identification(self, user: str | None, source: str = "webcam") -> int:
        """Enregistre une identification dans le journal partagé d'AELYN."""
        summary = f"Visage reconnu depuis {source} : {user}" if user else f"Aucun visage reconnu depuis {source}"
        return self.journal.record(
            agent=AGENT_NAME,
            action="identifier",
            target=user,
            summary=summary,
            status=ActionStatus.EXECUTED,
            payload={"source": source},
        )

"""Expose les caméras locales (webcam PC, Iriun Webcam) à l'API.

Nommé `security` pour matcher la forme REST demandée (`GET
/security/cameras`), mais NE dépend PAS de `aelyn_security` (détection
anti-spoofing / reconnaissance faciale, un chantier séparé, pas encore
branché à l'API). Uniquement `aelyn_media.camera` : la même caméra
locale que celle ouverte depuis le chat ("montre la caméra de
l'entrée/du salon", cf. media-agent/src/aelyn_media/camera.py).

L'aperçu vidéo reste une fenêtre OpenCV LOCALE sur la machine qui
exécute l'API (cf. camera.py), PAS un flux vidéo streamé sur HTTP :
utile seulement quand l'API tourne sur la même machine que l'endroit où
on veut voir la fenêtre (le cas visé pour l'instant : test local). `POST
/security/cameras/{name}/preview` lance cette fenêtre en tâche de fond
et répond immédiatement (202) plutôt que de bloquer la requête HTTP
jusqu'à sa fermeture.
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from aelyn_media.camera import CAMERA_NAMES, camera_index, show_camera

router = APIRouter(prefix="/security/cameras", tags=["security"])


class CameraOut(BaseModel):
    name: str
    index: int
    configured: bool


def _camera_out(name: str) -> CameraOut:
    index = camera_index(name)
    return CameraOut(name=name, index=index if index is not None else -1, configured=index is not None)


@router.get("", response_model=list[CameraOut])
def list_cameras() -> list[CameraOut]:
    return [_camera_out(name) for name in CAMERA_NAMES]


@router.get("/{name}", response_model=CameraOut)
def get_camera(name: str) -> CameraOut:
    if name not in CAMERA_NAMES:
        raise HTTPException(404, f"Caméra inconnue : {name}")
    return _camera_out(name)


@router.post("/{name}/preview", status_code=202)
def preview_camera(name: str) -> dict:
    """Ouvre l'aperçu vidéo EN DIRECT dans une fenêtre locale (cf.
    docstring du module), ne renvoie pas le flux, seulement une
    confirmation que la fenêtre s'ouvre."""
    if name not in CAMERA_NAMES:
        raise HTTPException(404, f"Caméra inconnue : {name}")
    threading.Thread(target=show_camera, args=(name,), daemon=True).start()
    return {"status": "opening", "name": name}

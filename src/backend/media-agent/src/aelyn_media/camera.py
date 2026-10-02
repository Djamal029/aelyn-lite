"""Contrôle des caméras locales (webcam PC, Iriun Webcam) via OpenCV.

Pour l'instant, "Entrée" et "Salon"/"toute la pièce" sont TOUTES DEUX des
caméras vues comme de simples périphériques vidéo LOCAUX par ce PC (pas
des caméras IP séparées dans la maison) : "Entrée" = la webcam
intégrée/branchée au PC, "Salon" = un téléphone exposé comme webcam par
Iriun Webcam. OpenCV les distingue uniquement par un INDEX de
périphérique (`cv2.VideoCapture(index)`).

Ces index ne sont ni stables ni devinables sur Windows (l'ordre dépend
du matériel/des pilotes, pas du nom de l'appareil) : jamais codés en
dur ici, toujours lus depuis `settings.camera_*_index` (cf.
`core/src/aelyn/core/config.py`, remplis via CAMERA_ENTREE_INDEX/
CAMERA_SALON_INDEX dans .env), voir `scripts/list_cameras.py` pour les
identifier sur une machine donnée avant tout test réel.

Pas d'asyncio ici (contrairement à `agent.py`/`MediaController`) : la
capture OpenCV est déjà synchrone, un pont vers un event loop dédié
n'apporterait rien.
"""

from __future__ import annotations

import cv2

from aelyn.core.config import settings

WINDOW_TITLE_PREFIX = "AELYN - Camera"

# Noms exposés au routage d'intention (cf. aelyn_conversation.models.Intent
# .camera_name) -> index de périphérique local. Résolu à l'appel (pas une
# constante figée à l'import) pour toujours refléter `settings` actuel.
CAMERA_NAMES = ("entree", "salon")


def camera_index(name: str) -> int | None:
    """Résout un nom de caméra ("entree"/"salon") vers l'index OpenCV
    configuré, ou `None` si le nom n'est pas reconnu."""
    return {
        "entree": settings.camera_entree_index,
        "salon": settings.camera_salon_index,
    }.get(name)


def show_camera(name: str, *, window_name: str | None = None) -> int:
    """Ouvre un aperçu vidéo EN DIRECT et BLOQUANT de la caméra `name`.

    Se ferme sur 'q'/Échap ou sur la fermeture de la fenêtre. Bloquant
    par choix assumé : ceci est un aperçu de test local (voir docstring
    du module), pas une fonctionnalité de streaming en tâche de fond :
    un simple `cv2.imshow` en boucle est honnête et suffisant ici.

    Retourne 0 si l'aperçu a pu s'ouvrir et se fermer normalement, 1 si
    la caméra n'a pas pu être ouverte (mauvais index dans .env,
    périphérique déjà utilisé par une autre application, etc.) ou si le
    flux s'est interrompu en cours de route.
    """
    index = camera_index(name)
    if index is None:
        print(f"Caméra inconnue : {name}")
        return 1

    capture = cv2.VideoCapture(index)
    if not capture.isOpened():
        capture.release()
        print(
            f"Impossible d'ouvrir la caméra « {name} » (index {index}). "
            "Vérifie CAMERA_ENTREE_INDEX/CAMERA_SALON_INDEX dans .env, "
            "lance media-agent/scripts/list_cameras.py pour identifier "
            "le bon index sur cette machine."
        )
        return 1

    title = window_name or f"{WINDOW_TITLE_PREFIX} - {name}"
    code = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                print(f"Flux de la caméra « {name} » interrompu.")
                code = 1
                break

            cv2.imshow(title, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):  # 27 = Échap
                break
            # Fermeture via la croix de la fenêtre plutôt qu'une touche :
            # getWindowProperty retombe sous 1 dès que l'utilisateur ferme
            # la fenêtre, sans quoi la boucle continuerait indéfiniment
            # sur une fenêtre qui n'existe plus.
            try:
                if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
    finally:
        capture.release()
        cv2.destroyWindow(title)

    return code

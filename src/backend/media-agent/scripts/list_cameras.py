"""Aide manuelle : identifie quel index OpenCV correspond à quelle
caméra réelle (webcam intégrée du PC vs Iriun Webcam) sur CETTE machine.

Les index de périphérique vidéo sur Windows ne sont ni stables ni
devinables (ça dépend de l'ordre de connexion/des pilotes) : deviner au
hasard entre CAMERA_ENTREE_INDEX et CAMERA_SALON_INDEX est le mode
d'échec le plus probable de toute cette fonctionnalité. Ce script ouvre
chaque index l'un après l'autre avec un court aperçu vidéo, pour que tu
puisses voir à l'écran laquelle est laquelle avant de remplir .env.

Usage :
    cd media-agent
    uv run python scripts/list_cameras.py [--max-index 5]

Pour chaque index qui s'ouvre : une fenêtre avec l'aperçu vidéo apparaît.
Note ce que tu vois (webcam du PC ou flux du téléphone/Iriun), puis :
    - 'n' ou Échap : passe à l'index suivant
    - 'q'           : arrête le script tout de suite

Une fois les bons index identifiés, mets-les dans .env :
    CAMERA_ENTREE_INDEX=<index de la webcam du PC>
    CAMERA_SALON_INDEX=<index d'Iriun Webcam>
"""

from __future__ import annotations

import argparse

import cv2


def _probe_index(index: int) -> bool:
    """Ouvre l'index `index`, affiche un aperçu tant que l'utilisateur ne
    passe pas au suivant. Retourne False si l'utilisateur veut arrêter
    tout le script ('q'), True sinon (y compris si cet index n'a rien
    donné, on continue vers le suivant)."""
    capture = cv2.VideoCapture(index)
    if not capture.isOpened():
        print(f"Index {index} : rien (aucun périphérique à cet index).")
        capture.release()
        return True

    print(
        f"Index {index} : périphérique trouvé, regarde la fenêtre pour "
        "identifier la caméra. 'n'/Échap = suivant, 'q' = quitter."
    )
    title = f"Index {index} - 'n' suivant, 'q' quitter"
    keep_going = True
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                print(f"Index {index} : périphérique trouvé mais pas de flux lisible.")
                break

            cv2.imshow(title, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("n"), ord("N"), 27):  # suivant
                break
            if key in (ord("q"), ord("Q")):  # quitte tout
                keep_going = False
                break
            try:
                if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
    finally:
        capture.release()
        cv2.destroyWindow(title)

    return keep_going


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-index",
        type=int,
        default=4,
        help="Plus grand index testé (0 à max-index inclus). Défaut : 4.",
    )
    args = parser.parse_args()

    print(f"Sondage des index de caméra 0 à {args.max_index}...")
    for index in range(args.max_index + 1):
        if not _probe_index(index):
            break

    print("Terminé. Renseigne CAMERA_ENTREE_INDEX/CAMERA_SALON_INDEX dans .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

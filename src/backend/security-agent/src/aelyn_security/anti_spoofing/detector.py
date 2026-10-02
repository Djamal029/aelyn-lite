"""Détection anti-spoofing (visage réel vs faux) via un modèle YOLOv8 entraîné.

Repris du prototype AntiSpoofing : ouvre la webcam et encadre chaque visage
détecté en vert (réel) ou rouge (faux/spoof) selon la classe prédite.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import cvzone
from ultralytics import YOLO

MODELS_DIR = Path(__file__).resolve().parents[3] / "models"
DEFAULT_MODEL = MODELS_DIR / "n_version_1_30.pt"
CLASS_NAMES = ["fake", "real"]


def run(model_path: Path = DEFAULT_MODEL, confidence: float = 0.8, camera_index: int = 0) -> None:
    """Lance la détection en direct depuis la webcam jusqu'à l'appui sur 'q'."""
    model = YOLO(str(model_path))
    cap = cv2.VideoCapture(camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    cv2.namedWindow("Image", cv2.WINDOW_NORMAL)

    try:
        while True:
            success, img = cap.read()
            if not success:
                break

            results = model(img, stream=True, verbose=False)
            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    w, h = x2 - x1, y2 - y1

                    conf = math.ceil(box.conf[0] * 100) / 100
                    name = CLASS_NAMES[int(box.cls[0])].upper()

                    if conf > confidence:
                        color = (0, 255, 0) if name == "REAL" else (0, 0, 255)
                        cvzone.cornerRect(img, (x1, y1, w, h), colorC=color, colorR=color)
                        cvzone.putTextRect(
                            img,
                            f"{name} {int(conf * 100)}%",
                            (max(0, x1), max(35, y1)),
                            scale=2,
                            thickness=2,
                            colorR=color,
                            colorB=color,
                        )

            cv2.imshow("Image", img)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    run()

"""Ré-entraîne le détecteur anti-spoofing (fake/real) à partir de Dataset/SplitData."""

from __future__ import annotations

from ultralytics import YOLO

from aelyn_security.anti_spoofing.detector import MODELS_DIR


def run(base_model: str = "yolov8n.pt", data_yaml: str = "Dataset/SplitData/data.yml", epochs: int = 30) -> None:
    model = YOLO(str(MODELS_DIR / base_model))
    model.train(data=data_yaml, epochs=epochs)


if __name__ == "__main__":
    run()

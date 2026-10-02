# aelyn-security

Agent de sécurité d'AELYN. Contient pour l'instant le module `anti_spoofing` :
détection de liveness (visage réel vs faux/spoof) via un modèle YOLOv8
entraîné sur des images réelles et des tentatives de spoofing (photo, écran).

Repris et réintégré depuis un prototype (`AntiSpoofingDetector`).

## Modèles

Les poids entraînés sont dans `models/` :

- `n_version_1_30.pt` : modèle utilisé par défaut par `detector.run()`.
- `n_version_1_3.pt` : version antérieure, conservée pour comparaison.
- `yolov8n.pt` : poids de base YOLOv8n, point de départ pour un ré-entraînement.

## Utilisation

```bash
uv run python -m aelyn_security.anti_spoofing.detector
```

Ouvre la webcam et encadre chaque visage détecté : vert = réel, rouge = faux.
Quitter avec `q`.

## Ré-entraîner le modèle

1. `data_collection.run(class_id=...)` (0 = faux, 1 = réel) pour peupler
   `Dataset/DataCollect` avec des images labellisées.
2. Regrouper les images/labels validés dans `Dataset/all`.
3. `split_data.run()` pour générer `Dataset/SplitData` (train/val/test) et son
   `data.yml`.
4. `train.run()` pour entraîner un nouveau modèle à partir de `yolov8n.pt` ;
   récupérer ensuite `runs/detect/train/weights/best.pt` et le déposer dans
   `models/`.

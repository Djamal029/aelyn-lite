"""Répartit le dataset collecté (Dataset/all) en train/val/test pour YOLO."""

from __future__ import annotations

import os
import random
import shutil
from itertools import islice

CLASSES = ["fake", "real"]


def run(
    input_folder: str = "Dataset/all",
    output_folder: str = "Dataset/SplitData",
    split_ratio: dict[str, float] | None = None,
) -> None:
    split_ratio = split_ratio or {"train": 0.7, "val": 0.2, "test": 0.1}

    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)

    for split in ("train", "val", "test"):
        os.makedirs(f"{output_folder}/{split}/images", exist_ok=True)
        os.makedirs(f"{output_folder}/{split}/labels", exist_ok=True)

    uniqueNames = list({name.split(".")[0] for name in os.listdir(input_folder)})
    random.shuffle(uniqueNames)

    lenData = len(uniqueNames)
    lenTrain = int(lenData * split_ratio["train"])
    lenVal = int(lenData * split_ratio["val"])
    lenTest = int(lenData * split_ratio["test"])

    remaining = lenData - lenTrain - lenVal - lenTest
    lenTrain += remaining

    names = iter(uniqueNames)
    splits = {
        "train": list(islice(names, lenTrain)),
        "val": list(islice(names, lenVal)),
        "test": list(islice(names, lenTest)),
    }
    print(f"Total Images: {lenData} \nSplit: {len(splits['train'])} {len(splits['val'])} {len(splits['test'])}")

    for split, filenames in splits.items():
        for filename in filenames:
            shutil.copy(f"{input_folder}/{filename}.jpg", f"{output_folder}/{split}/images/{filename}.jpg")
            shutil.copy(f"{input_folder}/{filename}.txt", f"{output_folder}/{split}/labels/{filename}.txt")

    print("Split Process Completed...")

    data_yaml = (
        f"path: ../Data\n"
        f"train: ../train/images\n"
        f"val: ../val/images\n"
        f"test: ../test/images\n\n"
        f"nc: {len(CLASSES)}\n"
        f"names: {CLASSES}"
    )
    with open(f"{output_folder}/data.yml", "w") as f:
        f.write(data_yaml)

    print("data.yml file created...")


if __name__ == "__main__":
    run()

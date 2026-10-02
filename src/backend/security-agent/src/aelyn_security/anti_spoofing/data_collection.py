"""Collecte d'images labellisées (réel/faux) pour ré-entraîner le détecteur.

Ouvre la webcam, détecte les visages, et sauvegarde les images nettes
(non floues) accompagnées d'un fichier .txt au format YOLO dans
``Dataset/DataCollect``.
"""

from __future__ import annotations

from time import time

import cv2
import cvzone
from cvzone.FaceDetectionModule import FaceDetector


def run(
    class_id: int = 1,
    output_folder: str = "Dataset/DataCollect",
    confidence: float = 0.8,
    save: bool = True,
    blur_threshold: int = 35,
    debug: bool = False,
    offset_pct_h: float = 0.1,
    offset_pct_w: float = 0.2,
    cam_size: tuple[int, int] = (640, 480),
    float_digits: int = 6,
) -> None:
    """class_id : 0 = faux visage, 1 = visage réel."""
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam_size[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_size[1])

    detector = FaceDetector()

    while True:
        success, img = cap.read()
        if not success:
            break

        imgOut = img.copy()
        img, bboxs = detector.findFaces(img, draw=False)

        listBlur: list[bool] = []
        listInfo: list[str] = []

        if bboxs:
            for bbox in bboxs:
                x, y, w, h = bbox["bbox"]
                score = bbox["score"][0]

                if score <= confidence:
                    continue

                offsetW = offset_pct_w * w
                x = int(x - offsetW)
                w = int(w + 2 * offsetW)

                offsetH = offset_pct_h * h
                y = int(y - offsetH * 5)
                h = int(h + offsetH * 5.5)

                x, y, w, h = max(0, x), max(0, y), max(0, w), max(0, h)

                imgFace = img[y : y + h, x : x + w]
                cv2.imshow("Face", imgFace)

                blurValue = int(cv2.Laplacian(imgFace, cv2.CV_64F).var())
                if blurValue > blur_threshold:
                    listBlur.append(True)

                ih, iw, _ = img.shape
                xc, yc = x + w / 2, y + h / 2
                xcn, ycn = round(xc / iw, float_digits), round(yc / ih, float_digits)
                wn, hn = w / iw, h / ih

                xcn, ycn, wn, hn = min(1, xcn), min(1, ycn), min(1, wn), min(1, hn)

                listInfo.append(f"{class_id} {xcn} {ycn} {wn} {hn}\n")

                if debug:
                    cv2.rectangle(imgOut, (x, y, w, h), (255, 0, 0), 3)
                    cvzone.putTextRect(
                        imgOut, f"Score: {int(score * 100)}% Blur: {blurValue}", (x, y - 20), scale=2, thickness=2
                    )

            if save and listBlur and all(listBlur):
                timeNow = str(time()).replace(".", "")
                cv2.imwrite(f"{output_folder}/{timeNow}.jpg", img)
                with open(f"{output_folder}/{timeNow}.txt", "a") as f:
                    f.writelines(listInfo)

        cv2.imshow("Image", imgOut)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    run()

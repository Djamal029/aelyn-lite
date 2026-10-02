import os

os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import cv2
from cvzone.FaceDetectionModule import FaceDetector

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise RuntimeError("Impossible d'ouvrir la caméra (index 0).")

detector = FaceDetector()

while True:
    success, frame = cap.read()
    if not success:
        continue

    frame, bboxs = detector.findFaces(frame)

    for bbox in bboxs:
        x, y, w, h = bbox["bbox"]
        score = bbox["score"][0]

        print(int(score * 100))

        if score > 0.6:
            frame = cv2.rectangle(
                frame,
                (x, y),
                (x + w, y + h),
                (0, 255, 0),
                2
            )

    cv2.imshow("Face detection", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
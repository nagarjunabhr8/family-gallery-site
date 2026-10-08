"""Photo quality metrics: sharpness, exposure, resolution, faces / eyes open.

All component scores are in 0..1 (higher is better).
"""

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from ..ai import registry


def sharpness_raw(gray: np.ndarray) -> float:
    """Variance of the Laplacian: high for crisp detail, low for blur."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def sharpness_score(var: float) -> float:
    # Logistic on log10(variance): ~30 -> 0.2 (blurry), 100 -> 0.5, 1000 -> 0.95
    return 1 / (1 + math.exp(-(math.log10(max(var, 1e-3)) - 2.0) * 3))


def exposure_score(gray: np.ndarray) -> float:
    """Penalise very dark/bright images and clipped shadows/highlights."""
    g = gray.astype(np.float32) / 255.0
    mean = float(g.mean())
    dark = float((g < 0.03).mean())
    bright = float((g > 0.97).mean())
    score = 1 - abs(mean - 0.48) * 1.4 - max(0.0, dark - 0.05) * 1.5 - max(0.0, bright - 0.05) * 1.5
    return min(1.0, max(0.0, score))


def resolution_score(width: int, height: int) -> float:
    """12 MP and above scores 1; WhatsApp-sized (~2 MP) about 0.45."""
    mp = width * height / 1e6
    return min(1.0, math.log2(mp + 1) / math.log2(13))


@dataclass
class FaceResult:
    count: int = 0
    judged: int = 0  # faces big enough to assess
    eyes_open: float | None = None
    face_sharpness: float | None = None
    boxes: list[tuple[int, int, int, int]] = field(default_factory=list)

    @property
    def score(self) -> float | None:
        if self.eyes_open is None:
            return None
        return 0.6 * self.eyes_open + 0.4 * (self.face_sharpness or 0)


class EyeChecker:
    """Haar eye detector run inside each eye-landmark region: finds open eyes, rarely closed ones."""

    def __init__(self) -> None:
        base = cv2.data.haarcascades
        self.eye_cascades = [
            cv2.CascadeClassifier(base + "haarcascade_eye.xml"),
            cv2.CascadeClassifier(base + "haarcascade_eye_tree_eyeglasses.xml"),
        ]

    def eyes_open(self, gray: np.ndarray, kps, face_w: float) -> bool:
        (rx, ry), (lx, ly) = kps[0], kps[1]
        return self._eye_open(gray, rx, ry, face_w) or self._eye_open(gray, lx, ly, face_w)

    def _eye_open(self, gray: np.ndarray, cx: float, cy: float, face_w: float) -> bool:
        half = max(8, int(face_w * 0.18))
        x0, y0 = max(0, int(cx) - half), max(0, int(cy) - half)
        crop = gray[y0 : int(cy) + half, x0 : int(cx) + half]
        if crop.size == 0:
            return False
        crop = cv2.equalizeHist(cv2.resize(crop, (64, 64), interpolation=cv2.INTER_CUBIC))
        return any(
            len(c.detectMultiScale(crop, scaleFactor=1.1, minNeighbors=3, minSize=(14, 14))) > 0
            for c in self.eye_cascades
        )


class FaceAnalyzer(EyeChecker):
    """YuNet face detection + eye check. Fallback when InsightFace models aren't installed."""

    MIN_FACE_PX = 60

    def __init__(self) -> None:
        super().__init__()
        self.detector = cv2.FaceDetectorYN.create(
            str(registry.model_path("yunet")), "", (320, 320), score_threshold=0.75, nms_threshold=0.3, top_k=50
        )

    def analyze(self, bgr: np.ndarray, gray: np.ndarray) -> FaceResult:
        h, w = gray.shape
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(bgr)
        res = FaceResult()
        if faces is None:
            return res
        res.count = len(faces)
        open_flags, sharp = [], []
        for f in faces:
            x, y, fw, fh = (float(v) for v in f[:4])
            res.boxes.append((int(x), int(y), int(fw), int(fh)))
            if fw < self.MIN_FACE_PX:
                continue
            res.judged += 1
            right_eye, left_eye = (f[4], f[5]), (f[6], f[7])
            open_flags.append(
                self._eye_open(gray, *right_eye, fw) or self._eye_open(gray, *left_eye, fw)
            )
            fx0, fy0 = max(0, int(x)), max(0, int(y))
            face = gray[fy0 : fy0 + int(fh), fx0 : fx0 + int(fw)]
            if face.size:
                sharp.append(sharpness_score(sharpness_raw(face)))
        if res.judged:
            res.eyes_open = sum(open_flags) / res.judged
            res.face_sharpness = float(np.mean(sharp)) if sharp else None
        return res


WEIGHTS = {"sharpness": 0.30, "exposure": 0.15, "resolution": 0.10, "face": 0.20, "aesthetic": 0.25}


def total_score(components: dict[str, float | None]) -> float:
    """Weighted mean (0..100) over the components that are available."""
    num = den = 0.0
    for key, weight in WEIGHTS.items():
        value = components.get(key)
        if value is not None:
            num += weight * value
            den += weight
    return round(100 * num / den, 1) if den else 0.0

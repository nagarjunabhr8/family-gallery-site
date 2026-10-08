"""InsightFace buffalo_l via ONNX Runtime: SCRFD-10G detection + ArcFace R50 embeddings.

Re-implements the small pre/post-processing parts of the `insightface` package
so we don't need it (it drags in full opencv-python, scipy and scikit-image).
"""

from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime as ort

from . import registry

DET_SIZE = 640
ARCFACE_DST = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float32,
)


@dataclass
class DetectedFace:
    box: np.ndarray  # x1, y1, x2, y2 in input-image pixels
    kps: np.ndarray  # (5, 2): right eye, left eye, nose, right mouth, left mouth (image left->right)
    score: float
    embedding: np.ndarray | None = None
    aligned: np.ndarray | None = None  # 112x112 BGR crop used for recognition


def _session(path) -> ort.InferenceSession:
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    return ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])


def _nms(dets: np.ndarray, thresh: float) -> list[int]:
    x1, y1, x2, y2, scores = dets.T
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0, xx2 - xx1 + 1) * np.maximum(0, yy2 - yy1 + 1)
        ovr = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[np.where(ovr <= thresh)[0] + 1]
    return keep


class FaceEngine:
    def __init__(self, det_thresh: float = 0.5) -> None:
        self.det = _session(registry.model_path("buffalo_l", "det_10g.onnx"))
        self.rec = _session(registry.model_path("buffalo_l", "w600k_r50.onnx"))
        self.det_input = self.det.get_inputs()[0].name
        self.det_outputs = [o.name for o in self.det.get_outputs()]
        self.rec_input = self.rec.get_inputs()[0].name
        self.det_thresh = det_thresh
        self.fmc, self.strides, self.num_anchors = 3, (8, 16, 32), 2
        self._anchor_cache: dict[tuple[int, int, int], np.ndarray] = {}

    # ---------- detection ----------

    def _anchors(self, h: int, w: int, stride: int) -> np.ndarray:
        key = (h, w, stride)
        if key not in self._anchor_cache:
            centers = np.stack(np.mgrid[:h, :w][::-1], axis=-1).astype(np.float32)
            centers = (centers * stride).reshape(-1, 2)
            self._anchor_cache[key] = np.stack([centers] * self.num_anchors, axis=1).reshape(-1, 2)
        return self._anchor_cache[key]

    def detect(self, bgr: np.ndarray) -> list[DetectedFace]:
        h, w = bgr.shape[:2]
        if h / w > 1:
            new_h, new_w = DET_SIZE, int(DET_SIZE * w / h)
        else:
            new_w, new_h = DET_SIZE, int(DET_SIZE * h / w)
        scale = new_h / h
        canvas = np.zeros((DET_SIZE, DET_SIZE, 3), dtype=np.uint8)
        canvas[:new_h, :new_w] = cv2.resize(bgr, (new_w, new_h))
        blob = cv2.dnn.blobFromImage(canvas, 1 / 128, (DET_SIZE, DET_SIZE), (127.5, 127.5, 127.5), swapRB=True)
        outs = self.det.run(self.det_outputs, {self.det_input: blob})
        if outs[0].ndim == 3:  # batched export
            outs = [o[0] for o in outs]

        boxes, kpss, scores = [], [], []
        for i, stride in enumerate(self.strides):
            sc = outs[i].reshape(-1)
            bb = outs[i + self.fmc].reshape(-1, 4) * stride
            kp = outs[i + self.fmc * 2].reshape(-1, 10) * stride
            anchors = self._anchors(DET_SIZE // stride, DET_SIZE // stride, stride)
            pos = np.where(sc >= self.det_thresh)[0]
            if not len(pos):
                continue
            a = anchors[pos]
            d = bb[pos]
            boxes.append(np.stack([a[:, 0] - d[:, 0], a[:, 1] - d[:, 1], a[:, 0] + d[:, 2], a[:, 1] + d[:, 3]], -1))
            k = kp[pos].reshape(-1, 5, 2) + a[:, None, :]
            kpss.append(k)
            scores.append(sc[pos])
        if not boxes:
            return []
        boxes_a = np.concatenate(boxes) / scale
        kps_a = np.concatenate(kpss) / scale
        scores_a = np.concatenate(scores)
        keep = _nms(np.hstack([boxes_a, scores_a[:, None]]), 0.4)
        return [DetectedFace(boxes_a[i], kps_a[i], float(scores_a[i])) for i in keep]

    # ---------- recognition ----------

    def embed(self, bgr: np.ndarray, faces: list[DetectedFace]) -> None:
        """Fill `embedding` (L2-normalised 512-d) and `aligned` for each face."""
        if not faces:
            return
        crops = []
        for f in faces:
            m, _ = cv2.estimateAffinePartial2D(f.kps.astype(np.float32), ARCFACE_DST, method=cv2.LMEDS)
            f.aligned = cv2.warpAffine(bgr, m, (112, 112), borderValue=0.0)
            crops.append(f.aligned)
        blob = cv2.dnn.blobFromImages(crops, 1 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
        (emb,) = self.rec.run(None, {self.rec_input: blob})
        emb = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-8)
        for f, e in zip(faces, emb.astype(np.float32)):
            f.embedding = e

    def analyze(self, bgr: np.ndarray) -> list[DetectedFace]:
        faces = self.detect(bgr)
        self.embed(bgr, faces)
        return faces

import cv2
import numpy as np

from app.analysis import quality as q

from .conftest import pattern


def _gray(img) -> np.ndarray:
    return np.asarray(img.convert("L"))


def _detailed(seed=1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = _gray(pattern(seed, (1024, 768))).astype(np.int16)
    noise = rng.integers(-40, 40, base.shape)
    return np.clip(base + noise, 0, 255).astype(np.uint8)


def test_blur_lowers_sharpness():
    sharp = _detailed()
    blurry = cv2.GaussianBlur(sharp, (0, 0), 6)
    s_sharp = q.sharpness_score(q.sharpness_raw(sharp))
    s_blur = q.sharpness_score(q.sharpness_raw(blurry))
    assert s_sharp > 0.8 and s_blur < 0.3


def test_exposure_penalises_dark_and_bright():
    good = _gray(pattern(1))
    dark = (good * 0.15).astype(np.uint8)
    bright = np.clip(good.astype(np.int16) + 170, 0, 255).astype(np.uint8)
    assert q.exposure_score(good) > 0.7
    assert q.exposure_score(dark) < 0.4
    assert q.exposure_score(bright) < 0.4


def test_resolution_score_monotonic():
    assert q.resolution_score(640, 480) < q.resolution_score(1600, 1200) < q.resolution_score(4000, 3000)
    assert q.resolution_score(4000, 3000) == 1.0


def test_total_score_ignores_missing_components():
    full = q.total_score({"sharpness": 1, "exposure": 1, "resolution": 1, "face": 1, "aesthetic": 1})
    partial = q.total_score({"sharpness": 1, "exposure": 1, "resolution": 1, "face": None, "aesthetic": None})
    assert full == partial == 100.0
    assert q.total_score({"sharpness": 0.5, "exposure": 0.5, "resolution": 0.5}) == 50.0

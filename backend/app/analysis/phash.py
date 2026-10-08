"""64-bit DCT perceptual hash and Hamming distance."""

import cv2
import numpy as np


def phash(gray: np.ndarray) -> str:
    """pHash of a grayscale uint8 image, as 16 hex chars."""
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    low = cv2.dct(small)[:8, :8]
    median = np.median(low.flatten()[1:])  # ignore the DC term
    bits = (low > median).flatten()
    value = 0
    for b in bits:
        value = (value << 1) | int(b)
    return f"{value:016x}"


def to_int(h: str) -> int:
    return int(h, 16)


def hamming(a: str, b: str) -> int:
    return (to_int(a) ^ to_int(b)).bit_count()


def hash_array(hashes: list[str]) -> np.ndarray:
    return np.array([to_int(h) for h in hashes], dtype=np.uint64)

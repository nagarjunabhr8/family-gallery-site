import io

import numpy as np
from PIL import Image, ImageEnhance

from app.analysis.phash import hamming, phash

from .conftest import pattern


def _hash(img: Image.Image) -> str:
    return phash(np.asarray(img.convert("L")))


def _jpeg_roundtrip(img: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue()))


def test_hash_format():
    h = _hash(pattern(1))
    assert len(h) == 16 and int(h, 16) >= 0


def test_resized_and_recompressed_copy_is_near():
    original = pattern(1, (1200, 900))
    copy = _jpeg_roundtrip(original.resize((400, 300)), quality=60)
    assert hamming(_hash(original), _hash(copy)) <= 4


def test_slightly_brighter_copy_is_near():
    original = pattern(2)
    brighter = ImageEnhance.Brightness(original).enhance(1.15)
    assert hamming(_hash(original), _hash(brighter)) <= 6


def test_different_photos_are_far():
    hashes = [_hash(pattern(seed)) for seed in range(10)]
    for i in range(len(hashes)):
        for j in range(i + 1, len(hashes)):
            assert hamming(hashes[i], hashes[j]) > 12


def test_hamming():
    assert hamming("0000000000000000", "0000000000000000") == 0
    assert hamming("0000000000000000", "ffffffffffffffff") == 64
    assert hamming("00000000000000ff", "000000000000000f") == 4

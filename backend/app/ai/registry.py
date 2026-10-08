"""Local AI model files. Downloaded once into <data>/models, then used fully offline."""

import hashlib
import json
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..safety import check_writable, data_dir, safe_mkdir, safe_unlink, safe_write_bytes


@dataclass(frozen=True)
class ModelSpec:
    filename: str  # a file, or a directory when `members` is set
    url: str
    purpose: str
    members: tuple[str, ...] = ()  # files to extract from a zip archive


MODELS: dict[str, ModelSpec] = {
    "yunet": ModelSpec(
        "face_detection_yunet_2023mar.onnx",
        "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
        "Face detection with eye/nose/mouth landmarks (fallback)",
    ),
    "clip_vision": ModelSpec(
        "clip-vit-b32-vision.onnx",
        "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model.onnx",
        "CLIP ViT-B/32 image encoder",
    ),
    "aesthetic_head": ModelSpec(
        "laion-aesthetic-vit-b32-linear.pth",
        "https://github.com/LAION-AI/aesthetic-predictor/raw/main/sa_0_4_vit_b_32_linear.pth",
        "LAION aesthetic predictor (linear head on CLIP ViT-B/32)",
    ),
    "buffalo_l": ModelSpec(
        "buffalo_l",
        "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
        "InsightFace buffalo_l: SCRFD face detector + ArcFace recognition (non-commercial licence)",
        members=("det_10g.onnx", "w600k_r50.onnx"),
    ),
}


def models_dir() -> Path:
    return data_dir() / "models"


def model_path(key: str, member: str | None = None) -> Path:
    base = models_dir() / MODELS[key].filename
    return base / member if member else base


def is_installed(key: str) -> bool:
    spec = MODELS[key]
    if spec.members:
        return all(model_path(key, m).is_file() for m in spec.members)
    return model_path(key).is_file()


def status() -> dict[str, dict]:
    return {
        key: {"installed": is_installed(key), "purpose": spec.purpose, "file": spec.filename}
        for key, spec in MODELS.items()
    }


def _fetch(url: str, dest: Path, label: str, progress: Callable[[str], None]) -> tuple[str, int]:
    part = check_writable(dest.with_name(dest.name + ".part"))
    sha = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "family-memories"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done, last = 0, -1
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            pct = done * 100 // total if total else -1
            if pct // 10 != last // 10:
                progress(f"  {label}: {done / 1e6:.0f} MB" + (f" ({pct}%)" if total else ""))
                last = pct
    part.replace(dest)
    return sha.hexdigest(), done


def download(key: str, progress: Callable[[str], None] = print) -> Path:
    """Download one model (no-op if present). Writes only inside <data>/models."""
    spec = MODELS[key]
    target = check_writable(model_path(key))
    if is_installed(key):
        return target
    safe_mkdir(models_dir())

    if spec.members:
        archive = check_writable(models_dir() / f"{spec.filename}.zip")
        digest, size = _fetch(spec.url, archive, key, progress)
        safe_mkdir(target)
        with zipfile.ZipFile(archive) as zf:
            by_name = {Path(n).name: n for n in zf.namelist() if not n.endswith("/")}
            for member in spec.members:
                if member not in by_name:
                    raise RuntimeError(f"{member} not found in {spec.url}")
                # write by basename only: archive paths are never trusted
                safe_write_bytes(target / member, zf.read(by_name[member]))
        safe_unlink(archive)
    else:
        digest, size = _fetch(spec.url, target, key, progress)

    manifest = models_dir() / "manifest.json"
    data = json.loads(manifest.read_text()) if manifest.is_file() else {}
    data[spec.filename] = {"url": spec.url, "sha256": digest, "bytes": size}
    safe_write_bytes(manifest, json.dumps(data, indent=2).encode())
    return target

"""CLIP zero-shot scene tags from the stored image embeddings."""

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..ai import registry
from ..models import ClipEmbedding, MediaTag

TAGS: dict[str, list[str]] = {
    "birthday": [
        "a photo of a birthday party",
        "a birthday cake with candles",
        "a child cutting a birthday cake",
    ],
    "wedding": [
        "a photo of an indian wedding ceremony",
        "a bride and groom at their wedding",
        "a decorated wedding stage with guests",
    ],
    "temple": [
        "a photo of a hindu temple",
        "people visiting a temple",
        "a statue of a hindu god in a temple",
    ],
    "school": [
        "a photo of children at school",
        "students in school uniform",
        "a school classroom or school function",
    ],
    "travel": [
        "a travel photo at a tourist place",
        "a scenic landscape on a trip",
        "tourists sightseeing at a famous monument",
    ],
    "beach": [
        "a photo at the beach",
        "people standing by the sea",
        "sand, sea waves and the shore",
    ],
}

# Everyday scenes, so ordinary photos don't get forced into a tag
BACKGROUND = [
    "a photo of people at home",
    "a selfie of a family",
    "a photo of a baby",
    "a photo of a child playing indoors",
    "a photo of food on a table",
    "a photo of a room",
    "a photo of a street",
    "a portrait of a person",
    "a decorated function hall or festival pandal",
    "people dressed up for a festival celebration",
]

LABELS = {
    "birthday": "Birthday",
    "wedding": "Wedding",
    "temple": "Temple",
    "school": "School",
    "travel": "Travel",
    "beach": "Beach",
}

_class_cache: tuple[list[str], np.ndarray] | None = None


def class_embeddings() -> tuple[list[str], np.ndarray]:
    """(names, matrix) with one row per tag (prompt average) and per background prompt."""
    global _class_cache
    if _class_cache is None:
        from ..ai.clip import ClipText

        enc = ClipText()
        names, rows = [], []
        for tag, prompts in TAGS.items():
            mean = np.mean([enc.embed(p) for p in prompts], axis=0)
            names.append(tag)
            rows.append(mean / np.linalg.norm(mean))
        for i, prompt in enumerate(BACKGROUND):
            names.append(f"_bg{i}")
            rows.append(enc.embed(prompt))
        _class_cache = (names, np.stack(rows).astype(np.float32))
    return _class_cache


def available() -> bool:
    return registry.is_installed("clip_text") and registry.is_installed("clip_tokenizer")


def tag_probabilities(image_embs: np.ndarray, classes: np.ndarray) -> np.ndarray:
    """Softmax over all classes (CLIP's logit scale is 100)."""
    logits = 100.0 * image_embs @ classes.T
    logits -= logits.max(axis=1, keepdims=True)
    p = np.exp(logits)
    return p / p.sum(axis=1, keepdims=True)


def tag_all(s: Session, threshold: float) -> dict:
    """Re-tag every photo that has a CLIP embedding. Cheap: one matrix multiply."""
    if not available():
        return {"tagged": 0, "skipped": "CLIP text model not installed"}
    names, classes = class_embeddings()
    rows = s.execute(select(ClipEmbedding.media_id, ClipEmbedding.vector)).all()
    s.execute(delete(MediaTag))
    if not rows:
        s.commit()
        return {"tagged": 0}
    ids = [r[0] for r in rows]
    embs = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
    probs = tag_probabilities(embs, classes)
    tagged = 0
    for media_id, p in zip(ids, probs):
        hit = False
        for j, name in enumerate(names):
            if not name.startswith("_bg") and p[j] >= threshold:
                s.add(MediaTag(media_id=media_id, tag=name, score=round(float(p[j]), 3)))
                hit = True
        tagged += hit
    s.commit()
    return {"tagged": tagged, "photos": len(ids)}

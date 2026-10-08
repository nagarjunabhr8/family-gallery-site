"""CLIP ViT-B/32 image embeddings (ONNX) and the LAION aesthetic head. Runs locally on CPU."""

import collections
import pickle
import zipfile
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

from . import registry

MODEL_NAME = "clip-vit-b32"
_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)


def preprocess(img: Image.Image) -> np.ndarray:
    """Resize shortest side to 224 (bicubic), centre-crop, normalise -> (1, 3, 224, 224)."""
    img = img.convert("RGB")
    scale = 224 / min(img.size)
    img = img.resize((max(224, round(img.width * scale)), max(224, round(img.height * scale))), Image.Resampling.BICUBIC)
    left, top = (img.width - 224) // 2, (img.height - 224) // 2
    arr = np.asarray(img.crop((left, top, left + 224, top + 224)), dtype=np.float32) / 255.0
    arr = (arr - _MEAN) / _STD
    return arr.transpose(2, 0, 1)[None]


def load_torch_linear(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Read weight/bias from a PyTorch state-dict .pth without importing torch.

    Uses a restricted unpickler that only allows tensor rebuilding, so the
    file cannot execute arbitrary code.
    """
    zf = zipfile.ZipFile(path)
    pkl = next(n for n in zf.namelist() if n.endswith("data.pkl"))
    prefix = pkl[: -len("data.pkl")]
    dtypes = {"FloatStorage": np.float32, "DoubleStorage": np.float64, "HalfStorage": np.float16}

    def rebuild_tensor(storage, offset, size, stride, *_):
        item = storage.itemsize
        view = np.lib.stride_tricks.as_strided(
            storage[offset:], shape=tuple(size), strides=tuple(s * item for s in stride)
        )
        return np.array(view)

    class SafeUnpickler(pickle.Unpickler):
        def find_class(self, module, name):
            if module == "torch._utils" and name == "_rebuild_tensor_v2":
                return rebuild_tensor
            if module == "torch._utils" and name == "_rebuild_parameter":
                return lambda data, *_: data
            if module == "collections" and name == "OrderedDict":
                return collections.OrderedDict
            if module == "torch" and name in dtypes:
                return name
            raise pickle.UnpicklingError(f"Blocked unexpected object in model file: {module}.{name}")

        def persistent_load(self, pid):
            _, storage_type, key, _location, _numel = pid
            dtype = dtypes[storage_type if isinstance(storage_type, str) else storage_type.__name__]
            return np.frombuffer(zf.read(f"{prefix}data/{key}"), dtype=dtype)

    with zf.open(pkl) as f:
        state = SafeUnpickler(f).load()
    weight = next(v for k, v in state.items() if k.endswith("weight"))
    bias = next(v for k, v in state.items() if k.endswith("bias"))
    return weight.astype(np.float32), bias.astype(np.float32)


class ClipScorer:
    def __init__(self) -> None:
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(
            str(registry.model_path("clip_vision")), opts, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        outputs = [o.name for o in self.session.get_outputs()]
        self.output_name = "image_embeds" if "image_embeds" in outputs else outputs[0]
        self.head = load_torch_linear(registry.model_path("aesthetic_head")) if registry.is_installed(
            "aesthetic_head"
        ) else None

    def embed(self, img: Image.Image) -> np.ndarray:
        (out,) = self.session.run([self.output_name], {self.input_name: preprocess(img)})
        vec = np.asarray(out, dtype=np.float32).reshape(-1)
        return vec / (np.linalg.norm(vec) + 1e-8)

    def aesthetic(self, embedding: np.ndarray) -> float | None:
        """LAION aesthetic rating, roughly 1 (poor) .. 10 (beautiful)."""
        if self.head is None:
            return None
        weight, bias = self.head
        return float(embedding @ weight.reshape(-1) + bias.reshape(-1)[0])


def aesthetic_score(raw: float) -> float:
    """Map LAION rating to 0..1 (3.5 -> 0, 7.5 -> 1)."""
    return min(1.0, max(0.0, (raw - 3.5) / 4.0))

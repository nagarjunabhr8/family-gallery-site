"""`python -m app.ai.download` — fetch the local AI models into <data>/models."""

import sys

from .. import safety
from ..config import default_data_dir
from .registry import MODELS, download, model_path


def main() -> int:
    safety.set_data_dir(default_data_dir())
    keys = sys.argv[1:] or list(MODELS)
    for key in keys:
        if key not in MODELS:
            print(f"Unknown model '{key}'. Choose from: {', '.join(MODELS)}")
            return 1
        print(f"{key}: {MODELS[key].purpose}")
        download(key)
        print(f"  ready: {model_path(key)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

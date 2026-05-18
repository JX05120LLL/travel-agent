"""Shared embedding model configuration."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FASTEMBED_CACHE_DIR = PROJECT_ROOT / ".cache" / "fastembed"
FASTEMBED_MODEL_CACHE_SUBDIR = "fast-bge-small-zh-v1.5"
FASTEMBED_MODEL_FILE = "model_optimized.onnx"


def get_fastembed_cache_dir() -> str:
    """Return a stable fastembed cache directory outside the OS temp folder."""
    raw_path = os.getenv("FASTEMBED_CACHE_DIR", "").strip()
    cache_dir = Path(raw_path).expanduser() if raw_path else DEFAULT_FASTEMBED_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    return str(cache_dir)


def get_fastembed_model_kwargs() -> dict[str, str]:
    """Build fastembed kwargs, preferring an already extracted local model."""
    cache_dir = Path(get_fastembed_cache_dir())
    kwargs = {"cache_dir": str(cache_dir)}
    local_model_dir = cache_dir / FASTEMBED_MODEL_CACHE_SUBDIR
    if (local_model_dir / FASTEMBED_MODEL_FILE).exists():
        kwargs["specific_model_path"] = str(local_model_dir)
    return kwargs

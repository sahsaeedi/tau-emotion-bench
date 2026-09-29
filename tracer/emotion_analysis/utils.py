import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")


def load_config(config_path: str) -> Dict[str, Any]:
    path = Path(config_path)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return json.loads(path.read_text(encoding="utf-8"))


def get_embedding_model_cfg(config: Dict[str, Any]) -> Dict[str, Any]:
    model_cfg = config.get("embedding_model")
    if model_cfg:
        return model_cfg
    raise ValueError("Config is missing 'embedding_model'.")


def resolve_project_path(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def task_embedding_text(task: Dict[str, Any]) -> str:
    """Text used for task embeddings: non-blank feeling, else instruction (may be empty)."""
    feeling = task.get("feeling")
    if isinstance(feeling, str) and feeling.strip():
        return feeling.strip()
    return str(task.get("instruction", ""))


def format_task_skip_line(task_path: Path, index: int, task: Dict[str, Any]) -> str:
    tid = task.get("task_id", "?")
    parts = [f"skip: file={task_path.name} index={index} task_id={tid!r}"]
    if task.get("failed") is True:
        err = task.get("error", "")
        if isinstance(err, str) and len(err) > 200:
            err = err[:200] + "…"
        parts.append(f"failed=True error={err!r}")
    else:
        parts.append("no non-blank feeling and empty/missing instruction")
    return " | ".join(parts)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _slugify(value: str) -> str:
    text = str(value).strip().lower().replace("\\", "/")
    text = re.sub(r"[^a-z0-9._/-]+", "-", text)
    text = text.strip("-")
    return text or "unknown"


def model_storage_parts(model_cfg: Dict[str, Any]) -> Dict[str, str]:
    encoder_type = _slugify(model_cfg.get("type", "unknown"))
    model = str(model_cfg.get("model", "unknown")).strip()
    if "/" in model:
        provider, model_name = model.split("/", 1)
    else:
        provider, model_name = "default", model
    return {
        "encoder_type": encoder_type,
        "provider": _slugify(provider),
        "model": _slugify(model_name),
    }


def output_dir_for_model(config: Dict[str, Any], model_cfg: Dict[str, Any]) -> Path:
    root = resolve_project_path(config["outputs"]["root_dir"])
    parts = model_storage_parts(model_cfg)
    return root / parts["encoder_type"] / parts["provider"] / parts["model"]


def encode_texts(model_cfg: Dict[str, Any], texts: List[str]) -> np.ndarray:
    encoder_type = model_cfg.get("type", "llm")
    if encoder_type == "llm":
        try:
            from litellm import embedding
        except ImportError as exc:
            raise ImportError("litellm is required for llm embeddings.") from exc

        model = model_cfg["model"]
        api_base = model_cfg.get("api_base", "")
        batch_size = int(model_cfg.get("batch_size", 64))
        all_vectors: List[List[float]] = []
        total_batches = (len(texts) + batch_size - 1) // batch_size if texts else 0

        for start in tqdm(
            range(0, len(texts), batch_size),
            total=total_batches,
            desc=f"Embedding {model}",
            unit="batch",
        ):
            batch = texts[start : start + batch_size]
            kwargs = {"model": model, "input": batch}
            if api_base:
                kwargs["api_base"] = api_base
            response = embedding(**kwargs)
            all_vectors.extend(item["embedding"] for item in response["data"])

        return np.array(all_vectors, dtype=float)

    raise ValueError(f"Unsupported encoder type: {encoder_type}")


def l2_normalize_rows(a: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(a, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (a / n).astype(np.float32)


def load_encoder_knn_models(model_dir: Path) -> Optional[Dict[str, Any]]:
    """Sklearn KNN classifiers saved by train_encoder (torch.load pickle bundle)."""
    knn_path = model_dir / "knn_models.pt"
    if not knn_path.is_file():
        return None
    try:
        import torch

        try:
            return torch.load(knn_path, map_location="cpu", weights_only=False)
        except TypeError:
            return torch.load(knn_path, map_location="cpu")
    except Exception:
        return None


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a_norm = np.linalg.norm(a)
    b_norm = np.linalg.norm(b)
    if a_norm == 0 or b_norm == 0:
        return 0.0
    return float(np.dot(a, b) / (a_norm * b_norm))

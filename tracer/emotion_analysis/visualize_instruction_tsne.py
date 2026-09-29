import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from utils import get_embedding_model_cfg, load_config, output_dir_for_model

FAMILY_COLORS: Dict[str, str] = {
    "anger": "#e15759",
    "fear": "#4e79a7",
    "disgust": "#b07aa1",
    "sadness": "#9c755f",
    "enjoyment": "#f28e2b",
}


def _select_device(torch_module) -> str:
    if torch_module.cuda.is_available():
        return "cuda"
    if (
        hasattr(torch_module.backends, "mps")
        and torch_module.backends.mps.is_available()
    ):
        return "mps"
    return "cpu"


def _load_model(model_dir: Path, label_maps: Dict, train_meta: Dict, device: str):
    import torch
    import torch.nn as nn

    input_dim = int(train_meta["input_dim"])
    hidden_dim = int(train_meta["hidden_dim"])
    dropout = float(train_meta["dropout"])

    class MultiHeadModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_dim, hidden_dim),
                nn.ReLU(),
            )
            self.family_head = nn.Linear(hidden_dim, len(label_maps["family_to_idx"]))
            self.leaf_head = nn.Linear(hidden_dim, len(label_maps["leaf_to_idx"]))
            self.dim_heads = nn.ModuleDict(
                {
                    dim: nn.Linear(hidden_dim, len(class_map))
                    for dim, class_map in label_maps["dim_to_idx"].items()
                }
            )

        def forward(self, features):
            z = self.backbone(features)
            out = {"family": self.family_head(z), "leaf": self.leaf_head(z)}
            for dim_name, head in self.dim_heads.items():
                out[dim_name] = head(z)
            return out

    model = MultiHeadModel()
    model.load_state_dict(
        torch.load(model_dir / "trained_encoder.pt", map_location=torch.device(device))
    )
    model = model.to(device)
    model.eval()
    return model


def _concat_outputs(
    outputs: Dict[str, Any], dim_order: List[str], feature_space: str
) -> np.ndarray:
    if feature_space == "family":
        return outputs["family"].detach().cpu().numpy().astype(np.float32)
    parts = [
        outputs["family"].detach().cpu().numpy(),
        outputs["leaf"].detach().cpu().numpy(),
    ]
    for dim in dim_order:
        parts.append(outputs[dim].detach().cpu().numpy())
    return np.concatenate(parts, axis=1).astype(np.float32)


def _to_representation(features: np.ndarray, representation: str) -> np.ndarray:
    if representation == "logits":
        return features
    x = features - features.max(axis=1, keepdims=True)
    ex = np.exp(x)
    den = ex.sum(axis=1, keepdims=True)
    den[den == 0.0] = 1.0
    return (ex / den).astype(np.float32)


def _joint_tsne(
    features: np.ndarray, perplexity: float, random_state: int
) -> np.ndarray:
    from sklearn.manifold import TSNE

    n = features.shape[0]
    if n < 4:
        raise ValueError(f"Need at least 4 points for t-SNE, got {n}")
    perp = max(1.0, min(float(perplexity), (n - 1) * 0.99))
    tsne = TSNE(
        n_components=2,
        metric="cosine",
        perplexity=perp,
        init="pca",
        learning_rate="auto",
        random_state=random_state,
    )
    return tsne.fit_transform(features)


def _write_instruction_png(
    points: List[Dict[str, Any]], out_path: Path, title: str
) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
    except ImportError as exc:
        raise ImportError(
            "matplotlib is required for t-SNE PNG plots. Run: pip install matplotlib"
        ) from exc

    fig, ax = plt.subplots(figsize=(12, 7), dpi=120)
    for fam, col in FAMILY_COLORS.items():
        fam_pts = [p for p in points if p["group"] == fam]
        if not fam_pts:
            continue
        xs = [p["x"] for p in fam_pts]
        ys = [p["y"] for p in fam_pts]
        ax.scatter(
            xs,
            ys,
            s=24,
            c=col,
            alpha=0.85,
            edgecolors="#111111",
            linewidths=0.5,
            label=fam,
        )

    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=c,
            markeredgecolor="#111111",
            markersize=8,
            label=n,
        )
        for n, c in FAMILY_COLORS.items()
    ]
    ax.legend(handles=handles, loc="best", frameon=True, fontsize=9)
    ax.set_title(title)
    ax.set_xlabel("t-SNE 1")
    ax.set_ylabel("t-SNE 2")
    ax.grid(False)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def visualize_instruction_tsne_for_model(
    config: Dict[str, Any], model_cfg: Dict[str, Any]
) -> Path:
    import torch

    model_dir = output_dir_for_model(config, model_cfg)
    for name in (
        "trained_encoder.pt",
        "label_maps.json",
        "training_metadata.json",
        "emotion_embeddings.json",
    ):
        p = model_dir / name
        if not p.is_file():
            raise FileNotFoundError(
                f"Missing {p}; run train_encoder (and encode_emotions) first."
            )

    label_maps = json.loads((model_dir / "label_maps.json").read_text(encoding="utf-8"))
    train_meta = json.loads(
        (model_dir / "training_metadata.json").read_text(encoding="utf-8")
    )
    emotions_payload = json.loads(
        (model_dir / "emotion_embeddings.json").read_text(encoding="utf-8")
    )
    dim_order = list(label_maps["dim_to_idx"].keys())

    x_instruction = np.array(
        [row["vector"] for row in emotions_payload["records"]], dtype=np.float32
    )
    device = _select_device(torch)
    model = _load_model(model_dir, label_maps, train_meta, device)
    print(f"[instruction-only-tsne] device={device}")

    with torch.no_grad():
        out_instruction = model(torch.tensor(x_instruction, device=device))

    vis = config.get("visualization", {}) or {}
    feature_space = (
        str(vis.get("instruction_task_feature_space", "family")).strip().lower()
    )
    if feature_space not in ("family", "all_heads"):
        feature_space = "family"
    representation = (
        str(vis.get("instruction_task_representation", "probs")).strip().lower()
    )
    if representation not in ("probs", "logits"):
        representation = "probs"

    f_instruction = _concat_outputs(
        out_instruction, dim_order=dim_order, feature_space=feature_space
    )
    if representation == "probs":
        if feature_space == "family":
            f_instruction = _to_representation(f_instruction, "probs")
        else:
            fam_i = _to_representation(
                out_instruction["family"].detach().cpu().numpy(), "probs"
            )
            leaf_i = _to_representation(
                out_instruction["leaf"].detach().cpu().numpy(), "probs"
            )
            dim_i = [
                _to_representation(out_instruction[d].detach().cpu().numpy(), "probs")
                for d in dim_order
            ]
            f_instruction = np.concatenate([fam_i, leaf_i] + dim_i, axis=1).astype(
                np.float32
            )

    perplexity = float(vis.get("instruction_task_tsne_perplexity", 30))
    random_state = int(vis.get("instruction_task_tsne_random_state", 42))
    xy = _joint_tsne(f_instruction, perplexity=perplexity, random_state=random_state)

    rows: List[Dict[str, Any]] = []
    for i, rec in enumerate(emotions_payload["records"]):
        rows.append(
            {
                "kind": "instruction_model_output",
                "label": rec.get("instruction_id", rec.get("item_id", str(i))),
                "group": str(rec["spec"]["emotion_family"]).lower(),
                "x": float(xy[i, 0]),
                "y": float(xy[i, 1]),
            }
        )

    out_dir = model_dir / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    points_path = out_dir / "instruction_model_output_tsne_points.json"
    png_path = out_dir / "instruction_model_output_tsne.png"
    meta_path = out_dir / "instruction_model_output_tsne_meta.json"

    points_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    _write_instruction_png(
        rows,
        png_path,
        title=f"instruction-only model-output t-SNE ({feature_space}, {representation})",
    )
    meta_path.write_text(
        json.dumps(
            {
                "kind": "instruction_model_output_tsne",
                "n_instruction_points": len(rows),
                "feature_space": feature_space,
                "representation": representation,
                "feature_dim": int(f_instruction.shape[1]),
                "perplexity": perplexity,
                "random_state": random_state,
                "points_json": str(points_path),
                "plot_png": str(png_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return png_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot instruction-only t-SNE from trained novel emotion encoder."
    )
    parser.add_argument("--config", default="emotion_analysis/config.json")
    args = parser.parse_args()

    config = load_config(args.config)
    model_cfg = get_embedding_model_cfg(config)
    out = visualize_instruction_tsne_for_model(config, model_cfg)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

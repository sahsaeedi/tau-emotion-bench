"""
Instruction vs task t-SNE with kNN decision regions in 2D t-SNE space.

Regions and task marker colors both come from the same KNeighborsClassifier
fit on instruction (x, y) with true emotion families.

Run from repo root (recommended):
  python3 emotion_analysis/visualize_instruction_vs_task_tsne_knn_regions.py --config emotion_analysis/config.json

Or from emotion_analysis/ (uses local ``config.json`` if the default path is missing):
  cd emotion_analysis && python3 visualize_instruction_vs_task_tsne_knn_regions.py --config config.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from utils import (
    encode_texts,
    format_task_skip_line,
    get_embedding_model_cfg,
    l2_normalize_rows,
    load_config,
    load_encoder_knn_models,
    output_dir_for_model,
    resolve_project_path,
    task_embedding_text,
)

FAMILY_COLORS: Dict[str, str] = {
    "anger": "#e15759",
    "fear": "#4e79a7",
    "disgust": "#b07aa1",
    "sadness": "#9c755f",
    "enjoyment": "#f28e2b",
}


def _hex_to_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array(
        [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)], dtype=np.float64
    )


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


def _plot_extent_with_tasks(
    xy_instruction: np.ndarray,
    task_rows: List[Dict[str, Any]],
    pad_frac: float,
) -> Tuple[float, float, float, float]:
    if task_rows:
        all_xy = np.vstack(
            [
                xy_instruction,
                np.array([[r["x"], r["y"]] for r in task_rows], dtype=np.float64),
            ]
        )
    else:
        all_xy = xy_instruction
    min_x, max_x = float(all_xy[:, 0].min()), float(all_xy[:, 0].max())
    min_y, max_y = float(all_xy[:, 1].min()), float(all_xy[:, 1].max())
    dx = max_x - min_x
    dy = max_y - min_y
    pad = max(dx, dy, 1e-6) * pad_frac
    return min_x - pad, max_x + pad, min_y - pad, max_y + pad


def _fit_tsne_family_knn(
    xy_instruction: np.ndarray,
    families_instruction: List[str],
    k_neighbors: int,
):
    from sklearn.neighbors import KNeighborsClassifier

    n = len(xy_instruction)
    if n < 1:
        raise ValueError("Need at least one instruction point for t-SNE kNN.")
    k_req = max(3, int(k_neighbors))
    k_eff = max(1, min(k_req, n))
    y = np.array([str(f).lower() for f in families_instruction], dtype=object)
    clf = KNeighborsClassifier(
        n_neighbors=k_eff, metric="euclidean", weights="distance"
    )
    clf.fit(xy_instruction.astype(np.float64), y)
    return clf, k_eff


def _write_png_tsne_knn_regions(
    clf,
    k_eff: int,
    xy_instruction: np.ndarray,
    task_rows: List[Dict[str, Any]],
    out_path: Path,
    *,
    feature_space: str,
    representation: str,
    grid_n: int = 88,
    pad_frac: float = 0.06,
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

    min_x, max_x, min_y, max_y = _plot_extent_with_tasks(
        xy_instruction, task_rows, pad_frac
    )
    span_x = max_x - min_x
    span_y = max_y - min_y
    cx = min_x + (np.arange(grid_n, dtype=np.float64) + 0.5) / grid_n * span_x
    cy = min_y + (np.arange(grid_n, dtype=np.float64) + 0.5) / grid_n * span_y
    xc, yc = np.meshgrid(cx, cy)
    grid_xy = np.stack([xc.ravel(), yc.ravel()], axis=1)
    preds = clf.predict(grid_xy)
    rgb = np.array(
        [_hex_to_rgb(FAMILY_COLORS.get(str(p).lower(), "#777777")) for p in preds],
        dtype=np.float32,
    )
    heat = (rgb / 255.0).reshape(grid_n, grid_n, 3)

    fig, ax = plt.subplots(figsize=(12, 7), dpi=120)
    ax.imshow(
        heat,
        extent=[min_x, max_x, min_y, max_y],
        origin="lower",
        alpha=0.92,
        interpolation="nearest",
    )
    if task_rows:
        xs = np.array([r["x"] for r in task_rows], dtype=np.float32)
        ys = np.array([r["y"] for r in task_rows], dtype=np.float32)
        cs = [FAMILY_COLORS.get(str(r["group"]).lower(), "#777777") for r in task_rows]
        sizes = [
            24.0 + 140.0 * min(1.0, max(0.0, float(r.get("family_max_prob", 0.5))))
            for r in task_rows
        ]
        ax.scatter(
            xs, ys, s=sizes, c=cs, alpha=0.9, edgecolors="#111111", linewidths=0.9
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
    ax.legend(handles=handles, loc="upper right", frameon=True, fontsize=9)
    ax.set_title(
        f"instruction vs task t-SNE — kNN regions ({feature_space}, {representation}; k={k_eff})"
    )
    ax.set_xlabel("t-SNE 1")
    ax.set_ylabel("t-SNE 2")
    ax.grid(False)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def visualize_instruction_vs_task_tsne_knn_regions_for_model(
    config: Dict[str, Any], model_cfg: Dict[str, Any]
) -> List[Path]:
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
    n_instruction = len(emotions_payload["records"])
    families_instruction = [
        str(rec["spec"]["emotion_family"]).lower()
        for rec in emotions_payload["records"]
    ]

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
    perplexity = float(vis.get("instruction_task_tsne_perplexity", 30))
    random_state = int(vis.get("instruction_task_tsne_random_state", 42))
    grid_n = int(
        vis.get(
            "instruction_task_heatmap_grid", vis.get("learned_tsne_heatmap_grid", 88)
        )
    )
    k_nb = int(
        vis.get("instruction_task_heatmap_k", vis.get("learned_tsne_heatmap_k", 18))
    )
    cap = vis.get("max_tasks")

    device = _select_device(torch)
    model = _load_model(model_dir, label_maps, train_meta, device)
    print(f"[instruction-vs-task-tsne-knn-regions] device={device}")
    knn_models = load_encoder_knn_models(model_dir)

    if knn_models and feature_space == "family":
        with torch.no_grad():
            z_i = (
                model.backbone(torch.tensor(x_instruction, device=device))
                .detach()
                .cpu()
                .numpy()
                .astype(np.float32)
            )
        f_instruction = l2_normalize_rows(z_i)
        use_knn = True
    else:
        with torch.no_grad():
            out_instruction = model(torch.tensor(x_instruction, device=device))
        f_instr_raw = _concat_outputs(
            out_instruction, dim_order=dim_order, feature_space=feature_space
        )
        if representation == "probs":
            if feature_space == "family":
                f_instruction = _to_representation(f_instr_raw, "probs")
            else:
                fam_i = _to_representation(
                    out_instruction["family"].detach().cpu().numpy(), "probs"
                )
                leaf_i = _to_representation(
                    out_instruction["leaf"].detach().cpu().numpy(), "probs"
                )
                dim_i = [
                    _to_representation(
                        out_instruction[d].detach().cpu().numpy(), "probs"
                    )
                    for d in dim_order
                ]
                f_instruction = np.concatenate([fam_i, leaf_i] + dim_i, axis=1).astype(
                    np.float32
                )
        else:
            f_instruction = f_instr_raw
        use_knn = False

    out_dir = model_dir / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_paths: List[Path] = []

    for task_path_str in config["inputs"]["task_paths"]:
        task_path = resolve_project_path(task_path_str)
        tasks = json.loads(task_path.read_text(encoding="utf-8"))

        texts: List[str] = []
        meta: List[str] = []
        skipped_here = 0
        for i, task in enumerate(tasks):
            t = task_embedding_text(task)
            if not str(t).strip():
                print(format_task_skip_line(task_path, i, task))
                skipped_here += 1
                continue
            texts.append(t)
            meta.append(f"{task_path.name}:{task.get('task_id', i)}")
        if skipped_here:
            print(
                f"[instruction-vs-task-tsne-knn-regions] Skipped {skipped_here} task(s) in {task_path.name} "
                "(empty embed text; omitted from plot)."
            )

        if cap not in (None, "", "all", "ALL", 0, -1):
            cap_int = int(cap)
            texts = texts[:cap_int]
            meta = meta[:cap_int]

        if not texts:
            print(
                f"[instruction-vs-task-tsne-knn-regions] No tasks to plot for {task_path.name}, skipping."
            )
            continue

        x_task = encode_texts(dict(model_cfg), texts).astype(np.float32)

        if use_knn:
            with torch.no_grad():
                z_t = (
                    model.backbone(torch.tensor(x_task, device=device))
                    .detach()
                    .cpu()
                    .numpy()
                    .astype(np.float32)
                )
            z_tn = l2_normalize_rows(z_t)
            all_features = np.vstack([f_instruction, z_tn])
            eff_representation = "backbone_l2+knn"
        else:
            with torch.no_grad():
                out_task = model(torch.tensor(x_task, device=device))
            f_task_raw = _concat_outputs(
                out_task, dim_order=dim_order, feature_space=feature_space
            )
            if representation == "probs":
                if feature_space == "family":
                    f_task = _to_representation(f_task_raw, "probs")
                else:
                    fam_t = _to_representation(
                        out_task["family"].detach().cpu().numpy(), "probs"
                    )
                    leaf_t = _to_representation(
                        out_task["leaf"].detach().cpu().numpy(), "probs"
                    )
                    dim_t = [
                        _to_representation(out_task[d].detach().cpu().numpy(), "probs")
                        for d in dim_order
                    ]
                    f_task = np.concatenate([fam_t, leaf_t] + dim_t, axis=1).astype(
                        np.float32
                    )
            else:
                f_task = f_task_raw
            all_features = np.vstack([f_instruction, f_task])
            eff_representation = representation

        xy = _joint_tsne(all_features, perplexity=perplexity, random_state=random_state)
        xy_instruction_plot = xy[:n_instruction]
        xy_task = xy[n_instruction:]

        clf_tsne, k_tsne_eff = _fit_tsne_family_knn(
            xy_instruction_plot, families_instruction, k_nb
        )

        rows: List[Dict[str, Any]] = []
        for i, rec in enumerate(emotions_payload["records"]):
            rows.append(
                {
                    "kind": "instruction_model_output",
                    "label": rec.get("instruction_id", rec.get("item_id", str(i))),
                    "group": str(rec["spec"]["emotion_family"]).lower(),
                    "x": float(xy_instruction_plot[i, 0]),
                    "y": float(xy_instruction_plot[i, 1]),
                }
            )

        task_rows_plot: List[Dict[str, Any]] = []
        for i, label in enumerate(meta):
            xy_one = xy_task[i : i + 1].astype(np.float64)
            proba_vec = clf_tsne.predict_proba(xy_one)[0]
            classes = [str(c).lower() for c in clf_tsne.classes_]
            bi = int(np.argmax(proba_vec))
            fam = classes[bi]
            probs = {classes[j]: float(proba_vec[j]) for j in range(len(classes))}
            pmax = float(proba_vec[bi])
            row = {
                "kind": "task_model_output",
                "label": label,
                "group": fam,
                "x": float(xy_task[i, 0]),
                "y": float(xy_task[i, 1]),
                "family_probs": probs,
                "family_max_prob": pmax,
            }
            rows.append(row)
            task_rows_plot.append(row)

        stem = task_path.stem
        suffix = "_tsne_knn_regions"
        points_path = out_dir / f"instruction_vs_{stem}{suffix}_points.json"
        png_path = out_dir / f"instruction_vs_{stem}{suffix}.png"
        meta_out_path = out_dir / f"instruction_vs_{stem}{suffix}_meta.json"

        points_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        _write_png_tsne_knn_regions(
            clf_tsne,
            k_tsne_eff,
            xy_instruction_plot,
            task_rows_plot,
            png_path,
            feature_space=feature_space,
            representation=eff_representation,
            grid_n=grid_n,
        )
        meta_out_path.write_text(
            json.dumps(
                {
                    "kind": "instruction_vs_task_tsne_knn_regions",
                    "task_file": str(task_path),
                    "n_instruction_points": n_instruction,
                    "n_task_points": len(texts),
                    "feature_space": feature_space,
                    "representation": eff_representation,
                    "feature_dim": int(all_features.shape[1]),
                    "perplexity": perplexity,
                    "random_state": random_state,
                    "region_mode": "tsne_knn",
                    "heatmap_grid": grid_n,
                    "heatmap_k_config": k_nb,
                    "tsne_knn_k_effective": k_tsne_eff,
                    "points_json": str(points_path),
                    "plot_png": str(png_path),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        out_paths.append(png_path)
        print(f"[instruction-vs-task-tsne-knn-regions] Wrote {png_path}")

    return out_paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="t-SNE instruction vs tasks with kNN decision regions in 2D (same kNN colors tasks and field)."
    )
    parser.add_argument("--config", default="emotion_analysis/config.json")
    args = parser.parse_args()

    config = load_config(args.config)
    model_cfg = get_embedding_model_cfg(config)
    out_paths = visualize_instruction_vs_task_tsne_knn_regions_for_model(
        config, model_cfg
    )
    for p in out_paths:
        print(f"Wrote {p}")


if __name__ == "__main__":
    main()

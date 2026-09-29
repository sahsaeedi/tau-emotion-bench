"""
t-SNE on the trained novel encoder's hidden representation z = backbone(x).

Stacks:
  - emotion rows: x from emotion_embeddings.json (same inputs as training)
  - tasks: x from embedding task feeling / instruction text

Then joint TSNE(z). Background: IDW-blended heatmap from emotion instruction sites (no emotion dots).
Foreground: tasks sized/colored by family softmax from logits.
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

_FAMILY_COLORS: Dict[str, str] = {
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


def _rgb_to_hex(rgb: np.ndarray) -> str:
    x = np.clip(np.round(rgb), 0, 255).astype(int)
    return f"#{x[0]:02x}{x[1]:02x}{x[2]:02x}"


def _invert_map(mapping: Dict[str, int]) -> Dict[int, str]:
    return {int(v): k for k, v in mapping.items()}


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


def _backbone_features(
    model, x: np.ndarray, device: str, batch_size: int = 512
) -> np.ndarray:
    import torch

    out_list: List[np.ndarray] = []
    xt = torch.tensor(x.astype(np.float32), device=device)
    with torch.no_grad():
        for start in range(0, len(xt), batch_size):
            batch = xt[start : start + batch_size]
            z = model.backbone(batch)
            out_list.append(z.detach().cpu().numpy())
    return np.vstack(out_list)


def _joint_tsne(z: np.ndarray, perplexity: float, random_state: int) -> np.ndarray:
    from sklearn.manifold import TSNE

    n = z.shape[0]
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
    return tsne.fit_transform(z)


def _idw_cell_color(
    cx: float,
    cy: float,
    xy_sites: np.ndarray,
    families: List[str],
    k: int,
    power: float,
) -> str:
    dist = np.linalg.norm(xy_sites - np.array([cx, cy], dtype=np.float64), axis=1)
    dist = np.maximum(dist, 1e-10)
    if len(dist) <= k:
        idx = np.arange(len(dist))
    else:
        idx = np.argpartition(dist, k)[:k]
    w = 1.0 / (dist[idx] ** power)
    w /= w.sum()
    rgb = np.zeros(3, dtype=np.float64)
    for wi, j in zip(w, idx):
        fam = str(families[j]).lower()
        rgb += wi * _hex_to_rgb(_FAMILY_COLORS.get(fam, "#777777"))
    return _rgb_to_hex(rgb)


def _write_png_heatmap_tasks(
    xy_em: np.ndarray,
    families_em: List[str],
    task_rows: List[Dict[str, Any]],
    out_path: Path,
    *,
    grid_n: int = 88,
    k_neighbors: int = 18,
    idw_power: float = 2.0,
    pad_frac: float = 0.06,
) -> None:
    """Heatmap from emotion t-SNE sites; save static PNG with task markers."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
    except ImportError as exc:
        raise ImportError(
            "matplotlib is required for t-SNE PNG plots. Run: pip install matplotlib"
        ) from exc

    all_xy = (
        np.vstack(
            [xy_em, np.array([[r["x"], r["y"]] for r in task_rows], dtype=np.float64)]
        )
        if task_rows
        else xy_em
    )
    min_x, max_x = float(all_xy[:, 0].min()), float(all_xy[:, 0].max())
    min_y, max_y = float(all_xy[:, 1].min()), float(all_xy[:, 1].max())
    dx = max_x - min_x
    dy = max_y - min_y
    pad_x = max(dx, dy, 1e-6) * pad_frac
    pad_y = max(dx, dy, 1e-6) * pad_frac
    min_x -= pad_x
    max_x += pad_x
    min_y -= pad_y
    max_y += pad_y

    heat = np.zeros((grid_n, grid_n, 3), dtype=np.float32)
    k_cell = min(k_neighbors, len(families_em)) if families_em else 1
    for i in range(grid_n):
        for j in range(grid_n):
            x0 = min_x + (i / grid_n) * (max_x - min_x)
            x1 = min_x + ((i + 1) / grid_n) * (max_x - min_x)
            y0 = min_y + (j / grid_n) * (max_y - min_y)
            y1 = min_y + ((j + 1) / grid_n) * (max_y - min_y)
            cx = (x0 + x1) / 2
            cy = (y0 + y1) / 2
            fill = _idw_cell_color(cx, cy, xy_em, families_em, k_cell, idw_power)
            heat[j, i, :] = (_hex_to_rgb(fill) / 255.0).astype(np.float32)

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
        cs = [_FAMILY_COLORS.get(str(r["group"]).lower(), "#777777") for r in task_rows]
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
        for n, c in _FAMILY_COLORS.items()
    ]
    ax.legend(handles=handles, loc="upper right", frameon=True, fontsize=9)
    ax.set_title("learned-space t-SNE (emotion heatmap + task logits)")
    ax.set_xlabel("t-SNE 1")
    ax.set_ylabel("t-SNE 2")
    ax.grid(False)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def visualize_learned_tsne_for_model(
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

    family_from_idx = _invert_map(label_maps["family_to_idx"])

    device = _select_device(torch)
    model = _load_model(model_dir, label_maps, train_meta, device)
    print(f"[learned-tsne] device={device}")

    emotion_records = emotions_payload["records"]
    x_em = np.array([r["vector"] for r in emotion_records], dtype=np.float32)
    z_em = _backbone_features(model, x_em, device)

    texts: List[str] = []
    meta: List[Tuple[str, str]] = []  # source file, task_id or index
    for task_path_str in config["inputs"]["task_paths"]:
        task_path = resolve_project_path(task_path_str)
        tasks = json.loads(task_path.read_text(encoding="utf-8"))
        skipped_here = 0
        for i, task in enumerate(tasks):
            t = task_embedding_text(task)
            if not str(t).strip():
                print(format_task_skip_line(task_path, i, task))
                skipped_here += 1
                continue
            texts.append(t)
            meta.append((task_path.name, str(task.get("task_id", i))))
        if skipped_here:
            print(
                f"[learned-tsne] Skipped {skipped_here} task(s) in {task_path.name} "
                "(empty embed text; omitted from plot)."
            )

    vis = config.get("visualization") or {}
    if "learned_tsne_max_tasks" in vis:
        cap = vis["learned_tsne_max_tasks"]
        if cap not in (None, "", "all", "ALL", 0, -1):
            cap = int(cap)
            texts = texts[:cap]
            meta = meta[:cap]

    if not texts:
        raise ValueError("No task texts found in config inputs.task_paths")

    model_cfg_infer = dict(model_cfg)
    x_task = encode_texts(model_cfg_infer, texts).astype(np.float32)
    z_task = _backbone_features(model, x_task, device)

    z_all = np.vstack([z_em, z_task])
    perp = float(vis.get("learned_tsne_perplexity", vis.get("tsne_perplexity", 30)))
    rs = int(vis.get("learned_tsne_random_state", vis.get("random_state", 42)))
    xy = _joint_tsne(z_all, perplexity=perp, random_state=rs)

    n_em = len(emotion_records)
    xy_em = xy[:n_em]
    xy_task = xy[n_em:]

    rows: List[Dict[str, Any]] = []
    for i, rec in enumerate(emotion_records):
        fam = rec["spec"]["emotion_family"]
        rows.append(
            {
                "kind": "emotion",
                "label": rec.get("instruction_id", rec.get("item_id", str(i))),
                "group": fam,
                "x": float(xy_em[i, 0]),
                "y": float(xy_em[i, 1]),
            }
        )

    import torch.nn.functional as F

    knn_models = load_encoder_knn_models(model_dir)
    z_task_n = l2_normalize_rows(z_task)
    if knn_models:
        fc = knn_models["family"]
        fam_probs_t = np.stack(
            [fc.predict_proba(z_task_n[j : j + 1])[0] for j in range(len(z_task_n))]
        )
        n_fam = fam_probs_t.shape[1]
    else:
        xt = torch.tensor(x_task.astype(np.float32), device=device)
        with torch.no_grad():
            fam_logits = model(xt)["family"]
            fam_probs_t = F.softmax(fam_logits, dim=1).detach().cpu().numpy()
        pred_idx = np.argmax(fam_probs_t, axis=1)
        n_fam = fam_probs_t.shape[1]

    task_rows_plot: List[Dict[str, Any]] = []
    for i, (src, tid) in enumerate(meta):
        if knn_models:
            classes = knn_models["family"].classes_
            bi = int(np.argmax(fam_probs_t[i]))
            fam_label_idx = int(classes[bi])
            fam = family_from_idx[fam_label_idx]
            probs = {
                family_from_idx[int(classes[k])]: float(fam_probs_t[i, k])
                for k in range(len(classes))
            }
            pmax = float(fam_probs_t[i][bi])
        else:
            fam = family_from_idx[int(pred_idx[i])]
            probs = {family_from_idx[j]: float(fam_probs_t[i, j]) for j in range(n_fam)}
            pmax = float(fam_probs_t[i, pred_idx[i]])
        row = {
            "kind": "task",
            "label": f"{src}:{tid}",
            "group": fam,
            "x": float(xy_task[i, 0]),
            "y": float(xy_task[i, 1]),
            "family_probs": probs,
            "family_max_prob": pmax,
        }
        rows.append(row)
        task_rows_plot.append(row)

    families_em = [
        str(rec["spec"]["emotion_family"]).lower() for rec in emotion_records
    ]
    grid_n = int(vis.get("learned_tsne_heatmap_grid", 88))
    k_nb = int(vis.get("learned_tsne_heatmap_k", 18))
    idw_p = float(vis.get("learned_tsne_idw_power", 2.0))

    out_dir = model_dir / "analysis"
    json_path = out_dir / "learned_space_tsne_points.json"
    png_path = out_dir / "learned_space_tsne.png"
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    _write_png_heatmap_tasks(
        xy_em,
        families_em,
        task_rows_plot,
        png_path,
        grid_n=grid_n,
        k_neighbors=max(3, k_nb),
        idw_power=idw_p,
    )

    sidecar = {
        "kind": "novel_learned_tsne",
        "hidden_dim": z_em.shape[1],
        "n_emotion": n_em,
        "n_task": len(texts),
        "perplexity": perp,
        "random_state": rs,
        "heatmap_grid": grid_n,
        "heatmap_k": k_nb,
        "idw_power": idw_p,
        "points_json": str(json_path),
        "plot_png": str(png_path),
    }
    (out_dir / "learned_space_tsne_meta.json").write_text(
        json.dumps(sidecar, indent=2), encoding="utf-8"
    )
    return png_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="t-SNE plot of novel encoder backbone features."
    )
    parser.add_argument("--config", default="emotion_analysis/config.json")
    args = parser.parse_args()
    config = load_config(args.config)
    model_cfg = get_embedding_model_cfg(config)
    out = visualize_learned_tsne_for_model(config, model_cfg)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

"""
Combined grid of the per-domain instruction-vs-task t-SNE kNN region plots
(one panel per file in inputs.task_paths, up to 5 per row), built from the
*_points.json / *_meta.json that run_all.py saved (no re-embedding, no
retraining), with white task markers and one shared legend for the figure.

Run from tracer/ after run_all.py:
  python3 emotion_analysis/visualize_combined_grid.py --config emotion_analysis/config.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from utils import get_embedding_model_cfg, load_config, output_dir_for_model

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


def _load_domain(
    analysis_dir: Path, stem: str
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    prefix = analysis_dir / f"instruction_vs_{stem}_tsne_knn_regions"
    meta = json.loads(Path(f"{prefix}_meta.json").read_text())
    points = json.loads(Path(f"{prefix}_points.json").read_text())
    return meta, points


def _plot_extent(
    xy_instruction: np.ndarray, xy_task: np.ndarray, pad_frac: float = 0.06
):
    all_xy = np.vstack([xy_instruction, xy_task]) if len(xy_task) else xy_instruction
    min_x, max_x = float(all_xy[:, 0].min()), float(all_xy[:, 0].max())
    min_y, max_y = float(all_xy[:, 1].min()), float(all_xy[:, 1].max())
    dx, dy = max_x - min_x, max_y - min_y
    pad = max(dx, dy, 1e-6) * pad_frac
    return min_x - pad, max_x + pad, min_y - pad, max_y + pad


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combine the per-domain t-SNE kNN region plots into one grid."
    )
    parser.add_argument("--config", default="emotion_analysis/config.json")
    args = parser.parse_args()

    config = load_config(args.config)
    analysis_dir = output_dir_for_model(config, get_embedding_model_cfg(config))
    analysis_dir = analysis_dir / "analysis"
    # Same stems as visualize_instruction_vs_task_tsne_knn_regions.py, e.g.
    # "bank_test_passed_tasks" -> panel title "Bank".
    stems = [Path(p).stem for p in config["inputs"]["task_paths"]]
    ncols = min(5, len(stems))
    nrows = math.ceil(len(stems) / ncols)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from scipy import ndimage
    from sklearn.neighbors import KNeighborsClassifier

    fig, axes = plt.subplots(
        nrows, ncols, figsize=(3.2 * ncols, 2.1 * nrows), dpi=140, squeeze=False
    )
    fig.subplots_adjust(wspace=0.12, hspace=0.38)
    axes = axes.ravel()
    for ax in axes[len(stems) :]:
        ax.set_visible(False)

    for ax, stem in zip(axes, stems):
        title = stem.split("_")[0].capitalize()
        meta, points = _load_domain(analysis_dir, stem)
        grid_n = int(meta["heatmap_grid"])
        k_eff = int(meta["tsne_knn_k_effective"])

        inst = [p for p in points if p["kind"] == "instruction_model_output"]
        task = [p for p in points if p["kind"] == "task_model_output"]

        xy_instruction = np.array([[p["x"], p["y"]] for p in inst], dtype=np.float64)
        families_instruction = np.array(
            [str(p["group"]).lower() for p in inst], dtype=object
        )
        xy_task = np.array([[p["x"], p["y"]] for p in task], dtype=np.float64)

        clf = KNeighborsClassifier(
            n_neighbors=k_eff, metric="euclidean", weights="distance"
        )
        clf.fit(xy_instruction, families_instruction)

        min_x, max_x, min_y, max_y = _plot_extent(xy_instruction, xy_task)
        span_x, span_y = max_x - min_x, max_y - min_y
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

        ax.imshow(
            heat,
            extent=[min_x, max_x, min_y, max_y],
            origin="lower",
            alpha=0.92,
            interpolation="nearest",
            aspect="auto",
        )

        # Black border around each connected region that contains at least one task point.
        pred_grid = preds.reshape(grid_n, grid_n)
        if len(xy_task):
            task_ix = np.clip(
                ((xy_task[:, 0] - min_x) / span_x * grid_n).astype(int), 0, grid_n - 1
            )
            task_iy = np.clip(
                ((xy_task[:, 1] - min_y) / span_y * grid_n).astype(int), 0, grid_n - 1
            )
            for fam in np.unique(pred_grid):
                labels, _ = ndimage.label(pred_grid == fam)
                hit = set(
                    labels[task_iy, task_ix][
                        pred_grid[task_iy, task_ix] == fam
                    ].tolist()
                )
                for lab in hit:
                    ax.contour(
                        cx,
                        cy,
                        ndimage.binary_fill_holes(labels == lab).astype(float),
                        levels=[0.5],
                        colors="black",
                        linewidths=1.6,
                        zorder=2,
                    )
        if len(xy_task):
            ax.scatter(
                xy_task[:, 0],
                xy_task[:, 1],
                s=55,
                c="white",
                alpha=0.95,
                edgecolors="#111111",
                linewidths=0.9,
                zorder=3,
            )

        ax.set_title(title, fontsize=19, pad=4)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)

    handles = [
        Line2D(
            [0],
            [0],
            marker="s",
            color="w",
            markerfacecolor=c,
            markeredgecolor="none",
            markersize=16,
            label=n.capitalize(),
        )
        for n, c in FAMILY_COLORS.items()
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=len(FAMILY_COLORS),
        frameon=False,
        fontsize=16,
        bbox_to_anchor=(0.5, -0.08),
    )

    out_png = analysis_dir / "instruction_vs_task_tsne_knn_regions_grid.png"
    out_pdf = analysis_dir / "instruction_vs_task_tsne_knn_regions_grid.pdf"
    fig.savefig(out_png, bbox_inches="tight")
    fig.savefig(out_pdf, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_png}")
    print(f"Wrote {out_pdf}")


if __name__ == "__main__":
    main()

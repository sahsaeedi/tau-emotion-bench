import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from utils import get_embedding_model_cfg, load_config, output_dir_for_model


@dataclass
class LabelMaps:
    family_to_idx: Dict[str, int]
    leaf_to_idx: Dict[str, int]
    dim_to_idx: Dict[str, Dict[str, int]]


def build_label_maps(records: List[Dict], schema: Dict) -> LabelMaps:
    families = list(schema["customer_service_curated_hierarchy"].keys())
    family_to_idx = {name: i for i, name in enumerate(families)}

    leaves = []
    for _, leaf_list in schema["customer_service_curated_hierarchy"].items():
        leaves.extend(leaf_list)
    leaves = sorted(set(leaves))
    leaf_to_idx = {name: i for i, name in enumerate(leaves)}

    dim_to_idx = {}
    for dim_name, values in schema["generation_dimensions"].items():
        dim_to_idx[dim_name] = {v: i for i, v in enumerate(values)}

    return LabelMaps(
        family_to_idx=family_to_idx, leaf_to_idx=leaf_to_idx, dim_to_idx=dim_to_idx
    )


def stratified_split_by_family(
    y_family: np.ndarray, val_ratio: float, seed: int
) -> Tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    train_indices: List[int] = []
    val_indices: List[int] = []

    for family_id in sorted(set(y_family.tolist())):
        idx = np.where(y_family == family_id)[0]
        rng.shuffle(idx)
        n_val = max(1, int(round(len(idx) * val_ratio)))
        n_val = min(n_val, max(1, len(idx) - 1)) if len(idx) > 1 else 1
        val_indices.extend(idx[:n_val].tolist())
        train_indices.extend(idx[n_val:].tolist())

    if not train_indices:
        # Edge case fallback
        all_idx = np.arange(len(y_family))
        rng.shuffle(all_idx)
        split = max(1, int(round(len(all_idx) * (1.0 - val_ratio))))
        train_indices = all_idx[:split].tolist()
        val_indices = all_idx[split:].tolist()

    return np.array(train_indices, dtype=np.int64), np.array(
        val_indices, dtype=np.int64
    )


def accuracy_from_logits(logits, targets) -> float:
    pred = logits.argmax(dim=1)
    return float((pred == targets).float().mean().item())


def write_learning_curves(history: List[Dict], out_dir: Path) -> Tuple[Path, Path]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError(
            "matplotlib is required for learning curve plots. Run: pip install matplotlib"
        ) from exc

    curves_csv = out_dir / "learning_curves.csv"
    curves_png = out_dir / "learning_curves.png"
    df = pd.DataFrame(history)
    df.to_csv(curves_csv, index=False)

    if df.empty:
        return curves_csv, curves_png

    loss_metrics = [m for m in ("train_loss", "val_loss") if m in df.columns]
    acc_metrics = [
        m
        for m in (
            "val_family_acc",
            "val_leaf_acc",
            "val_politeness_acc",
            "val_urgency_acc",
            "val_trust_in_agent_acc",
        )
        if m in df.columns
    ]

    n_panels = (1 if loss_metrics else 0) + (1 if acc_metrics else 0)
    if n_panels == 0:
        return curves_csv, curves_png

    fig, axes = plt.subplots(1, n_panels, figsize=(7 * n_panels, 4), dpi=120)
    if n_panels == 1:
        axes = [axes]

    epochs = df["epoch"].tolist()
    panel = 0

    if loss_metrics:
        ax = axes[panel]
        for m in loss_metrics:
            ax.plot(epochs, df[m].tolist(), marker="o", markersize=3, label=m)
        ax.set_title("Loss")
        ax.set_xlabel("Epoch")
        ax.set_ylabel("Loss")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        panel += 1

    if acc_metrics:
        ax = axes[panel]
        for m in acc_metrics:
            ax.plot(
                epochs,
                df[m].tolist(),
                marker="o",
                markersize=3,
                label=m.replace("val_", "").replace("_acc", ""),
            )
        ax.set_title("Validation Accuracy")
        ax.set_xlabel("Epoch")
        ax.set_ylabel("Accuracy")
        ax.set_ylim(0, 1.05)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    fig.suptitle("Learning Curves", fontsize=13)
    fig.tight_layout()
    fig.savefig(curves_png, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved learning curves → {curves_png}")
    return curves_csv, curves_png


def select_torch_device(torch_module) -> str:
    if torch_module.cuda.is_available():
        return "cuda"
    if (
        hasattr(torch_module.backends, "mps")
        and torch_module.backends.mps.is_available()
    ):
        return "mps"
    return "cpu"


def train_for_model(config: Dict, model_cfg: Dict) -> Path:
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
    except ImportError as exc:
        raise ImportError(
            "PyTorch is required. Install torch in your environment."
        ) from exc

    out_dir = output_dir_for_model(config, model_cfg)
    emb_path = out_dir / "emotion_embeddings.json"
    if not emb_path.is_file():
        raise FileNotFoundError(f"Missing embeddings: {emb_path}")

    payload = json.loads(emb_path.read_text(encoding="utf-8"))
    records = payload["records"]
    schema = json.loads(
        Path(config["inputs"]["emotion_schema_path"]).read_text(encoding="utf-8")
    )
    maps = build_label_maps(records, schema)

    x = np.array([row["vector"] for row in records], dtype=np.float32)
    y_family = np.array(
        [maps.family_to_idx[row["spec"]["emotion_family"]] for row in records],
        dtype=np.int64,
    )
    y_leaf = np.array(
        [maps.leaf_to_idx[row["spec"]["emotion_leaf"]] for row in records],
        dtype=np.int64,
    )
    y_dims = {
        dim: np.array(
            [maps.dim_to_idx[dim][row["spec"][dim]] for row in records], dtype=np.int64
        )
        for dim in maps.dim_to_idx
    }

    torch.manual_seed(int(config["training"].get("seed", 42)))
    random.seed(int(config["training"].get("seed", 42)))
    np.random.seed(int(config["training"].get("seed", 42)))

    hidden_dim = int(config["training"].get("hidden_dim", 256))
    dropout = float(config["training"].get("dropout", 0.15))
    epochs = int(config["training"].get("epochs", 30))
    batch_size = int(config["training"].get("batch_size", 128))
    lr = float(config["training"].get("lr", 1e-3))
    val_ratio = float(config["training"].get("val_split", 0.2))
    es_cfg = config["training"].get("early_stopping") or {}
    es_enabled = bool(es_cfg.get("enabled", False))
    es_patience = int(es_cfg.get("patience", 5))
    es_min_delta = float(es_cfg.get("min_delta", 0.0))

    input_dim = x.shape[1]

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
            self.family_head = nn.Linear(hidden_dim, len(maps.family_to_idx))
            self.leaf_head = nn.Linear(hidden_dim, len(maps.leaf_to_idx))
            self.dim_heads = nn.ModuleDict(
                {
                    dim: nn.Linear(hidden_dim, len(class_map))
                    for dim, class_map in maps.dim_to_idx.items()
                }
            )

        def forward(self, features):
            z = self.backbone(features)
            out = {
                "family": self.family_head(z),
                "leaf": self.leaf_head(z),
            }
            for dim_name, head in self.dim_heads.items():
                out[dim_name] = head(z)
            return out

    model = MultiHeadModel()
    device = select_torch_device(torch)
    model = model.to(device)
    print(f"Training device: {device}")
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    x_tensor = torch.tensor(x, device=device)
    y_family_t = torch.tensor(y_family, device=device)
    y_leaf_t = torch.tensor(y_leaf, device=device)
    y_dims_t = {k: torch.tensor(v, device=device) for k, v in y_dims.items()}

    train_idx, val_idx = stratified_split_by_family(
        y_family, val_ratio=val_ratio, seed=int(config["training"].get("seed", 42))
    )
    val_idx_t = torch.tensor(val_idx, dtype=torch.long, device=device)
    history: List[Dict] = []
    best_state = None
    best_epoch = 0
    best_score = -1.0
    epochs_without_improve = 0

    for epoch in range(1, epochs + 1):
        np.random.shuffle(train_idx)
        losses = []
        for start in range(0, len(train_idx), batch_size):
            batch_idx = train_idx[start : start + batch_size]
            batch_idx_t = torch.tensor(batch_idx, dtype=torch.long, device=device)
            xb = x_tensor[batch_idx_t]
            outputs = model(xb)
            loss = F.cross_entropy(outputs["family"], y_family_t[batch_idx_t])
            loss = loss + F.cross_entropy(outputs["leaf"], y_leaf_t[batch_idx_t])
            for dim_name in y_dims_t:
                loss = loss + F.cross_entropy(
                    outputs[dim_name], y_dims_t[dim_name][batch_idx_t]
                )

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(float(loss.item()))

        train_loss = float(np.mean(losses)) if losses else 0.0

        model.eval()
        with torch.no_grad():
            val_x = x_tensor[val_idx_t]
            val_out = model(val_x)
            val_loss = F.cross_entropy(val_out["family"], y_family_t[val_idx_t])
            val_loss = val_loss + F.cross_entropy(val_out["leaf"], y_leaf_t[val_idx_t])
            for dim_name in y_dims_t:
                val_loss = val_loss + F.cross_entropy(
                    val_out[dim_name], y_dims_t[dim_name][val_idx_t]
                )

            family_acc = accuracy_from_logits(val_out["family"], y_family_t[val_idx_t])
            leaf_acc = accuracy_from_logits(val_out["leaf"], y_leaf_t[val_idx_t])
            dim_acc = {
                dim_name: accuracy_from_logits(
                    val_out[dim_name], y_dims_t[dim_name][val_idx_t]
                )
                for dim_name in y_dims_t
            }

        model.train()
        avg_dim_acc = float(np.mean(list(dim_acc.values()))) if dim_acc else 0.0
        val_score = (family_acc + leaf_acc + avg_dim_acc) / 3.0
        improved = val_score > (best_score + es_min_delta)
        if improved:
            best_score = val_score
            best_epoch = epoch
            best_state = {
                k: v.detach().cpu().clone() for k, v in model.state_dict().items()
            }
            epochs_without_improve = 0
        else:
            epochs_without_improve += 1

        row = {
            "epoch": epoch,
            "train_loss": train_loss,
            "val_loss": float(val_loss.item()),
            "val_family_acc": family_acc,
            "val_leaf_acc": leaf_acc,
        }
        for dim_name, acc in dim_acc.items():
            row[f"val_{dim_name}_acc"] = acc
        history.append(row)

        dim_summary = " ".join([f"{k}={v:.3f}" for k, v in dim_acc.items()])
        print(
            f"Epoch {epoch:02d}/{epochs} train_loss={train_loss:.4f} "
            f"val_loss={float(val_loss.item()):.4f} "
            f"val_family={family_acc:.3f} val_leaf={leaf_acc:.3f} {dim_summary}"
        )

        if es_enabled and epochs_without_improve >= es_patience:
            print(
                f"Early stopping at epoch {epoch}: no val score improvement "
                f"for {epochs_without_improve} epochs (patience={es_patience})."
            )
            break

    if best_state is not None:
        model.load_state_dict(best_state)

    # kNN on L2-normalized backbone features (same space as encode_task_feelings when knn_models.pt is used)
    from sklearn.neighbors import KNeighborsClassifier

    def _l2_rows(a: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(a, axis=1, keepdims=True)
        n[n == 0] = 1.0
        return (a / n).astype(np.float32)

    knn_k = int(config["training"].get("knn_k", 7))
    knn_k_eff = max(1, min(knn_k, len(x)))

    model.eval()
    with torch.no_grad():
        z_all = model.backbone(x_tensor).detach().cpu().numpy().astype(np.float32)
    z_n = _l2_rows(z_all)

    knn_models: Dict[str, Any] = {}
    knn_models["family"] = KNeighborsClassifier(
        n_neighbors=knn_k_eff, metric="cosine", weights="distance"
    )
    knn_models["family"].fit(z_n, y_family)
    knn_models["leaf"] = KNeighborsClassifier(
        n_neighbors=knn_k_eff, metric="cosine", weights="distance"
    )
    knn_models["leaf"].fit(z_n, y_leaf)
    for dim_name, yv in y_dims.items():
        clf = KNeighborsClassifier(
            n_neighbors=knn_k_eff, metric="cosine", weights="distance"
        )
        clf.fit(z_n, yv)
        knn_models[dim_name] = clf

    knn_path = out_dir / "knn_models.pt"
    torch.save(knn_models, knn_path)
    print(f"Wrote kNN models (backbone space, k={knn_k_eff}) → {knn_path}")

    ckpt_path = out_dir / "trained_encoder.pt"
    label_maps_path = out_dir / "label_maps.json"
    train_meta_path = out_dir / "training_metadata.json"
    metrics_path = out_dir / "training_metrics.json"

    torch.save(model.state_dict(), ckpt_path)
    label_maps_path.write_text(
        json.dumps(
            {
                "family_to_idx": maps.family_to_idx,
                "leaf_to_idx": maps.leaf_to_idx,
                "dim_to_idx": maps.dim_to_idx,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    train_meta_path.write_text(
        json.dumps(
            {
                "input_dim": input_dim,
                "hidden_dim": hidden_dim,
                "dropout": dropout,
                "epochs": epochs,
                "batch_size": batch_size,
                "lr": lr,
                "val_split": val_ratio,
                "train_size": int(len(train_idx)),
                "val_size": int(len(val_idx)),
                "best_epoch": best_epoch,
                "best_val_score": best_score,
                "early_stopping": {
                    "enabled": es_enabled,
                    "patience": es_patience,
                    "min_delta": es_min_delta,
                },
                "knn_k": knn_k,
                "knn_k_effective": knn_k_eff,
                "knn_models_path": str(knn_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    metrics_path.write_text(
        json.dumps(
            {
                "best_epoch": best_epoch,
                "best_val_score": best_score,
                "early_stopping_enabled": es_enabled,
                "early_stopping_patience": es_patience,
                "early_stopping_min_delta": es_min_delta,
                "history": history,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    curves_csv, curves_png = write_learning_curves(history, out_dir)
    print(f"Wrote {curves_csv}")
    print(f"Wrote {curves_png}")
    return ckpt_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train PyTorch multi-head classifier on emotion embeddings."
    )
    parser.add_argument("--config", default="emotion_analysis/config.json")
    args = parser.parse_args()

    config = load_config(args.config)
    model_cfg = get_embedding_model_cfg(config)
    ckpt = train_for_model(config, model_cfg)
    print(f"Wrote {ckpt}")


if __name__ == "__main__":
    main()

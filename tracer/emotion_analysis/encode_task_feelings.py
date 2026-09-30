import argparse
import json
import random
from typing import Dict, List, Optional, Tuple

import numpy as np
from utils import (
    cosine_similarity,
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


def _invert_map(mapping: Dict[str, int]) -> Dict[int, str]:
    return {int(v): k for k, v in mapping.items()}


def select_torch_device(torch_module) -> str:
    if torch_module.cuda.is_available():
        return "cuda"
    if (
        hasattr(torch_module.backends, "mps")
        and torch_module.backends.mps.is_available()
    ):
        return "mps"
    return "cpu"


def _spec_key(spec: Dict[str, str]) -> Tuple[Tuple[str, str], ...]:
    return tuple(sorted((str(k), str(v)) for k, v in spec.items()))


def build_instruction_bank(
    emotion_rows: List[Dict],
) -> Dict[Tuple[Tuple[str, str], ...], List[Dict]]:
    """Group the persona instructions by their full spec (family, leaf, politeness, urgency, trust)."""
    bank: Dict[Tuple[Tuple[str, str], ...], List[Dict]] = {}
    for row in emotion_rows:
        bank.setdefault(_spec_key(row["spec"]), []).append(row)
    return bank


def pick_leaf_in_family(
    leaf_dist: Dict[str, float], family: str, family_leaves: Dict[str, List[str]]
) -> str:
    """Highest-probability leaf among the leaves that belong to the predicted family."""
    allowed = family_leaves[family]
    return max(allowed, key=lambda leaf: leaf_dist.get(leaf, 0.0))


def select_instruction(
    bank: Dict[Tuple[Tuple[str, str], ...], List[Dict]],
    spec: Dict[str, str],
    rng: random.Random,
) -> Optional[Dict]:
    """Pick one instruction at random from those written for exactly this spec."""
    candidates = bank.get(_spec_key(spec), [])
    if not candidates:
        return None
    row = rng.choice(candidates)
    return {
        "instruction_id": row["instruction_id"],
        "item_id": row["item_id"],
        "text": row["instruction_text"],
        "spec": dict(spec),
        "candidates": len(candidates),
        "selection": "random_within_predicted_spec",
    }


def _label_block(dist: Dict[str, float], label: str) -> Dict:
    return {"label": label, "score": float(dist.get(label, 0.0)), "distribution": dist}


def predict_for_model(config: Dict, model_cfg: Dict) -> Dict[str, str]:
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
    except ImportError as exc:
        raise ImportError(
            "PyTorch is required. Install torch in your environment."
        ) from exc

    model_dir = output_dir_for_model(config, model_cfg)
    label_maps = json.loads((model_dir / "label_maps.json").read_text(encoding="utf-8"))
    train_meta = json.loads(
        (model_dir / "training_metadata.json").read_text(encoding="utf-8")
    )
    emotions_payload = json.loads(
        (model_dir / "emotion_embeddings.json").read_text(encoding="utf-8")
    )
    schema = json.loads(
        resolve_project_path(config["inputs"]["emotion_schema_path"]).read_text(
            encoding="utf-8"
        )
    )
    family_leaves: Dict[str, List[str]] = schema["customer_service_curated_hierarchy"]

    family_from_idx = _invert_map(label_maps["family_to_idx"])
    leaf_from_idx = _invert_map(label_maps["leaf_to_idx"])
    dim_from_idx = {
        dim: _invert_map(class_map)
        for dim, class_map in label_maps["dim_to_idx"].items()
    }

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
    device = select_torch_device(torch)
    try:
        w = torch.load(
            model_dir / "trained_encoder.pt",
            map_location=torch.device(device),
            weights_only=True,
        )
    except TypeError:
        w = torch.load(
            model_dir / "trained_encoder.pt", map_location=torch.device(device)
        )
    model.load_state_dict(w)
    model = model.to(device)
    model.eval()
    knn_models = load_encoder_knn_models(model_dir)
    if knn_models:
        print(f"Inference device: {device} (task labels: backbone + kNN)")
    else:
        print(
            f"Inference device: {device} (task labels: classifier heads; no knn_models.pt)"
        )

    emotion_vectors = np.array(
        [row["vector"] for row in emotions_payload["records"]], dtype=float
    )
    emotion_rows = emotions_payload["records"]
    instruction_bank = build_instruction_bank(emotion_rows)
    selection_seed = int(
        config["inference"].get(
            "instruction_selection_seed", config["training"].get("seed", 42)
        )
    )

    output_suffix = config["inference"].get(
        "task_output_suffix", "_with_emotion_predictions.json"
    )
    written_paths: List[str] = []
    for task_path_str in config["inputs"]["task_paths"]:
        task_path = resolve_project_path(task_path_str)
        tasks = json.loads(task_path.read_text(encoding="utf-8"))
        encode_indices: List[int] = []
        texts: List[str] = []
        for i, task in enumerate(tasks):
            t = task_embedding_text(task)
            if not str(t).strip():
                print(format_task_skip_line(task_path, i, task))
                continue
            encode_indices.append(i)
            texts.append(t)

        no_instruction_n = 0
        if not encode_indices:
            print(
                f"No tasks to encode in {task_path} (all skipped); writing copy without novel_emotion_prediction."
            )
        else:
            vectors = encode_texts(model_cfg, texts).astype(np.float32)
            vt = torch.tensor(vectors, device=device)

            if knn_models:
                with torch.no_grad():
                    z = model.backbone(vt).detach().cpu().numpy().astype(np.float32)
                z_n = l2_normalize_rows(z)
                fam_probs = np.stack(
                    [
                        knn_models["family"].predict_proba(z_n[j : j + 1])[0]
                        for j in range(len(z_n))
                    ]
                )
                leaf_probs = np.stack(
                    [
                        knn_models["leaf"].predict_proba(z_n[j : j + 1])[0]
                        for j in range(len(z_n))
                    ]
                )
                dim_probs = {
                    dim_name: np.stack(
                        [
                            knn_models[dim_name].predict_proba(z_n[j : j + 1])[0]
                            for j in range(len(z_n))
                        ]
                    )
                    for dim_name in dim_from_idx
                }
                fam_classes = [int(c) for c in knn_models["family"].classes_]
                leaf_classes = [int(c) for c in knn_models["leaf"].classes_]
                dim_classes = {
                    dim_name: [int(c) for c in knn_models[dim_name].classes_]
                    for dim_name in dim_probs
                }
            else:
                with torch.no_grad():
                    outputs = model(vt)
                    fam_probs = (
                        F.softmax(outputs["family"], dim=1).detach().cpu().numpy()
                    )
                    leaf_probs = (
                        F.softmax(outputs["leaf"], dim=1).detach().cpu().numpy()
                    )
                    dim_probs = {
                        dim: F.softmax(logits, dim=1).detach().cpu().numpy()
                        for dim, logits in outputs.items()
                        if dim not in ("family", "leaf")
                    }
                fam_classes = list(range(fam_probs.shape[1]))
                leaf_classes = list(range(leaf_probs.shape[1]))
                dim_classes = {
                    dim_name: list(range(probs.shape[1]))
                    for dim_name, probs in dim_probs.items()
                }

            for j, orig_i in enumerate(encode_indices):
                task = tasks[orig_i]

                # Labels: family first, then the best leaf *within that family*, then each dimension.
                fam_dist = {
                    family_from_idx[c]: float(p)
                    for c, p in zip(fam_classes, fam_probs[j])
                }
                leaf_dist = {
                    leaf_from_idx[c]: float(p)
                    for c, p in zip(leaf_classes, leaf_probs[j])
                }
                family = max(fam_dist, key=fam_dist.get)
                leaf = pick_leaf_in_family(leaf_dist, family, family_leaves)
                dims = {}
                for dim_name, probs in dim_probs.items():
                    dist = {
                        dim_from_idx[dim_name][c]: float(p)
                        for c, p in zip(dim_classes[dim_name], probs[j])
                    }
                    dims[dim_name] = _label_block(dist, max(dist, key=dist.get))

                # Instruction: one random instruction written for exactly the predicted spec,
                # so the exported labels always describe the Emotion Instruction text.
                spec = {"emotion_family": family, "emotion_leaf": leaf}
                spec.update(
                    {dim_name: block["label"] for dim_name, block in dims.items()}
                )
                rng = random.Random(
                    f"{selection_seed}|{task_path.name}|{task.get('task_id')}|{task.get('run')}|{orig_i}"
                )
                selected = select_instruction(instruction_bank, spec, rng)
                if selected is None:
                    no_instruction_n += 1

                task_vec = vectors[j].astype(float)
                sims = [
                    (cosine_similarity(task_vec, emo_vec), row)
                    for row, emo_vec in zip(emotion_rows, emotion_vectors)
                ]
                sims.sort(key=lambda x: x[0], reverse=True)

                task["novel_emotion_prediction"] = {
                    "family": _label_block(fam_dist, family),
                    "leaf": _label_block(leaf_dist, leaf),
                    "generation_dimensions": dims,
                    "selected_instruction": selected,
                    # Reference only (nearest by embedding, ignores the predicted labels); not used for export.
                    "closest_instructions_top2": [
                        {
                            "instruction_id": row["instruction_id"],
                            "item_id": row["item_id"],
                            "similarity": float(score),
                            "text": row["instruction_text"],
                        }
                        for score, row in sims[:2]
                    ],
                }

        skipped_n = len(tasks) - len(encode_indices)
        if skipped_n:
            print(
                f"Skipped {skipped_n} task(s) in {task_path.name} (no embedding; no novel_emotion_prediction)."
            )
        if no_instruction_n:
            print(
                f"Warning: {no_instruction_n} task(s) in {task_path.name} have no instruction for their predicted spec."
            )

        out_path = task_path.with_name(f"{task_path.stem}{output_suffix}")
        out_path.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
        written_paths.append(str(out_path))
        print(f"Wrote {out_path}")

    summary_path = model_dir / "task_prediction_outputs.json"
    summary_path.write_text(
        json.dumps({"outputs": written_paths}, indent=2), encoding="utf-8"
    )
    return {"summary_path": str(summary_path)}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Encode task feelings and run trained novel emotion encoder."
    )
    parser.add_argument("--config", default="emotion_analysis/config.json")
    args = parser.parse_args()

    config = load_config(args.config)
    model_cfg = get_embedding_model_cfg(config)
    result = predict_for_model(config, model_cfg)
    print(f"Wrote {result['summary_path']}")


if __name__ == "__main__":
    main()

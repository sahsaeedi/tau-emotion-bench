import argparse
import json
from pathlib import Path
from typing import Dict, List

from utils import (
    encode_texts,
    ensure_parent,
    get_embedding_model_cfg,
    load_config,
    output_dir_for_model,
    resolve_project_path,
)


def build_training_text(spec: Dict[str, str], instruction_text: str) -> str:
    # Only embed the natural-language instruction text so the classifier learns
    # to detect emotional tone from language rather than from an explicit label
    # prefix (which never appears at inference time on task feelings).
    return instruction_text


def encode_emotions_for_model(config: Dict, model_cfg: Dict) -> Path:
    input_path = resolve_project_path(
        config["inputs"]["emotion_persona_instructions_path"]
    )
    data = json.loads(input_path.read_text(encoding="utf-8"))

    rows: List[Dict] = []
    texts: List[str] = []
    for item in data.get("items", []):
        spec = item.get("spec", {})
        for instruction in item.get("instructions", []):
            instruction_text = str(instruction.get("text", "")).strip()
            if not instruction_text:
                continue
            text_for_encoder = build_training_text(spec, instruction_text)
            rows.append(
                {
                    "item_id": item.get("id"),
                    "instruction_id": instruction.get("id"),
                    "instruction_text": instruction_text,
                    "spec": spec,
                    "text_for_encoder": text_for_encoder,
                }
            )
            texts.append(text_for_encoder)

    vectors = encode_texts(model_cfg, texts)
    for row, vector in zip(rows, vectors):
        row["vector"] = vector.tolist()

    out_dir = output_dir_for_model(config, model_cfg)
    out_path = out_dir / "emotion_embeddings.json"
    ensure_parent(out_path)
    payload = {
        "kind": "novel_emotion_embeddings",
        "model_config": model_cfg,
        "source_path": str(input_path),
        "embedding_dim": int(vectors.shape[1]) if vectors.size else 0,
        "records": rows,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Encode emotion persona instructions.")
    parser.add_argument("--config", default="emotion_analysis/config.json")
    args = parser.parse_args()

    config = load_config(args.config)
    model_cfg = get_embedding_model_cfg(config)
    out_path = encode_emotions_for_model(config, model_cfg)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

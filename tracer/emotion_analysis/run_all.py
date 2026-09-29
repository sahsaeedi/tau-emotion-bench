import argparse

from encode_emotions import encode_emotions_for_model
from encode_task_feelings import predict_for_model
from train_encoder import train_for_model
from utils import get_embedding_model_cfg, load_config
from visualize_instruction_tsne import visualize_instruction_tsne_for_model
from visualize_instruction_vs_task_tsne_knn_regions import (
    visualize_instruction_vs_task_tsne_knn_regions_for_model,
)


def run_all(config_path: str) -> None:
    config = load_config(config_path)
    model_cfg = get_embedding_model_cfg(config)
    emb = encode_emotions_for_model(config, model_cfg)
    print(f"[1/5] {emb}")
    ckpt = train_for_model(config, model_cfg)
    print(f"[2/5] {ckpt}")
    pred = predict_for_model(config, model_cfg)
    print(f"[3/5] {pred['summary_path']}")
    inst_tsne = visualize_instruction_tsne_for_model(config, model_cfg)
    print(f"[4/5] {inst_tsne}")
    tsne_paths = visualize_instruction_vs_task_tsne_knn_regions_for_model(
        config, model_cfg
    )
    for tsne in tsne_paths:
        print(f"[5/5] {tsne}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run novel emotion analysis pipeline end-to-end."
    )
    parser.add_argument("--config", default="emotion_analysis/config.json")
    args = parser.parse_args()
    run_all(args.config)


if __name__ == "__main__":
    main()

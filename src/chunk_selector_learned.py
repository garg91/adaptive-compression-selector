import json
from pathlib import Path


MODEL_PATH = Path("results/phase3_interleaved/chunk_selector_tree.json")


def load_tree(path: Path = MODEL_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_MODEL = None


def get_model() -> dict:
    global _MODEL

    if _MODEL is None:
        _MODEL = load_tree()

    return _MODEL


def predict_from_tree(node: dict, feature_values: dict) -> str:
    if node["type"] == "leaf":
        return node["class"]

    feature = node["feature"]
    threshold = node["threshold"]

    value = feature_values[feature]

    if value <= threshold:
        return predict_from_tree(node["left_if_leq"], feature_values)

    return predict_from_tree(node["right_if_gt"], feature_values)


def choose_learned_chunk_compressor(features: dict, chunk_size: int) -> str:
    model = get_model()

    feature_values = {
        "chunk_size": float(chunk_size),
        "original_size": float(features["size_bytes"]),
        "entropy": float(features["entropy"]),
        "text_ratio": float(features["text_ratio"]),
        "zero_ratio": float(features["zero_ratio"]),
        "unique_byte_count": float(features["unique_byte_count"]),
    }

    return predict_from_tree(model["tree"], feature_values)
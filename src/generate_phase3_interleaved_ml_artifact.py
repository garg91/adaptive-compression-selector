import argparse
import json
import os
import random
import struct
import time
from pathlib import Path

import zstandard as zstd


def mb_to_bytes(mb: int) -> int:
    return mb * 1024 * 1024


def make_metadata_block(target_size: int, block_id: int) -> bytes:
    records = []
    i = 0

    while sum(len(r) for r in records) < target_size:
        record = {
            "block_id": block_id,
            "record_id": i,
            "type": "metadata",
            "model": "phase3_interleaved_transformer",
            "layer": i % 96,
            "tensor_name": f"encoder.layers.{i % 96}.attention.q_proj.weight",
            "dtype": "float32",
            "shape": [4096, 4096],
            "optimizer": "adamw",
            "learning_rate": 0.0001,
            "notes": "repeated structured metadata for compression testing",
        }
        records.append(json.dumps(record, separators=(",", ":")).encode() + b"\n")
        i += 1

    return b"".join(records)[:target_size]


def make_sparse_float_block(target_size: int, block_id: int) -> bytes:
    data = bytearray(target_size)

    # Mostly zeros, with occasional float32 values.
    for offset in range((block_id % 128) * 4, target_size, 4096):
        value = float((offset // 4096) % 17)
        data[offset:offset + 4] = struct.pack("<f", value)

    return bytes(data)


def make_dense_float_like_block(target_size: int, block_id: int) -> bytes:
    # Not truly random: this imitates dense tensor bytes with weak local structure.
    # It should be compressible a little, but not extremely.
    rng = random.Random(10_000 + block_id)
    data = bytearray()

    while len(data) < target_size:
        # Generate repeated float-ish patterns with noise.
        base = rng.uniform(-1.0, 1.0)
        for _ in range(1024):
            value = base + rng.uniform(-0.01, 0.01)
            data.extend(struct.pack("<f", value))
            if len(data) >= target_size:
                break

    return bytes(data[:target_size])


def make_high_entropy_block(target_size: int, block_id: int) -> bytes:
    # Incompressible region.
    return os.urandom(target_size)


def make_label_block(target_size: int, block_id: int) -> bytes:
    data = bytearray()

    classes = 17 + (block_id % 13)

    while len(data) < target_size:
        for i in range(4096):
            data.extend(struct.pack("<I", i % classes))
            if len(data) >= target_size:
                break

    return bytes(data[:target_size])


def make_token_text_block(target_size: int, block_id: int) -> bytes:
    vocab = [
        "patient", "model", "gradient", "embedding", "attention", "layer",
        "checkpoint", "feature", "token", "loss", "optimizer", "batch",
        "dataset", "sparse", "dense", "float", "label", "metadata",
    ]

    lines = []
    i = 0

    while sum(len(x) for x in lines) < target_size:
        words = [
            vocab[(i + block_id + j) % len(vocab)]
            for j in range(12)
        ]
        line = f"{block_id},{i}," + " ".join(words) + f",{i % 1000}\n"
        lines.append(line.encode())
        i += 1

    return b"".join(lines)[:target_size]


def make_already_compressed_block(target_size: int, block_id: int) -> bytes:
    # Create compressible source, compress it internally, then repeat/trim.
    source = (
        f"already-compressed-inner-block-{block_id} "
        "this simulates jpeg/png/parquet/zstd-compressed payloads inside ML artifacts\n"
    ).encode() * 100_000

    compressed = zstd.ZstdCompressor(level=10).compress(source)

    if len(compressed) >= target_size:
        return compressed[:target_size]

    repeats = (target_size // len(compressed)) + 1
    return (compressed * repeats)[:target_size]


REGIME_BUILDERS = {
    "metadata": make_metadata_block,
    "sparse_float": make_sparse_float_block,
    "dense_float_like": make_dense_float_like_block,
    "high_entropy": make_high_entropy_block,
    "labels": make_label_block,
    "token_text": make_token_text_block,
    "already_compressed": make_already_compressed_block,
}


DEFAULT_PATTERN = [
    "metadata",
    "sparse_float",
    "dense_float_like",
    "labels",
    "token_text",
    "high_entropy",
    "sparse_float",
    "already_compressed",
    "metadata",
    "dense_float_like",
    "labels",
    "high_entropy",
    "token_text",
    "sparse_float",
]


def generate_artifact(
    output_path: Path,
    target_mb: int,
    regime_block_kb: int,
    seed: int,
    pattern: list[str],
) -> dict:
    random.seed(seed)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    target_size = mb_to_bytes(target_mb)
    regime_block_size = regime_block_kb * 1024

    written = 0
    block_id = 0
    counts = {name: 0 for name in REGIME_BUILDERS}
    bytes_by_regime = {name: 0 for name in REGIME_BUILDERS}

    start = time.perf_counter()

    with open(output_path, "wb") as f:
        while written < target_size:
            regime = pattern[block_id % len(pattern)]
            remaining = target_size - written
            current_size = min(regime_block_size, remaining)

            builder = REGIME_BUILDERS[regime]
            block = builder(current_size, block_id)

            if len(block) != current_size:
                raise RuntimeError(
                    f"Builder {regime} produced {len(block)} bytes, expected {current_size}"
                )

            f.write(block)

            counts[regime] += 1
            bytes_by_regime[regime] += current_size
            written += current_size
            block_id += 1

    elapsed = time.perf_counter() - start

    manifest = {
        "output_path": str(output_path),
        "target_mb": target_mb,
        "actual_bytes": output_path.stat().st_size,
        "actual_mb": output_path.stat().st_size / (1024 * 1024),
        "regime_block_kb": regime_block_kb,
        "seed": seed,
        "pattern": pattern,
        "blocks": block_id,
        "counts": counts,
        "bytes_by_regime": bytes_by_regime,
        "generation_time_seconds": elapsed,
    }

    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="data/ml_data/phase3_interleaved_ml_artifact_512mb.bin",
    )
    parser.add_argument("--target-mb", type=int, default=512)
    parser.add_argument("--regime-block-kb", type=int, default=256)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument(
        "--pattern",
        default=",".join(DEFAULT_PATTERN),
        help="Comma-separated regime pattern",
    )

    args = parser.parse_args()

    pattern = [x.strip() for x in args.pattern.split(",") if x.strip()]

    for regime in pattern:
        if regime not in REGIME_BUILDERS:
            raise ValueError(
                f"Unknown regime {regime}. Valid regimes: {sorted(REGIME_BUILDERS)}"
            )

    manifest = generate_artifact(
        output_path=Path(args.output),
        target_mb=args.target_mb,
        regime_block_kb=args.regime_block_kb,
        seed=args.seed,
        pattern=pattern,
    )

    print("Generated Phase 3 interleaved ML artifact")
    print(f"output: {manifest['output_path']}")
    print(f"actual MB: {manifest['actual_mb']:.2f}")
    print(f"regime block KB: {manifest['regime_block_kb']}")
    print(f"blocks: {manifest['blocks']}")
    print(f"manifest: {manifest['output_path']}.manifest.json")
    print("counts:")
    for key, value in manifest["counts"].items():
        if value:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
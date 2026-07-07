import json
from collections import defaultdict
from pathlib import Path

from selector import choose_compressor


RESULTS_PATH = Path("results/benchmark_results.json")


BASELINES = [
    "store",
    "gzip_9",
    "zlib_9",
    "bz2_9",
    "lzma_6",
    "lzma_9",
    "zstd_3",
    "zstd_10",
    "zstd_19",
]

SELECTOR_MODES = [
    "fast",
    "balanced_fast",
    "balanced_size",
    "balanced",
    "best_size",
]


def load_results():
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        rows = json.load(f)

    return [r for r in rows if "error" not in r]


def group_by_file(rows):
    by_file = defaultdict(dict)

    for row in rows:
        by_file[row["file"]][row["compressor"]] = row

    return by_file


def evaluate_fixed_baseline(by_file, compressor):
    total_original = 0
    total_compressed = 0
    total_compress_time = 0.0
    total_decompress_time = 0.0
    files_used = 0

    for file, compressor_rows in by_file.items():
        if compressor not in compressor_rows:
            continue

        row = compressor_rows[compressor]

        total_original += row["original_size_bytes"]
        total_compressed += row["compressed_size_bytes"]
        total_compress_time += row["compression_time_seconds"]
        total_decompress_time += row["decompression_time_seconds"]
        files_used += 1

    return {
        "strategy": f"always_{compressor}",
        "files_used": files_used,
        "total_original_bytes": total_original,
        "total_compressed_bytes": total_compressed,
        "overall_ratio": total_compressed / total_original if total_original else 1.0,
        "total_compression_time_seconds": total_compress_time,
        "total_decompression_time_seconds": total_decompress_time,
    }


def evaluate_oracle_best_size(by_file):
    total_original = 0
    total_compressed = 0
    total_compress_time = 0.0
    total_decompress_time = 0.0
    files_used = 0
    wins = defaultdict(int)

    for file, compressor_rows in by_file.items():
        best = min(
            compressor_rows.values(),
            key=lambda r: r["compressed_size_bytes"],
        )

        wins[best["compressor"]] += 1
        total_original += best["original_size_bytes"]
        total_compressed += best["compressed_size_bytes"]
        total_compress_time += best["compression_time_seconds"]
        total_decompress_time += best["decompression_time_seconds"]
        files_used += 1

    return {
        "strategy": "oracle_best_size",
        "files_used": files_used,
        "total_original_bytes": total_original,
        "total_compressed_bytes": total_compressed,
        "overall_ratio": total_compressed / total_original if total_original else 1.0,
        "total_compression_time_seconds": total_compress_time,
        "total_decompression_time_seconds": total_decompress_time,
        "wins": dict(wins),
    }


def evaluate_selector(by_file, mode):
    total_original = 0
    total_compressed = 0
    total_compress_time = 0.0
    total_decompress_time = 0.0
    files_used = 0
    choices = defaultdict(int)
    missing_choices = []

    for file, compressor_rows in by_file.items():
        sample = next(iter(compressor_rows.values()))

        chosen = choose_compressor(
            file_path=sample["file"],
            category=sample["category"],
            extension=sample["extension"],
            original_size_bytes=sample["original_size_bytes"],
            entropy=sample["entropy"],
            text_ratio=sample["text_ratio"],
            unique_byte_count=sample["unique_byte_count"],
            mode=mode,
        )

        if chosen not in compressor_rows:
            missing_choices.append((file, chosen))
            continue

        row = compressor_rows[chosen]

        choices[chosen] += 1
        total_original += row["original_size_bytes"]
        total_compressed += row["compressed_size_bytes"]
        total_compress_time += row["compression_time_seconds"]
        total_decompress_time += row["decompression_time_seconds"]
        files_used += 1

    return {
        "strategy": f"selector_{mode}",
        "files_used": files_used,
        "total_original_bytes": total_original,
        "total_compressed_bytes": total_compressed,
        "overall_ratio": total_compressed / total_original if total_original else 1.0,
        "total_compression_time_seconds": total_compress_time,
        "total_decompression_time_seconds": total_decompress_time,
        "choices": dict(choices),
        "missing_choices": missing_choices,
    }


def print_summary(results):
    print("\nOverall strategy comparison\n")
    print(
        f"{'Strategy':<24} "
        f"{'Ratio':>10} "
        f"{'Compressed MB':>15} "
        f"{'Comp Time s':>14} "
        f"{'Decomp Time s':>14}"
    )
    print("-" * 82)

    for r in sorted(results, key=lambda x: x["overall_ratio"]):
        compressed_mb = r["total_compressed_bytes"] / (1024 * 1024)

        print(
            f"{r['strategy']:<24} "
            f"{r['overall_ratio']:>10.4f} "
            f"{compressed_mb:>15.2f} "
            f"{r['total_compression_time_seconds']:>14.2f} "
            f"{r['total_decompression_time_seconds']:>14.2f}"
        )

    print("\nSelector choices\n")

    for r in results:
        if "choices" in r:
            print(f"{r['strategy']}: {r['choices']}")

    print("\nOracle best-size wins\n")

    for r in results:
        if r["strategy"] == "oracle_best_size":
            print(r["wins"])


def main():
    rows = load_results()
    by_file = group_by_file(rows)

    results = []

    for compressor in BASELINES:
        results.append(evaluate_fixed_baseline(by_file, compressor))

    for mode in SELECTOR_MODES:
        results.append(evaluate_selector(by_file, mode))

    results.append(evaluate_oracle_best_size(by_file))

    print_summary(results)

    output_path = Path("results/selector_evaluation.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nSaved detailed evaluation to {output_path}")


if __name__ == "__main__":
    main()
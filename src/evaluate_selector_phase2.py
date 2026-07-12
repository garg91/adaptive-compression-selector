import json
from collections import defaultdict
from pathlib import Path

from selector import choose_compressor


RESULTS_PATH = Path("results/benchmark_results_phase2.json")
OUTPUT_PATH = Path("results/selector_evaluation_phase2.json")


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

# Used only when the selector chooses a compressor that was skipped by the
# Phase 2 benchmark guard for a specific file. This keeps the evaluation from
# crashing and makes the fallback explicit in the output JSON.
FALLBACK_BY_MODE = {
    "fast": ["zstd_3", "store", "zstd_10", "lzma_6"],
    "balanced_fast": ["zstd_10", "zstd_3", "lzma_6", "store"],
    "balanced_size": ["lzma_6", "zstd_10", "zstd_3", "store"],
    "balanced": ["lzma_6", "zstd_10", "zstd_3", "store"],
    "best_size": ["lzma_6", "zstd_10", "zstd_3", "store"],
}


def is_valid_result_row(row):
    """Return True only for successful benchmark rows with complete metrics."""
    required_fields = {
        "file",
        "compressor",
        "original_size_bytes",
        "compressed_size_bytes",
        "compression_time_seconds",
        "decompression_time_seconds",
    }

    return (
        "error" not in row
        and not row.get("skipped", False)
        and required_fields.issubset(row.keys())
    )


def load_results():
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        rows = json.load(f)

    valid_rows = [r for r in rows if is_valid_result_row(r)]
    skipped_rows = sum(1 for r in rows if r.get("skipped", False))
    error_rows = sum(1 for r in rows if "error" in r)
    malformed_rows = len(rows) - len(valid_rows) - skipped_rows - error_rows

    print(f"Loaded raw rows:       {len(rows)}")
    print(f"Valid result rows:    {len(valid_rows)}")
    print(f"Skipped rows ignored: {skipped_rows}")
    print(f"Error rows ignored:   {error_rows}")
    print(f"Malformed ignored:    {malformed_rows}")

    return valid_rows


def group_by_file(rows):
    by_file = defaultdict(dict)

    for row in rows:
        by_file[row["file"]][row["compressor"]] = row

    return by_file


def aggregate_rows(strategy, selected_rows, extra=None):
    total_original = 0
    total_compressed = 0
    total_compress_time = 0.0
    total_decompress_time = 0.0

    for row in selected_rows:
        total_original += row["original_size_bytes"]
        total_compressed += row["compressed_size_bytes"]
        total_compress_time += row["compression_time_seconds"]
        total_decompress_time += row["decompression_time_seconds"]

    result = {
        "strategy": strategy,
        "files_used": len(selected_rows),
        "total_original_bytes": total_original,
        "total_compressed_bytes": total_compressed,
        "overall_ratio": total_compressed / total_original if total_original else 1.0,
        "total_compression_time_seconds": total_compress_time,
        "total_decompression_time_seconds": total_decompress_time,
    }

    if extra:
        result.update(extra)

    return result


def evaluate_fixed_baseline(by_file, compressor):
    selected_rows = []
    missing_files = 0

    for _file, compressor_rows in by_file.items():
        row = compressor_rows.get(compressor)

        if row is None:
            missing_files += 1
            continue

        selected_rows.append(row)

    return aggregate_rows(
        strategy=f"always_{compressor}",
        selected_rows=selected_rows,
        extra={"missing_files": missing_files},
    )


def evaluate_oracle_best_size(by_file):
    selected_rows = []
    wins = defaultdict(int)

    for _file, compressor_rows in by_file.items():
        if not compressor_rows:
            continue

        best = min(
            compressor_rows.values(),
            key=lambda r: r["compressed_size_bytes"],
        )

        wins[best["compressor"]] += 1
        selected_rows.append(best)

    return aggregate_rows(
        strategy="oracle_best_size_phase2_valid_rows",
        selected_rows=selected_rows,
        extra={"wins": dict(wins)},
    )


def choose_fallback_compressor(compressor_rows, mode):
    for fallback in FALLBACK_BY_MODE.get(mode, []):
        if fallback in compressor_rows:
            return fallback

    if compressor_rows:
        return min(
            compressor_rows.values(),
            key=lambda r: r["compressed_size_bytes"],
        )["compressor"]

    return None


def evaluate_selector(by_file, mode):
    selected_rows = []
    choices = defaultdict(int)
    fallback_choices = defaultdict(int)
    missing_choices = []

    for file, compressor_rows in by_file.items():
        if not compressor_rows:
            continue

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

        actual_chosen = chosen

        if actual_chosen not in compressor_rows:
            fallback = choose_fallback_compressor(compressor_rows, mode)

            if fallback is None:
                missing_choices.append({"file": file, "chosen": chosen, "fallback": None})
                continue

            missing_choices.append({"file": file, "chosen": chosen, "fallback": fallback})
            fallback_choices[f"{chosen}->{fallback}"] += 1
            actual_chosen = fallback

        row = compressor_rows[actual_chosen]

        choices[actual_chosen] += 1
        selected_rows.append(row)

    return aggregate_rows(
        strategy=f"selector_{mode}",
        selected_rows=selected_rows,
        extra={
            "choices": dict(choices),
            "fallback_choices": dict(fallback_choices),
            # Keep full detail in JSON, but this should be small because Phase 2 had only 92 skipped rows.
            "missing_choices": missing_choices,
            "missing_choice_count": len(missing_choices),
        },
    )


def print_summary(results):
    print("\nOverall strategy comparison\n")
    print(
        f"{'Strategy':<38} "
        f"{'Files':>8} "
        f"{'Ratio':>10} "
        f"{'Compressed MB':>15} "
        f"{'Comp Time s':>14} "
        f"{'Decomp Time s':>14}"
    )
    print("-" * 106)

    for r in sorted(results, key=lambda x: x["overall_ratio"]):
        compressed_mb = r["total_compressed_bytes"] / (1024 * 1024)

        print(
            f"{r['strategy']:<38} "
            f"{r['files_used']:>8} "
            f"{r['overall_ratio']:>10.4f} "
            f"{compressed_mb:>15.2f} "
            f"{r['total_compression_time_seconds']:>14.2f} "
            f"{r['total_decompression_time_seconds']:>14.2f}"
        )

    print("\nSelector choices\n")

    for r in results:
        if "choices" in r:
            print(f"{r['strategy']}: {r['choices']}")
            if r.get("fallback_choices"):
                print(f"  fallbacks: {r['fallback_choices']}")

    print("\nOracle best-size wins\n")

    for r in results:
        if r["strategy"].startswith("oracle_best_size"):
            print(r["wins"])


def main():
    rows = load_results()
    by_file = group_by_file(rows)

    print(f"Files with at least one valid result row: {len(by_file)}")

    results = []

    for compressor in BASELINES:
        results.append(evaluate_fixed_baseline(by_file, compressor))

    for mode in SELECTOR_MODES:
        results.append(evaluate_selector(by_file, mode))

    results.append(evaluate_oracle_best_size(by_file))

    print_summary(results)

    OUTPUT_PATH.parent.mkdir(exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nSaved detailed Phase 2 evaluation to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

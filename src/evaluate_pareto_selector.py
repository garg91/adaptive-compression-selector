import json
from collections import defaultdict
from pathlib import Path


RESULTS_PATH = Path("results/benchmark_results.json")
OUTPUT_JSON_PATH = Path("results/pareto_selector_evaluation.json")
REPORT_PATH = Path("results/pareto_selector_report.txt")


LAMBDA_VALUES = [
    0.0,
    0.001,
    0.005,
    0.01,
    0.05,
    0.1,
    0.5,
    1.0,
    5.0,
]


def load_results():
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        rows = json.load(f)

    return [row for row in rows if "error" not in row]


def group_by_file(rows):
    by_file = defaultdict(list)

    for row in rows:
        by_file[row["file"]].append(row)

    return by_file


def mb(n):
    return n / (1024 * 1024)


def is_dominated(candidate, rows):
    """
    A compressor is dominated if another compressor is:
      - smaller or equal in compressed size
      - faster or equal in compression time
      - strictly better in at least one dimension
    """

    for other in rows:
        if other["compressor"] == candidate["compressor"]:
            continue

        smaller_or_equal = (
            other["compressed_size_bytes"] <= candidate["compressed_size_bytes"]
        )
        faster_or_equal = (
            other["compression_time_seconds"] <= candidate["compression_time_seconds"]
        )

        strictly_better = (
            other["compressed_size_bytes"] < candidate["compressed_size_bytes"]
            or other["compression_time_seconds"] < candidate["compression_time_seconds"]
        )

        if smaller_or_equal and faster_or_equal and strictly_better:
            return True

    return False


def pareto_frontier(rows):
    frontier = []

    for row in rows:
        if not is_dominated(row, rows):
            frontier.append(row)

    return frontier


def pareto_score(row, lambda_value):
    """
    Lower is better.

    score = compressed_size_mb + lambda * compression_time_seconds

    lambda controls how much compression time matters:
      - lambda = 0.0    pure best size
      - small lambda    size-focused
      - large lambda    speed-focused
    """

    return mb(row["compressed_size_bytes"]) + (
        lambda_value * row["compression_time_seconds"]
    )


def choose_pareto(row_list, lambda_value):
    frontier = pareto_frontier(row_list)

    return min(
        frontier,
        key=lambda row: (
            pareto_score(row, lambda_value),
            row["compressed_size_bytes"],
            row["compression_time_seconds"],
        ),
    )


def evaluate_lambda(by_file, lambda_value):
    total_original = 0
    total_compressed = 0
    total_compression_time = 0.0
    total_decompression_time = 0.0
    choices = defaultdict(int)
    per_file = []

    for file_path, rows in sorted(by_file.items()):
        chosen = choose_pareto(rows, lambda_value)

        total_original += chosen["original_size_bytes"]
        total_compressed += chosen["compressed_size_bytes"]
        total_compression_time += chosen["compression_time_seconds"]
        total_decompression_time += chosen["decompression_time_seconds"]
        choices[chosen["compressor"]] += 1

        best_size = min(rows, key=lambda r: r["compressed_size_bytes"])

        per_file.append(
            {
                "file": file_path,
                "category": chosen["category"],
                "chosen_compressor": chosen["compressor"],
                "best_size_compressor": best_size["compressor"],
                "original_size_bytes": chosen["original_size_bytes"],
                "compressed_size_bytes": chosen["compressed_size_bytes"],
                "compressed_mb": mb(chosen["compressed_size_bytes"]),
                "compression_ratio": chosen["compression_ratio"],
                "compression_time_seconds": chosen["compression_time_seconds"],
                "decompression_time_seconds": chosen["decompression_time_seconds"],
                "size_penalty_vs_best_percent": (
                    (
                        chosen["compressed_size_bytes"]
                        - best_size["compressed_size_bytes"]
                    )
                    / best_size["compressed_size_bytes"]
                )
                * 100.0,
                "speedup_vs_best": (
                    best_size["compression_time_seconds"]
                    / chosen["compression_time_seconds"]
                    if chosen["compression_time_seconds"] > 0
                    else float("inf")
                ),
            }
        )

    return {
        "lambda": lambda_value,
        "files_used": len(by_file),
        "total_original_bytes": total_original,
        "total_compressed_bytes": total_compressed,
        "original_mb": mb(total_original),
        "compressed_mb": mb(total_compressed),
        "overall_ratio": total_compressed / total_original,
        "total_compression_time_seconds": total_compression_time,
        "total_decompression_time_seconds": total_decompression_time,
        "choices": dict(choices),
        "per_file": per_file,
    }


def build_report(results):
    lines = []

    lines.append("Pareto-Aware Selector Evaluation")
    lines.append("=" * 100)
    lines.append("")
    lines.append(
        "score = compressed_size_mb + lambda * compression_time_seconds"
    )
    lines.append("")
    lines.append(
        f"{'Lambda':>10} "
        f"{'Ratio':>10} "
        f"{'Compressed MB':>15} "
        f"{'Comp Time s':>14} "
        f"{'Decomp Time s':>14} "
        f"{'Choices':<35}"
    )
    lines.append("-" * 100)

    for r in results:
        lines.append(
            f"{r['lambda']:>10.3f} "
            f"{r['overall_ratio']:>10.4f} "
            f"{r['compressed_mb']:>15.2f} "
            f"{r['total_compression_time_seconds']:>14.2f} "
            f"{r['total_decompression_time_seconds']:>14.2f} "
            f"{str(r['choices']):<35}"
        )

    lines.append("")
    lines.append("=" * 100)
    lines.append("Detailed per-file choices")
    lines.append("=" * 100)

    for r in results:
        lines.append("")
        lines.append("-" * 100)
        lines.append(f"Lambda = {r['lambda']}")
        lines.append("-" * 100)

        lines.append(
            f"{'File':<45} "
            f"{'Chosen':<10} "
            f"{'Best':<10} "
            f"{'MB':>9} "
            f"{'Comp s':>9} "
            f"{'Size Penalty':>14} "
            f"{'Speedup':>10}"
        )

        for item in r["per_file"]:
            file_short = item["file"]
            if len(file_short) > 44:
                file_short = "..." + file_short[-41:]

            lines.append(
                f"{file_short:<45} "
                f"{item['chosen_compressor']:<10} "
                f"{item['best_size_compressor']:<10} "
                f"{item['compressed_mb']:>9.2f} "
                f"{item['compression_time_seconds']:>9.2f} "
                f"{item['size_penalty_vs_best_percent']:>13.2f}% "
                f"{item['speedup_vs_best']:>9.2f}x"
            )

    return lines


def main():
    rows = load_results()
    by_file = group_by_file(rows)

    results = []

    for lambda_value in LAMBDA_VALUES:
        results.append(evaluate_lambda(by_file, lambda_value))

    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    report_lines = build_report(results)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        f.write("\n")

    print(f"Saved Pareto selector JSON to {OUTPUT_JSON_PATH}")
    print(f"Saved Pareto selector report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
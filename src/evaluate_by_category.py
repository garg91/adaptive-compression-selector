import json
from collections import defaultdict
from pathlib import Path

from selector import choose_compressor


RESULTS_PATH = Path("results/benchmark_results.json")
OUTPUT_JSON_PATH = Path("results/category_evaluation.json")
REPORT_PATH = Path("results/category_report.txt")


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

    return [row for row in rows if "error" not in row]


def group_by_file(rows):
    by_file = defaultdict(dict)

    for row in rows:
        by_file[row["file"]][row["compressor"]] = row

    return by_file


def get_file_category(compressor_rows):
    sample = next(iter(compressor_rows.values()))
    return sample["category"]


def empty_metrics(strategy, category):
    return {
        "strategy": strategy,
        "category": category,
        "files_used": 0,
        "total_original_bytes": 0,
        "total_compressed_bytes": 0,
        "overall_ratio": 1.0,
        "total_compression_time_seconds": 0.0,
        "total_decompression_time_seconds": 0.0,
        "choices": defaultdict(int),
    }


def finalize_metrics(metrics):
    if metrics["total_original_bytes"] > 0:
        metrics["overall_ratio"] = (
            metrics["total_compressed_bytes"] / metrics["total_original_bytes"]
        )

    metrics["compressed_mb"] = metrics["total_compressed_bytes"] / (1024 * 1024)
    metrics["original_mb"] = metrics["total_original_bytes"] / (1024 * 1024)

    if isinstance(metrics.get("choices"), defaultdict):
        metrics["choices"] = dict(metrics["choices"])

    return metrics


def add_row(metrics, row, chosen=None):
    metrics["files_used"] += 1
    metrics["total_original_bytes"] += row["original_size_bytes"]
    metrics["total_compressed_bytes"] += row["compressed_size_bytes"]
    metrics["total_compression_time_seconds"] += row["compression_time_seconds"]
    metrics["total_decompression_time_seconds"] += row["decompression_time_seconds"]

    if chosen:
        metrics["choices"][chosen] += 1


def evaluate_fixed_by_category(by_file, compressor):
    category_metrics = {}

    for _, compressor_rows in by_file.items():
        if compressor not in compressor_rows:
            continue

        category = get_file_category(compressor_rows)
        key = (category, f"always_{compressor}")

        if key not in category_metrics:
            category_metrics[key] = empty_metrics(f"always_{compressor}", category)

        add_row(category_metrics[key], compressor_rows[compressor])

    return [finalize_metrics(m) for m in category_metrics.values()]


def evaluate_oracle_by_category(by_file):
    category_metrics = {}

    for _, compressor_rows in by_file.items():
        category = get_file_category(compressor_rows)
        key = (category, "oracle_best_size")

        if key not in category_metrics:
            category_metrics[key] = empty_metrics("oracle_best_size", category)

        best = min(
            compressor_rows.values(),
            key=lambda row: row["compressed_size_bytes"],
        )

        add_row(category_metrics[key], best, chosen=best["compressor"])

    return [finalize_metrics(m) for m in category_metrics.values()]


def evaluate_selector_by_category(by_file, mode):
    category_metrics = {}

    for _, compressor_rows in by_file.items():
        sample = next(iter(compressor_rows.values()))
        category = sample["category"]

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
            continue

        key = (category, f"selector_{mode}")

        if key not in category_metrics:
            category_metrics[key] = empty_metrics(f"selector_{mode}", category)

        add_row(category_metrics[key], compressor_rows[chosen], chosen=chosen)

    return [finalize_metrics(m) for m in category_metrics.values()]


def percent_change(new, old):
    if old == 0:
        return 0.0
    return ((new - old) / old) * 100.0


def build_category_table(all_results):
    lines = []
    by_category = defaultdict(list)

    for row in all_results:
        by_category[row["category"]].append(row)

    for category in sorted(by_category):
        rows = by_category[category]
        rows_sorted = sorted(rows, key=lambda r: r["overall_ratio"])

        lines.append("")
        lines.append("=" * 90)
        lines.append(f"Category: {category}")
        lines.append("=" * 90)

        lines.append(
            f"{'Strategy':<24} "
            f"{'Files':>5} "
            f"{'Ratio':>10} "
            f"{'Compressed MB':>15} "
            f"{'Comp Time s':>14} "
            f"{'Decomp Time s':>14}"
        )
        lines.append("-" * 90)

        for r in rows_sorted:
            lines.append(
                f"{r['strategy']:<24} "
                f"{r['files_used']:>5} "
                f"{r['overall_ratio']:>10.4f} "
                f"{r['compressed_mb']:>15.2f} "
                f"{r['total_compression_time_seconds']:>14.2f} "
                f"{r['total_decompression_time_seconds']:>14.2f}"
            )

        lzma9 = next((r for r in rows if r["strategy"] == "always_lzma_9"), None)
        balanced = next((r for r in rows if r["strategy"] == "selector_balanced"), None)
        best_size = next((r for r in rows if r["strategy"] == "selector_best_size"), None)
        oracle = next((r for r in rows if r["strategy"] == "oracle_best_size"), None)

        if lzma9 and balanced:
            size_change = percent_change(
                balanced["total_compressed_bytes"],
                lzma9["total_compressed_bytes"],
            )
            time_change = percent_change(
                balanced["total_compression_time_seconds"],
                lzma9["total_compression_time_seconds"],
            )

            lines.append("")
            lines.append("Balanced selector vs always_lzma_9:")
            lines.append(f"  compressed size change: {size_change:+.2f}%")
            lines.append(f"  compression time change: {time_change:+.2f}%")

        if oracle and best_size:
            same_size = (
                oracle["total_compressed_bytes"]
                == best_size["total_compressed_bytes"]
            )

            lines.append("")
            lines.append("Best-size selector vs oracle:")
            lines.append(f"  exact oracle match by compressed bytes: {same_size}")
            lines.append(f"  selector choices: {best_size.get('choices', {})}")
            lines.append(f"  oracle choices:   {oracle.get('choices', {})}")

    return lines


def build_compact_takeaways(all_results):
    lines = []
    by_category = defaultdict(list)

    for row in all_results:
        by_category[row["category"]].append(row)

    lines.append("")
    lines.append("=" * 90)
    lines.append("Compact takeaways")
    lines.append("=" * 90)

    for category in sorted(by_category):
        rows = by_category[category]

        best = min(rows, key=lambda r: r["overall_ratio"])
        fastest_nonstore = min(
            [r for r in rows if r["strategy"] != "always_store"],
            key=lambda r: r["total_compression_time_seconds"],
        )

        lzma9 = next((r for r in rows if r["strategy"] == "always_lzma_9"), None)
        balanced = next((r for r in rows if r["strategy"] == "selector_balanced"), None)

        lines.append("")
        lines.append(f"{category}:")
        lines.append(f"  best ratio: {best['strategy']} ({best['overall_ratio']:.4f})")
        lines.append(
            f"  fastest non-store: {fastest_nonstore['strategy']} "
            f"({fastest_nonstore['total_compression_time_seconds']:.2f}s)"
        )

        if lzma9 and balanced:
            size_change = percent_change(
                balanced["total_compressed_bytes"],
                lzma9["total_compressed_bytes"],
            )
            time_change = percent_change(
                balanced["total_compression_time_seconds"],
                lzma9["total_compression_time_seconds"],
            )

            lines.append(
                f"  selector_balanced vs lzma_9: "
                f"{size_change:+.2f}% size, {time_change:+.2f}% time"
            )

    return lines


def build_overall_summary(all_results):
    lines = []
    totals = defaultdict(lambda: {
        "strategy": "",
        "files_used": 0,
        "total_original_bytes": 0,
        "total_compressed_bytes": 0,
        "total_compression_time_seconds": 0.0,
        "total_decompression_time_seconds": 0.0,
    })

    for row in all_results:
        strategy = row["strategy"]
        totals[strategy]["strategy"] = strategy
        totals[strategy]["files_used"] += row["files_used"]
        totals[strategy]["total_original_bytes"] += row["total_original_bytes"]
        totals[strategy]["total_compressed_bytes"] += row["total_compressed_bytes"]
        totals[strategy]["total_compression_time_seconds"] += row[
            "total_compression_time_seconds"
        ]
        totals[strategy]["total_decompression_time_seconds"] += row[
            "total_decompression_time_seconds"
        ]

    rows = []
    for item in totals.values():
        if item["total_original_bytes"] == 0:
            continue

        item["overall_ratio"] = (
            item["total_compressed_bytes"] / item["total_original_bytes"]
        )
        item["compressed_mb"] = item["total_compressed_bytes"] / (1024 * 1024)
        rows.append(item)

    rows.sort(key=lambda r: r["overall_ratio"])

    lines.append("Adaptive Compression Selector Report")
    lines.append("=" * 90)
    lines.append("")
    lines.append("Overall strategy comparison")
    lines.append("-" * 90)
    lines.append(
        f"{'Strategy':<24} "
        f"{'Files':>5} "
        f"{'Ratio':>10} "
        f"{'Compressed MB':>15} "
        f"{'Comp Time s':>14} "
        f"{'Decomp Time s':>14}"
    )
    lines.append("-" * 90)

    for r in rows:
        lines.append(
            f"{r['strategy']:<24} "
            f"{r['files_used']:>5} "
            f"{r['overall_ratio']:>10.4f} "
            f"{r['compressed_mb']:>15.2f} "
            f"{r['total_compression_time_seconds']:>14.2f} "
            f"{r['total_decompression_time_seconds']:>14.2f}"
        )

    return lines


def main():
    rows = load_results()
    by_file = group_by_file(rows)

    all_results = []

    for compressor in BASELINES:
        all_results.extend(evaluate_fixed_by_category(by_file, compressor))

    for mode in SELECTOR_MODES:
        all_results.extend(evaluate_selector_by_category(by_file, mode))

    all_results.extend(evaluate_oracle_by_category(by_file))

    all_results = sorted(
        all_results,
        key=lambda r: (r["category"], r["overall_ratio"], r["strategy"]),
    )

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    report_lines = []
    report_lines.extend(build_overall_summary(all_results))
    report_lines.extend(build_category_table(all_results))
    report_lines.extend(build_compact_takeaways(all_results))

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        f.write("\n")

    print(f"Saved category evaluation JSON to {OUTPUT_JSON_PATH}")
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
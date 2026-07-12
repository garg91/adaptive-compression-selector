import json
from collections import Counter, defaultdict
from pathlib import Path


BENCHMARK_PATH = Path("results/benchmark_results_phase2.json")

OUTPUT_TXT = Path("results/compact_phase2_summary.txt")
OUTPUT_JSON = Path("results/compact_phase2_summary.json")


FULL_COVERAGE_STRATEGIES = {
    "store",
    "zstd_3",
    "zstd_10",
}

SELECTOR_NAMES = {
    "selector_fast",
    "selector_balanced_fast",
    "selector_balanced_size",
    "selector_best_size",
}

COMPRESSOR_ORDER = [
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


def mb(n: float) -> float:
    return n / (1024 * 1024)


def pct_change(new: float, old: float) -> float:
    if old == 0:
        return 0.0
    return ((new - old) / old) * 100.0


def load_rows():
    with open(BENCHMARK_PATH, "r", encoding="utf-8") as f:
        rows = json.load(f)

    loaded = len(rows)

    valid_rows = [
        r for r in rows
        if "error" not in r
        and not r.get("skipped", False)
        and "compressed_size_bytes" in r
        and "compression_time_seconds" in r
        and "decompression_time_seconds" in r
    ]

    skipped_rows = [r for r in rows if r.get("skipped", False)]
    error_rows = [r for r in rows if "error" in r]
    malformed_rows = [
        r for r in rows
        if "error" not in r
        and not r.get("skipped", False)
        and (
            "compressed_size_bytes" not in r
            or "compression_time_seconds" not in r
            or "decompression_time_seconds" not in r
        )
    ]

    return {
        "loaded": loaded,
        "valid_rows": valid_rows,
        "skipped_rows": skipped_rows,
        "error_rows": error_rows,
        "malformed_rows": malformed_rows,
    }


def group_by_file(rows):
    by_file = defaultdict(dict)

    for row in rows:
        by_file[row["file"]][row["compressor"]] = row

    return by_file


def corpus_stats(by_file):
    total_original = 0
    by_category = defaultdict(lambda: {"files": 0, "original_bytes": 0})

    for file_path, compressor_rows in by_file.items():
        sample = next(iter(compressor_rows.values()))
        original_size = sample["original_size_bytes"]
        category = sample["category"]

        total_original += original_size
        by_category[category]["files"] += 1
        by_category[category]["original_bytes"] += original_size

    return {
        "files": len(by_file),
        "original_bytes": total_original,
        "original_mb": mb(total_original),
        "by_category": dict(by_category),
    }


def evaluate_fixed_compressors(by_file):
    results = []

    total_files = len(by_file)

    for compressor in COMPRESSOR_ORDER:
        total_original = 0
        total_compressed = 0
        total_comp_time = 0.0
        total_decomp_time = 0.0
        files_used = 0

        by_category = defaultdict(lambda: {
            "files_used": 0,
            "original_bytes": 0,
            "compressed_bytes": 0,
            "compression_time_seconds": 0.0,
            "decompression_time_seconds": 0.0,
        })

        for file_path, compressor_rows in by_file.items():
            if compressor not in compressor_rows:
                continue

            row = compressor_rows[compressor]
            category = row["category"]

            files_used += 1
            total_original += row["original_size_bytes"]
            total_compressed += row["compressed_size_bytes"]
            total_comp_time += row["compression_time_seconds"]
            total_decomp_time += row["decompression_time_seconds"]

            cat = by_category[category]
            cat["files_used"] += 1
            cat["original_bytes"] += row["original_size_bytes"]
            cat["compressed_bytes"] += row["compressed_size_bytes"]
            cat["compression_time_seconds"] += row["compression_time_seconds"]
            cat["decompression_time_seconds"] += row["decompression_time_seconds"]

        coverage = files_used / total_files if total_files else 0.0

        results.append({
            "strategy": f"always_{compressor}",
            "compressor": compressor,
            "files_used": files_used,
            "total_files": total_files,
            "coverage": coverage,
            "full_coverage": files_used == total_files,
            "original_bytes": total_original,
            "compressed_bytes": total_compressed,
            "compressed_mb": mb(total_compressed),
            "ratio": total_compressed / total_original if total_original else 1.0,
            "compression_time_seconds": total_comp_time,
            "decompression_time_seconds": total_decomp_time,
            "by_category": dict(by_category),
        })

    return results


def oracle_by_file(by_file):
    oracle_rows = {}

    for file_path, compressor_rows in by_file.items():
        best = min(
            compressor_rows.values(),
            key=lambda r: (
                r["compressed_size_bytes"],
                r["compression_time_seconds"],
            ),
        )
        oracle_rows[file_path] = best

    return oracle_rows


def oracle_summary(oracle_rows):
    total_original = 0
    total_compressed = 0
    total_comp_time = 0.0
    total_decomp_time = 0.0

    wins = Counter()
    wins_by_category = defaultdict(Counter)

    for file_path, row in oracle_rows.items():
        compressor = row["compressor"]
        category = row["category"]

        wins[compressor] += 1
        wins_by_category[category][compressor] += 1

        total_original += row["original_size_bytes"]
        total_compressed += row["compressed_size_bytes"]
        total_comp_time += row["compression_time_seconds"]
        total_decomp_time += row["decompression_time_seconds"]

    return {
        "strategy": "oracle_best_size",
        "files_used": len(oracle_rows),
        "original_bytes": total_original,
        "compressed_bytes": total_compressed,
        "compressed_mb": mb(total_compressed),
        "ratio": total_compressed / total_original if total_original else 1.0,
        "compression_time_seconds": total_comp_time,
        "decompression_time_seconds": total_decomp_time,
        "wins": dict(wins),
        "wins_by_category": {
            category: dict(counter)
            for category, counter in wins_by_category.items()
        },
    }


def is_dominated(candidate, rows):
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


def pareto_summary(by_file):
    frontier_counts = Counter()
    dominated_counts = Counter()
    frontier_counts_by_category = defaultdict(Counter)
    dominated_counts_by_category = defaultdict(Counter)

    for file_path, compressor_rows in by_file.items():
        rows = list(compressor_rows.values())
        sample = rows[0]
        category = sample["category"]

        for row in rows:
            compressor = row["compressor"]

            if is_dominated(row, rows):
                dominated_counts[compressor] += 1
                dominated_counts_by_category[category][compressor] += 1
            else:
                frontier_counts[compressor] += 1
                frontier_counts_by_category[category][compressor] += 1

    return {
        "frontier_counts": dict(frontier_counts),
        "dominated_counts": dict(dominated_counts),
        "frontier_counts_by_category": {
            category: dict(counter)
            for category, counter in frontier_counts_by_category.items()
        },
        "dominated_counts_by_category": {
            category: dict(counter)
            for category, counter in dominated_counts_by_category.items()
        },
    }


def largest_gaps_vs_oracle(by_file, oracle_rows, top_n=25):
    gaps = []

    for file_path, compressor_rows in by_file.items():
        oracle = oracle_rows[file_path]

        best_fast = None
        if "zstd_3" in compressor_rows:
            best_fast = compressor_rows["zstd_3"]

        zstd10 = compressor_rows.get("zstd_10")
        lzma6 = compressor_rows.get("lzma_6")
        lzma9 = compressor_rows.get("lzma_9")
        zstd19 = compressor_rows.get("zstd_19")

        candidates = {
            "zstd_3_vs_oracle": best_fast,
            "zstd_10_vs_oracle": zstd10,
            "lzma_6_vs_oracle": lzma6,
            "lzma_9_vs_oracle": lzma9,
            "zstd_19_vs_oracle": zstd19,
        }

        for label, row in candidates.items():
            if row is None:
                continue

            size_gap_bytes = row["compressed_size_bytes"] - oracle["compressed_size_bytes"]
            size_gap_percent = pct_change(
                row["compressed_size_bytes"],
                oracle["compressed_size_bytes"],
            )

            gaps.append({
                "label": label,
                "file": file_path,
                "category": oracle["category"],
                "oracle_compressor": oracle["compressor"],
                "candidate_compressor": row["compressor"],
                "original_mb": mb(row["original_size_bytes"]),
                "oracle_compressed_mb": mb(oracle["compressed_size_bytes"]),
                "candidate_compressed_mb": mb(row["compressed_size_bytes"]),
                "size_gap_mb": mb(size_gap_bytes),
                "size_gap_percent": size_gap_percent,
                "oracle_comp_time": oracle["compression_time_seconds"],
                "candidate_comp_time": row["compression_time_seconds"],
            })

    gaps.sort(key=lambda x: x["size_gap_mb"], reverse=True)

    return gaps[:top_n]


def category_oracle_table(oracle_rows):
    by_category = defaultdict(lambda: {
        "files": 0,
        "original_bytes": 0,
        "compressed_bytes": 0,
        "compression_time_seconds": 0.0,
        "decompression_time_seconds": 0.0,
        "wins": Counter(),
    })

    for row in oracle_rows.values():
        category = row["category"]
        item = by_category[category]

        item["files"] += 1
        item["original_bytes"] += row["original_size_bytes"]
        item["compressed_bytes"] += row["compressed_size_bytes"]
        item["compression_time_seconds"] += row["compression_time_seconds"]
        item["decompression_time_seconds"] += row["decompression_time_seconds"]
        item["wins"][row["compressor"]] += 1

    output = {}

    for category, item in by_category.items():
        output[category] = {
            "files": item["files"],
            "original_mb": mb(item["original_bytes"]),
            "compressed_mb": mb(item["compressed_bytes"]),
            "ratio": item["compressed_bytes"] / item["original_bytes"]
            if item["original_bytes"]
            else 1.0,
            "compression_time_seconds": item["compression_time_seconds"],
            "decompression_time_seconds": item["decompression_time_seconds"],
            "wins": dict(item["wins"]),
        }

    return output


def format_counter(counter_dict):
    if not counter_dict:
        return "{}"

    items = sorted(counter_dict.items(), key=lambda x: (-x[1], x[0]))
    return "{" + ", ".join(f"{k}: {v}" for k, v in items) + "}"


def build_report(summary):
    lines = []

    corpus = summary["corpus"]
    row_stats = summary["row_stats"]
    oracle = summary["oracle"]
    fixed = summary["fixed_compressors"]
    pareto = summary["pareto"]
    category_oracle = summary["category_oracle"]
    largest_gaps = summary["largest_gaps_vs_oracle"]

    lines.append("Compact Phase 2 Summary")
    lines.append("=" * 100)
    lines.append("")
    lines.append("Input row integrity")
    lines.append("-" * 100)
    lines.append(f"Loaded rows:      {row_stats['loaded_rows']}")
    lines.append(f"Valid rows:       {row_stats['valid_rows']}")
    lines.append(f"Skipped rows:     {row_stats['skipped_rows']}")
    lines.append(f"Error rows:       {row_stats['error_rows']}")
    lines.append(f"Malformed rows:   {row_stats['malformed_rows']}")

    lines.append("")
    lines.append("Corpus")
    lines.append("-" * 100)
    lines.append(f"Files:            {corpus['files']}")
    lines.append(f"Original MB:      {corpus['original_mb']:.2f}")

    lines.append("")
    lines.append(f"{'Category':<22} {'Files':>8} {'Original MB':>15}")
    lines.append("-" * 50)

    for category, stats in sorted(corpus["by_category"].items()):
        lines.append(
            f"{category:<22} "
            f"{stats['files']:>8} "
            f"{mb(stats['original_bytes']):>15.2f}"
        )

    lines.append("")
    lines.append("Fixed compressor coverage")
    lines.append("-" * 100)
    lines.append(
        f"{'Strategy':<18} {'Files':>8} {'Coverage':>10} "
        f"{'Ratio':>10} {'Compressed MB':>15} {'Comp s':>12} {'Decomp s':>12}"
    )
    lines.append("-" * 100)

    for row in sorted(fixed, key=lambda r: (not r["full_coverage"], r["ratio"])):
        lines.append(
            f"{row['strategy']:<18} "
            f"{row['files_used']:>8} "
            f"{row['coverage'] * 100:>9.4f}% "
            f"{row['ratio']:>10.4f} "
            f"{row['compressed_mb']:>15.2f} "
            f"{row['compression_time_seconds']:>12.2f} "
            f"{row['decompression_time_seconds']:>12.2f}"
        )

    lines.append("")
    lines.append("Oracle best-size summary")
    lines.append("-" * 100)
    lines.append(f"Files:            {oracle['files_used']}")
    lines.append(f"Ratio:            {oracle['ratio']:.4f}")
    lines.append(f"Compressed MB:    {oracle['compressed_mb']:.2f}")
    lines.append(f"Comp time s:      {oracle['compression_time_seconds']:.2f}")
    lines.append(f"Decomp time s:    {oracle['decompression_time_seconds']:.2f}")
    lines.append(f"Wins:             {format_counter(oracle['wins'])}")

    lines.append("")
    lines.append("Oracle wins by category")
    lines.append("-" * 100)

    for category, item in sorted(category_oracle.items()):
        lines.append("")
        lines.append(f"{category}:")
        lines.append(f"  files:          {item['files']}")
        lines.append(f"  original MB:    {item['original_mb']:.2f}")
        lines.append(f"  compressed MB:  {item['compressed_mb']:.2f}")
        lines.append(f"  ratio:          {item['ratio']:.4f}")
        lines.append(f"  wins:           {format_counter(item['wins'])}")

    lines.append("")
    lines.append("Global Pareto counts")
    lines.append("-" * 100)
    lines.append("Frontier counts:")
    lines.append(f"  {format_counter(pareto['frontier_counts'])}")
    lines.append("")
    lines.append("Dominated counts:")
    lines.append(f"  {format_counter(pareto['dominated_counts'])}")

    lines.append("")
    lines.append("Largest compressor gaps vs oracle")
    lines.append("-" * 100)
    lines.append(
        f"{'Label':<22} {'Category':<16} {'Oracle':<10} {'Candidate':<10} "
        f"{'Orig MB':>10} {'Gap MB':>12} {'Gap %':>10}"
    )
    lines.append("-" * 100)

    for item in largest_gaps:
        lines.append(
            f"{item['label']:<22} "
            f"{item['category']:<16} "
            f"{item['oracle_compressor']:<10} "
            f"{item['candidate_compressor']:<10} "
            f"{item['original_mb']:>10.2f} "
            f"{item['size_gap_mb']:>12.2f} "
            f"{item['size_gap_percent']:>9.2f}%"
        )

    lines.append("")
    lines.append("Notes")
    lines.append("-" * 100)
    lines.append(
        "Ratios for partial-coverage compressors are computed only over files where "
        "that compressor actually ran. Use the coverage column before comparing "
        "fixed baselines directly."
    )
    lines.append(
        "For headline comparisons, prefer full-coverage strategies or restrict all "
        "strategies to a common file subset."
    )

    return lines


def main():
    loaded = load_rows()
    rows = loaded["valid_rows"]
    by_file = group_by_file(rows)

    corpus = corpus_stats(by_file)
    oracle_rows = oracle_by_file(by_file)
    oracle = oracle_summary(oracle_rows)
    fixed = evaluate_fixed_compressors(by_file)
    pareto = pareto_summary(by_file)
    category_oracle = category_oracle_table(oracle_rows)
    largest_gaps = largest_gaps_vs_oracle(by_file, oracle_rows, top_n=25)

    summary = {
        "row_stats": {
            "loaded_rows": loaded["loaded"],
            "valid_rows": len(loaded["valid_rows"]),
            "skipped_rows": len(loaded["skipped_rows"]),
            "error_rows": len(loaded["error_rows"]),
            "malformed_rows": len(loaded["malformed_rows"]),
        },
        "corpus": corpus,
        "fixed_compressors": fixed,
        "oracle": oracle,
        "category_oracle": category_oracle,
        "pareto": pareto,
        "largest_gaps_vs_oracle": largest_gaps,
    }

    OUTPUT_TXT.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    report_lines = build_report(summary)

    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        f.write("\n")

    print(f"Saved compact Phase 2 summary to {OUTPUT_TXT}")
    print(f"Saved compact Phase 2 JSON to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
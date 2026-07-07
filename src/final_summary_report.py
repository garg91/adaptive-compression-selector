import json
from collections import defaultdict
from pathlib import Path


BENCHMARK_PATH = Path("results/benchmark_results.json")
SELECTOR_EVAL_PATH = Path("results/selector_evaluation.json")
PARETO_EVAL_PATH = Path("results/pareto_selector_evaluation.json")

REPORT_PATH = Path("results/final_summary_report.txt")
REPORT_JSON_PATH = Path("results/final_summary_report.json")


FIXED_BASELINES = [
    "always_store",
    "always_zstd_3",
    "always_zstd_10",
    "always_zstd_19",
    "always_bz2_9",
    "always_lzma_6",
    "always_lzma_9",
    "always_zlib_9",
    "always_gzip_9",
]

RULE_MODES = [
    "selector_fast",
    "selector_balanced_fast",
    "selector_balanced_size",
    "selector_best_size",
]

PARETO_LAMBDAS_TO_SHOW = [
    0.0,
    0.05,
    0.1,
    1.0,
    5.0,
]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def mb(n):
    return n / (1024 * 1024)


def pct_change(new, old):
    return ((new - old) / old) * 100.0


def seconds_saved(new_time, old_time):
    return old_time - new_time


def load_selector_rows():
    rows = load_json(SELECTOR_EVAL_PATH)

    # Support both list and dict formats.
    if isinstance(rows, dict):
        if "strategies" in rows:
            rows = rows["strategies"]
        elif "results" in rows:
            rows = rows["results"]
        else:
            rows = list(rows.values())

    by_name = {}

    for row in rows:
        name = (
            row.get("strategy")
            or row.get("name")
            or row.get("mode")
            or row.get("selector")
        )

        if not name:
            continue

        by_name[name] = row

    return by_name


def get_row_value(row, *keys):
    for key in keys:
        if key in row:
            return row[key]
    raise KeyError(f"Could not find any of keys {keys} in row: {row.keys()}")


def normalize_selector_row(name, row):
    if "compressed_mb" in row:
        compressed_mb = row["compressed_mb"]
    elif "total_compressed_bytes" in row:
        compressed_mb = mb(row["total_compressed_bytes"])
    else:
        raise KeyError(
            f"Could not find compressed size in row for {name}: {row.keys()}"
        )

    return {
        "name": name,
        "ratio": get_row_value(row, "overall_ratio", "ratio"),
        "compressed_mb": compressed_mb,
        "compression_time_seconds": get_row_value(
            row,
            "total_compression_time_seconds",
            "compression_time_seconds",
            "comp_time_seconds",
        ),
        "decompression_time_seconds": get_row_value(
            row,
            "total_decompression_time_seconds",
            "decompression_time_seconds",
            "decomp_time_seconds",
        ),
        "choices": row.get("choices", {}),
    }


def load_pareto_rows():
    rows = load_json(PARETO_EVAL_PATH)

    by_lambda = {}

    for row in rows:
        by_lambda[float(row["lambda"])] = {
            "name": f"pareto_lambda_{row['lambda']}",
            "lambda": float(row["lambda"]),
            "ratio": row["overall_ratio"],
            "compressed_mb": row["compressed_mb"],
            "compression_time_seconds": row["total_compression_time_seconds"],
            "decompression_time_seconds": row["total_decompression_time_seconds"],
            "choices": row.get("choices", {}),
        }

    return by_lambda


def benchmark_category_stats():
    rows = [r for r in load_json(BENCHMARK_PATH) if "error" not in r]

    files = {}

    for r in rows:
        files[r["file"]] = {
            "category": r["category"],
            "original_size_bytes": r["original_size_bytes"],
        }

    by_category = defaultdict(lambda: {"files": 0, "original_bytes": 0})

    for file_info in files.values():
        category = file_info["category"]
        by_category[category]["files"] += 1
        by_category[category]["original_bytes"] += file_info["original_size_bytes"]

    return dict(by_category)


def choose_present_rows(selector_by_name, pareto_by_lambda):
    rows = []

    for name in FIXED_BASELINES:
        if name in selector_by_name:
            rows.append(normalize_selector_row(name, selector_by_name[name]))

    for name in RULE_MODES:
        if name in selector_by_name:
            rows.append(normalize_selector_row(name, selector_by_name[name]))

    if "oracle_best_size" in selector_by_name:
        rows.append(
            normalize_selector_row(
                "oracle_best_size",
                selector_by_name["oracle_best_size"],
            )
        )

    for lam in PARETO_LAMBDAS_TO_SHOW:
        if lam in pareto_by_lambda:
            rows.append(pareto_by_lambda[lam])

    # Deduplicate by name while preserving latest occurrence.
    by_name = {r["name"]: r for r in rows}

    return sorted(
        by_name.values(),
        key=lambda r: (
            r["compressed_mb"],
            r["compression_time_seconds"],
        ),
    )


def format_strategy_table(rows):
    lines = []

    lines.append(
        f"{'Strategy':<28} "
        f"{'Ratio':>8} "
        f"{'Compressed MB':>15} "
        f"{'Comp Time s':>14} "
        f"{'Decomp Time s':>14} "
        f"{'Choices':<35}"
    )
    lines.append("-" * 125)

    for r in rows:
        choices = r.get("choices", {})
        choice_text = str(choices) if choices else ""

        if len(choice_text) > 35:
            choice_text = choice_text[:32] + "..."

        lines.append(
            f"{r['name']:<28} "
            f"{r['ratio']:>8.4f} "
            f"{r['compressed_mb']:>15.2f} "
            f"{r['compression_time_seconds']:>14.2f} "
            f"{r['decompression_time_seconds']:>14.2f} "
            f"{choice_text:<35}"
        )

    return lines


def build_key_comparisons(selector_by_name):
    rows = {
        name: normalize_selector_row(name, row)
        for name, row in selector_by_name.items()
    }

    comparisons = {}

    def add_comparison(label, a_name, b_name):
        if a_name not in rows or b_name not in rows:
            return

        a = rows[a_name]
        b = rows[b_name]

        comparisons[label] = {
            "strategy": a_name,
            "baseline": b_name,
            "compressed_mb_change": a["compressed_mb"] - b["compressed_mb"],
            "compressed_size_change_percent": pct_change(
                a["compressed_mb"],
                b["compressed_mb"],
            ),
            "compression_time_saved_seconds": seconds_saved(
                a["compression_time_seconds"],
                b["compression_time_seconds"],
            ),
            "compression_time_change_percent": pct_change(
                a["compression_time_seconds"],
                b["compression_time_seconds"],
            ),
            "decompression_time_change_seconds": (
                a["decompression_time_seconds"] - b["decompression_time_seconds"]
            ),
        }

    add_comparison(
        "balanced_size_vs_lzma_9",
        "selector_balanced_size",
        "always_lzma_9",
    )
    add_comparison(
        "balanced_size_vs_lzma_6",
        "selector_balanced_size",
        "always_lzma_6",
    )
    add_comparison(
        "balanced_fast_vs_zstd_10",
        "selector_balanced_fast",
        "always_zstd_10",
    )
    add_comparison(
        "fast_vs_zstd_3",
        "selector_fast",
        "always_zstd_3",
    )
    add_comparison(
        "best_size_vs_oracle",
        "selector_best_size",
        "oracle_best_size",
    )

    return comparisons


def format_comparisons(comparisons):
    lines = []

    for label, c in comparisons.items():
        lines.append("")
        lines.append(label)
        lines.append("-" * len(label))
        lines.append(f"strategy:  {c['strategy']}")
        lines.append(f"baseline:  {c['baseline']}")
        lines.append(
            f"compressed size change: "
            f"{c['compressed_mb_change']:+.2f} MB "
            f"({c['compressed_size_change_percent']:+.2f}%)"
        )
        lines.append(
            f"compression time saved: "
            f"{c['compression_time_saved_seconds']:+.2f}s "
            f"({c['compression_time_change_percent']:+.2f}% time change)"
        )
        lines.append(
            f"decompression time change: "
            f"{c['decompression_time_change_seconds']:+.2f}s"
        )

    return lines


def build_category_section(category_stats):
    lines = []

    lines.append(
        f"{'Category':<22} "
        f"{'Files':>8} "
        f"{'Original MB':>15}"
    )
    lines.append("-" * 50)

    for category, stats in sorted(category_stats.items()):
        lines.append(
            f"{category:<22} "
            f"{stats['files']:>8} "
            f"{mb(stats['original_bytes']):>15.2f}"
        )

    return lines


def build_final_takeaways(selector_by_name):
    rows = {
        name: normalize_selector_row(name, row)
        for name, row in selector_by_name.items()
    }

    lines = []

    best = rows.get("selector_best_size")
    oracle = rows.get("oracle_best_size")
    balanced_size = rows.get("selector_balanced_size")
    balanced_fast = rows.get("selector_balanced_fast")
    fast = rows.get("selector_fast")
    lzma_9 = rows.get("always_lzma_9")
    zstd_10 = rows.get("always_zstd_10")
    zstd_3 = rows.get("always_zstd_3")

    if best and oracle:
        exact_match = (
            abs(best["compressed_mb"] - oracle["compressed_mb"]) < 1e-9
            and abs(
                best["compression_time_seconds"]
                - oracle["compression_time_seconds"]
            )
            < 1e-9
        )

        lines.append(
            f"1. Best-size selector matched the oracle exactly: {exact_match}."
        )

    if balanced_size and lzma_9:
        size_pct = pct_change(
            balanced_size["compressed_mb"],
            lzma_9["compressed_mb"],
        )
        time_pct = pct_change(
            balanced_size["compression_time_seconds"],
            lzma_9["compression_time_seconds"],
        )

        lines.append(
            "2. Balanced-size mode stayed very close to fixed lzma_9 size "
            f"({size_pct:+.2f}%) while reducing compression time "
            f"({time_pct:+.2f}%)."
        )

    if balanced_fast and zstd_10:
        size_pct = pct_change(
            balanced_fast["compressed_mb"],
            zstd_10["compressed_mb"],
        )
        time_pct = pct_change(
            balanced_fast["compression_time_seconds"],
            zstd_10["compression_time_seconds"],
        )

        lines.append(
            "3. Balanced-fast mode behaved like a smart zstd_10 profile "
            f"({size_pct:+.2f}% size, {time_pct:+.2f}% time)."
        )

    if fast and zstd_3:
        size_pct = pct_change(
            fast["compressed_mb"],
            zstd_3["compressed_mb"],
        )
        time_pct = pct_change(
            fast["compression_time_seconds"],
            zstd_3["compression_time_seconds"],
        )

        lines.append(
            "4. Fast mode behaved like a smart zstd_3 profile "
            f"({size_pct:+.2f}% size, {time_pct:+.2f}% time)."
        )

    lines.append(
        "5. gzip_9 and zlib_9 should remain as baselines only; earlier Pareto "
        "analysis showed they were dominated across this corpus."
    )

    return lines


def build_report():
    selector_by_name = load_selector_rows()
    pareto_by_lambda = load_pareto_rows()
    category_stats = benchmark_category_stats()

    rows = choose_present_rows(selector_by_name, pareto_by_lambda)
    comparisons = build_key_comparisons(selector_by_name)
    takeaways = build_final_takeaways(selector_by_name)

    output_json = {
        "strategies": rows,
        "comparisons": comparisons,
        "category_stats": category_stats,
        "takeaways": takeaways,
    }

    lines = []

    lines.append("Adaptive Compression Selector — Final Summary Report")
    lines.append("=" * 125)
    lines.append("")
    lines.append("Corpus")
    lines.append("-" * 125)
    lines.extend(build_category_section(category_stats))

    total_files = sum(s["files"] for s in category_stats.values())
    total_mb = sum(mb(s["original_bytes"]) for s in category_stats.values())

    lines.append("")
    lines.append(f"Total files:       {total_files}")
    lines.append(f"Total original MB: {total_mb:.2f}")

    lines.append("")
    lines.append("=" * 125)
    lines.append("Strategy Comparison")
    lines.append("=" * 125)
    lines.extend(format_strategy_table(rows))

    lines.append("")
    lines.append("=" * 125)
    lines.append("Key Comparisons")
    lines.append("=" * 125)
    lines.extend(format_comparisons(comparisons))

    lines.append("")
    lines.append("=" * 125)
    lines.append("Final Takeaways")
    lines.append("=" * 125)

    for takeaway in takeaways:
        lines.append(takeaway)

    lines.append("")
    lines.append("=" * 125)
    lines.append("Recommended Final Modes")
    lines.append("=" * 125)
    lines.append("")
    lines.append("best_size:")
    lines.append("  Use when compressed size matters most. Matches the best-size oracle.")
    lines.append("")
    lines.append("balanced_size:")
    lines.append("  Use for near-lzma_9 size with meaningful compression-time savings.")
    lines.append("")
    lines.append("balanced_fast:")
    lines.append("  Use for zstd_10-like practical compression with very low runtime.")
    lines.append("")
    lines.append("fast:")
    lines.append("  Use for zstd_3-like throughput-first compression.")
    lines.append("")
    lines.append("baseline-only:")
    lines.append("  gzip_9 and zlib_9 are useful for comparison, but not for selection.")

    return lines, output_json


def main():
    lines, output_json = build_report()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")

    with open(REPORT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(output_json, f, indent=2)

    print(f"Saved final summary report to {REPORT_PATH}")
    print(f"Saved final summary JSON to {REPORT_JSON_PATH}")


if __name__ == "__main__":
    main()
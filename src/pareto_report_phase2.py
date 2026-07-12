import json
from collections import defaultdict
from pathlib import Path


RESULTS_PATH = Path("results/benchmark_results_phase2.json")
REPORT_PATH = Path("results/pareto_report_phase2.txt")
OUTPUT_JSON_PATH = Path("results/pareto_report_phase2.json")


def load_results():
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        rows = json.load(f)

    error_count = sum(1 for row in rows if "error" in row)
    skipped_count = sum(1 for row in rows if row.get("skipped", False))
    malformed_count = sum(
        1
        for row in rows
        if "error" not in row
        and not row.get("skipped", False)
        and (
            "compressed_size_bytes" not in row
            or "compression_time_seconds" not in row
            or "decompression_time_seconds" not in row
        )
    )

    valid_rows = [
        row for row in rows
        if "error" not in row
        and not row.get("skipped", False)
        and "compressed_size_bytes" in row
        and "compression_time_seconds" in row
        and "decompression_time_seconds" in row
    ]

    print(f"Loaded rows:      {len(rows)}")
    print(f"Valid rows:       {len(valid_rows)}")
    print(f"Skipped rows:     {skipped_count}")
    print(f"Error rows:       {error_count}")
    print(f"Malformed rows:   {malformed_count}")

    return valid_rows


def group_by_file(rows):
    by_file = defaultdict(list)

    for row in rows:
        by_file[row["file"]].append(row)

    return by_file


def mb(n):
    return n / (1024 * 1024)


def is_dominated(candidate, others):
    """
    A compressor is dominated if another compressor is:
      - smaller or equal in compressed size
      - faster or equal in compression time
      - strictly better in at least one of those two dimensions
    """

    for other in others:
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
            return True, other

    return False, None


def get_pareto_frontier(rows):
    frontier = []
    dominated = []

    for row in rows:
        row_is_dominated, dominator = is_dominated(row, rows)

        if row_is_dominated:
            dominated.append((row, dominator))
        else:
            frontier.append(row)

    frontier.sort(
        key=lambda r: (
            r["compression_time_seconds"],
            r["compressed_size_bytes"],
        )
    )

    dominated.sort(
        key=lambda pair: (
            pair[0]["compression_time_seconds"],
            pair[0]["compressed_size_bytes"],
        )
    )

    return frontier, dominated


def size_penalty_vs_best(row, best_size_row):
    return (
        (row["compressed_size_bytes"] - best_size_row["compressed_size_bytes"])
        / best_size_row["compressed_size_bytes"]
    ) * 100.0


def speedup_vs_best(row, best_size_row):
    if row["compression_time_seconds"] == 0:
        return float("inf")

    return best_size_row["compression_time_seconds"] / row["compression_time_seconds"]


def build_report(by_file):
    lines = []
    json_output = []

    global_frontier_counts = defaultdict(int)
    global_dominated_counts = defaultdict(int)

    lines.append("Pareto Frontier Compression Report")
    lines.append("=" * 110)
    lines.append("")
    lines.append(
        "A compressor is Pareto-optimal for a file if no other compressor is both "
        "smaller and faster."
    )

    for file_path in sorted(by_file):
        rows = by_file[file_path]
        if not rows:
            continue

        sample = rows[0]

        best_size = min(rows, key=lambda r: r["compressed_size_bytes"])
        fastest = min(rows, key=lambda r: r["compression_time_seconds"])

        frontier, dominated = get_pareto_frontier(rows)

        for r in frontier:
            global_frontier_counts[r["compressor"]] += 1

        for r, _ in dominated:
            global_dominated_counts[r["compressor"]] += 1

        file_record = {
            "file": file_path,
            "category": sample["category"],
            "extension": sample["extension"],
            "original_size_bytes": sample["original_size_bytes"],
            "entropy": sample["entropy"],
            "text_ratio": sample["text_ratio"],
            "unique_byte_count": sample["unique_byte_count"],
            "best_size_compressor": best_size["compressor"],
            "fastest_compressor": fastest["compressor"],
            "pareto_frontier": [],
            "dominated": [],
        }

        lines.append("")
        lines.append("=" * 110)
        lines.append(file_path)
        lines.append("=" * 110)
        lines.append(f"category:          {sample['category']}")
        lines.append(f"extension:         {sample['extension']}")
        lines.append(f"original MB:       {mb(sample['original_size_bytes']):.2f}")
        lines.append(f"entropy:           {sample['entropy']:.4f}")
        lines.append(f"text_ratio:        {sample['text_ratio']:.4f}")
        lines.append(f"unique bytes:      {sample['unique_byte_count']}")
        lines.append("")
        lines.append(
            f"best size:         {best_size['compressor']} "
            f"({mb(best_size['compressed_size_bytes']):.2f} MB, "
            f"{best_size['compression_time_seconds']:.2f}s)"
        )
        lines.append(
            f"fastest:           {fastest['compressor']} "
            f"({mb(fastest['compressed_size_bytes']):.2f} MB, "
            f"{fastest['compression_time_seconds']:.6f}s)"
        )

        lines.append("")
        lines.append("Pareto frontier:")
        lines.append("-" * 110)
        lines.append(
            f"{'Compressor':<12} "
            f"{'Size MB':>10} "
            f"{'Ratio':>10} "
            f"{'Comp s':>10} "
            f"{'Decomp s':>10} "
            f"{'Size vs Best':>14} "
            f"{'Speedup vs Best':>16}"
        )
        lines.append("-" * 110)

        for r in frontier:
            penalty = size_penalty_vs_best(r, best_size)
            speedup = speedup_vs_best(r, best_size)

            lines.append(
                f"{r['compressor']:<12} "
                f"{mb(r['compressed_size_bytes']):>10.2f} "
                f"{r['compression_ratio']:>10.4f} "
                f"{r['compression_time_seconds']:>10.4f} "
                f"{r['decompression_time_seconds']:>10.4f} "
                f"{penalty:>13.2f}% "
                f"{speedup:>16.2f}x"
            )

            file_record["pareto_frontier"].append(
                {
                    "compressor": r["compressor"],
                    "compressed_size_bytes": r["compressed_size_bytes"],
                    "compressed_mb": mb(r["compressed_size_bytes"]),
                    "compression_ratio": r["compression_ratio"],
                    "compression_time_seconds": r["compression_time_seconds"],
                    "decompression_time_seconds": r["decompression_time_seconds"],
                    "size_penalty_vs_best_percent": penalty,
                    "speedup_vs_best": speedup,
                }
            )

        lines.append("")
        lines.append("Dominated compressors:")
        lines.append("-" * 110)
        lines.append(
            f"{'Compressor':<12} "
            f"{'Size MB':>10} "
            f"{'Comp s':>10} "
            f"{'Dominated by':>16} "
            f"{'Reason':<40}"
        )
        lines.append("-" * 110)

        if not dominated:
            lines.append("None")
        else:
            for r, dominator in dominated:
                reason_parts = []

                if dominator["compressed_size_bytes"] < r["compressed_size_bytes"]:
                    reason_parts.append("smaller")
                elif dominator["compressed_size_bytes"] == r["compressed_size_bytes"]:
                    reason_parts.append("same size")

                if dominator["compression_time_seconds"] < r["compression_time_seconds"]:
                    reason_parts.append("faster")
                elif dominator["compression_time_seconds"] == r["compression_time_seconds"]:
                    reason_parts.append("same speed")

                reason = " and ".join(reason_parts)

                lines.append(
                    f"{r['compressor']:<12} "
                    f"{mb(r['compressed_size_bytes']):>10.2f} "
                    f"{r['compression_time_seconds']:>10.4f} "
                    f"{dominator['compressor']:>16} "
                    f"{reason:<40}"
                )

                file_record["dominated"].append(
                    {
                        "compressor": r["compressor"],
                        "dominated_by": dominator["compressor"],
                        "compressed_size_bytes": r["compressed_size_bytes"],
                        "compressed_mb": mb(r["compressed_size_bytes"]),
                        "compression_time_seconds": r["compression_time_seconds"],
                        "dominator_compressed_size_bytes": dominator[
                            "compressed_size_bytes"
                        ],
                        "dominator_compression_time_seconds": dominator[
                            "compression_time_seconds"
                        ],
                        "reason": reason,
                    }
                )

        json_output.append(file_record)

    lines.append("")
    lines.append("=" * 110)
    lines.append("Global Pareto summary")
    lines.append("=" * 110)
    lines.append("")
    lines.append("Number of files where each compressor appears on the Pareto frontier:")
    lines.append("-" * 110)

    for compressor, count in sorted(
        global_frontier_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"{compressor:<12} {count:>4}")

    lines.append("")
    lines.append("Number of files where each compressor is dominated:")
    lines.append("-" * 110)

    for compressor, count in sorted(
        global_dominated_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        lines.append(f"{compressor:<12} {count:>4}")

    return lines, json_output


def main():
    rows = load_results()
    by_file = group_by_file(rows)

    report_lines, json_output = build_report(by_file)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        f.write("\n")

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(json_output, f, indent=2)

    print(f"Saved Pareto report to {REPORT_PATH}")
    print(f"Saved Pareto JSON to {OUTPUT_JSON_PATH}")


if __name__ == "__main__":
    main()
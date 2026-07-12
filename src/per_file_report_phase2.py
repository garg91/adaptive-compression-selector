import json
from collections import defaultdict
from pathlib import Path

from selector import choose_compressor


RESULTS_PATH = Path("results/benchmark_results_phase2.json")
REPORT_PATH = Path("results/per_file_report_phase2.txt")


MODES = [
    "fast",
    "balanced_fast",
    "balanced_size",
    "best_size",
]


REQUIRED_RESULT_KEYS = {
    "compressed_size_bytes",
    "compression_ratio",
    "compression_time_seconds",
    "decompression_time_seconds",
}


def is_valid_result_row(row):
    return (
        "error" not in row
        and not row.get("skipped", False)
        and REQUIRED_RESULT_KEYS.issubset(row.keys())
    )


def load_results():
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        rows = json.load(f)

    skipped_count = sum(1 for r in rows if r.get("skipped", False))
    error_count = sum(1 for r in rows if "error" in r)
    malformed_count = sum(
        1
        for r in rows
        if "error" not in r
        and not r.get("skipped", False)
        and not REQUIRED_RESULT_KEYS.issubset(r.keys())
    )

    valid_rows = [r for r in rows if is_valid_result_row(r)]

    print(f"Loaded rows:    {len(rows)}")
    print(f"Valid rows:     {len(valid_rows)}")
    print(f"Skipped rows:   {skipped_count}")
    print(f"Error rows:     {error_count}")
    print(f"Malformed rows: {malformed_count}")

    return valid_rows


def group_by_file(rows):
    by_file = defaultdict(dict)
    for row in rows:
        by_file[row["file"]][row["compressor"]] = row
    return by_file


def mb(n):
    return n / (1024 * 1024)


def size_penalty_percent(row, best):
    if best["compressed_size_bytes"] == 0:
        return 0.0

    return (
        (row["compressed_size_bytes"] - best["compressed_size_bytes"])
        / best["compressed_size_bytes"]
    ) * 100.0


def main():
    rows = load_results()
    by_file = group_by_file(rows)

    lines = []

    lines.append("Per-File Adaptive Compression Report - Phase 2")
    lines.append("=" * 100)
    lines.append("")
    lines.append(f"Input benchmark: {RESULTS_PATH}")
    lines.append(f"Valid benchmark rows: {len(rows)}")
    lines.append(f"Files represented: {len(by_file)}")

    missing_decisions = []

    for file_path in sorted(by_file):
        compressor_rows = by_file[file_path]

        if not compressor_rows:
            continue

        sample = next(iter(compressor_rows.values()))

        best = min(
            compressor_rows.values(),
            key=lambda r: r["compressed_size_bytes"],
        )

        lines.append("")
        lines.append("=" * 100)
        lines.append(file_path)
        lines.append("=" * 100)
        lines.append(f"category:          {sample['category']}")
        lines.append(f"extension:         {sample['extension']}")
        lines.append(f"original MB:       {mb(sample['original_size_bytes']):.2f}")
        lines.append(f"entropy:           {sample['entropy']:.4f}")
        lines.append(f"text_ratio:        {sample['text_ratio']:.4f}")
        lines.append(f"unique bytes:      {sample['unique_byte_count']}")
        lines.append("")
        lines.append(
            f"oracle best:       {best['compressor']} "
            f"({mb(best['compressed_size_bytes']):.2f} MB, "
            f"ratio {best['compression_ratio']:.4f}, "
            f"{best['compression_time_seconds']:.2f}s)"
        )

        lines.append("")
        lines.append("Selector decisions:")
        lines.append("-" * 100)

        for mode in MODES:
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

            row = compressor_rows.get(chosen)

            if row is None:
                # This can happen in Phase 2 when the benchmark guard skipped the
                # selector's chosen compressor for a file. Keep the report alive and
                # make the missing decision visible instead of raising KeyError.
                missing_decisions.append({
                    "file": file_path,
                    "mode": mode,
                    "chosen": chosen,
                    "available": sorted(compressor_rows.keys()),
                })

                lines.append(
                    f"{mode:<16} -> {chosen:<8} "
                    f"UNAVAILABLE in valid Phase 2 rows "
                    f"available={sorted(compressor_rows.keys())}"
                )
                continue

            size_penalty = size_penalty_percent(row, best)

            lines.append(
                f"{mode:<16} -> {chosen:<8} "
                f"{mb(row['compressed_size_bytes']):>8.2f} MB "
                f"ratio {row['compression_ratio']:.4f} "
                f"comp {row['compression_time_seconds']:>7.2f}s "
                f"decomp {row['decompression_time_seconds']:>6.2f}s "
                f"size_vs_oracle {size_penalty:+.2f}%"
            )

        lines.append("")
        lines.append("All compressors:")
        lines.append("-" * 100)

        ranked = sorted(
            compressor_rows.values(),
            key=lambda r: r["compressed_size_bytes"],
        )

        for r in ranked:
            lines.append(
                f"{r['compressor']:<8} "
                f"{mb(r['compressed_size_bytes']):>8.2f} MB "
                f"ratio {r['compression_ratio']:.4f} "
                f"comp {r['compression_time_seconds']:>7.2f}s "
                f"decomp {r['decompression_time_seconds']:>6.2f}s"
            )

    if missing_decisions:
        lines.append("")
        lines.append("=" * 100)
        lines.append("Selector decisions unavailable due to Phase 2 skips")
        lines.append("=" * 100)
        lines.append(f"Total unavailable selector decisions: {len(missing_decisions)}")

        for item in missing_decisions[:200]:
            lines.append(
                f"{item['file']} | mode={item['mode']} | "
                f"chosen={item['chosen']} | available={item['available']}"
            )

        if len(missing_decisions) > 200:
            lines.append(f"... {len(missing_decisions) - 200} more omitted")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")

    print(f"Saved per-file report to {REPORT_PATH}")
    print(f"Files represented in report: {len(by_file)}")
    print(f"Unavailable selector decisions: {len(missing_decisions)}")


if __name__ == "__main__":
    main()

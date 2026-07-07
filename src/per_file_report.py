import json
from collections import defaultdict
from pathlib import Path

from selector import choose_compressor


RESULTS_PATH = Path("results/benchmark_results.json")
REPORT_PATH = Path("results/per_file_report.txt")


MODES = [
    "fast",
    "balanced_fast",
    "balanced_size",
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


def mb(n):
    return n / (1024 * 1024)


def main():
    rows = load_results()
    by_file = group_by_file(rows)

    lines = []

    lines.append("Per-File Adaptive Compression Report")
    lines.append("=" * 100)

    for file_path in sorted(by_file):
        compressor_rows = by_file[file_path]
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

            row = compressor_rows[chosen]

            size_penalty = (
                (row["compressed_size_bytes"] - best["compressed_size_bytes"])
                / best["compressed_size_bytes"]
            ) * 100.0

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

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")

    print(f"Saved per-file report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
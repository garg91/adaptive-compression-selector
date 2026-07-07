import json
from pathlib import Path
from collections import defaultdict


RESULTS_PATH = Path("results/benchmark_results.json")


def main() -> None:
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        rows = json.load(f)

    valid_rows = [r for r in rows if "error" not in r]

    by_file = defaultdict(list)
    for row in valid_rows:
        by_file[row["file"]].append(row)

    print("\nBest compressor by file size:\n")

    wins = defaultdict(int)

    for file, file_rows in by_file.items():
        best = min(file_rows, key=lambda r: r["compressed_size_bytes"])
        wins[best["compressor"]] += 1

        print(f"{file}")
        print(f"  category: {best['category']}")
        print(f"  best: {best['compressor']}")
        print(f"  original: {best['original_size_bytes']:,} bytes")
        print(f"  compressed: {best['compressed_size_bytes']:,} bytes")
        print(f"  ratio: {best['compression_ratio']:.4f}")
        print(f"  compression time: {best['compression_time_seconds']:.4f}s")
        print(f"  decompression time: {best['decompression_time_seconds']:.4f}s")
        print()

    print("\nWin count by compressor:\n")
    for compressor, count in sorted(wins.items(), key=lambda x: x[1], reverse=True):
        print(f"{compressor}: {count}")


if __name__ == "__main__":
    main()
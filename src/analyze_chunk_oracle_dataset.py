import csv
from collections import Counter, defaultdict
from pathlib import Path


DATASET_PATH = Path("datasets/phase3/chunk_oracle_dataset.csv")


def to_float(value):
    try:
        return float(value)
    except ValueError:
        return 0.0


def main():
    rows = []

    with open(DATASET_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"Rows: {len(rows)}")

    by_compressor = Counter(row["best_compressor"] for row in rows)
    by_chunk_size = Counter(row["chunk_size"] for row in rows)

    print()
    print("Oracle labels by compressor:")
    for key, value in by_compressor.most_common():
        print(f"  {key:<10} {value}")

    print()
    print("Rows by chunk size:")
    for key, value in sorted(by_chunk_size.items(), key=lambda x: int(x[0])):
        print(f"  {int(key):>10} bytes  {value}")

    print()
    print("Feature averages by oracle compressor:")
    grouped = defaultdict(list)

    for row in rows:
        grouped[row["best_compressor"]].append(row)

    for compressor, group in sorted(grouped.items()):
        entropy = sum(to_float(r["entropy"]) for r in group) / len(group)
        text = sum(to_float(r["text_ratio"]) for r in group) / len(group)
        zero = sum(to_float(r["zero_ratio"]) for r in group) / len(group)
        unique = sum(to_float(r["unique_byte_count"]) for r in group) / len(group)
        ratio = sum(to_float(r["compression_ratio"]) for r in group) / len(group)

        print()
        print(compressor)
        print(f"  count:        {len(group)}")
        print(f"  entropy:      {entropy:.4f}")
        print(f"  text_ratio:   {text:.4f}")
        print(f"  zero_ratio:   {zero:.4f}")
        print(f"  unique_bytes: {unique:.2f}")
        print(f"  comp_ratio:   {ratio:.6f}")


if __name__ == "__main__":
    main()
import argparse
import csv
import json
import struct
from pathlib import Path


def read_adc(path: Path):
    with open(path, "rb") as f:
        magic = f.read(4)
        if magic != b"ADC1":
            raise ValueError(f"{path} is not an ADC1 file")

        header_len = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(header_len))

    return header


def extract_rows(adc_path: Path):
    header = read_adc(adc_path)

    table = {
        item["id"]: item["name"]
        for item in header["compressor_table"]
    }

    rows = []

    for chunk in header["chunks"]:
        features = chunk["features"]
        compressor = table[chunk["compressor_id"]]

        rows.append({
            "adc_file": str(adc_path),
            "source_file": header.get("original_file", ""),
            "mode": header.get("mode", ""),
            "chunk_size": header.get("chunk_size", ""),
            "chunk_index": chunk["index"],
            "original_offset": chunk["original_offset"],
            "original_size": chunk["original_size"],
            "compressed_size": chunk["compressed_size"],
            "compression_ratio": chunk["compressed_size"] / chunk["original_size"]
            if chunk["original_size"]
            else 1.0,
            "best_compressor": compressor,
            "entropy": features.get("entropy", ""),
            "text_ratio": features.get("text_ratio", ""),
            "zero_ratio": features.get("zero_ratio", ""),
            "unique_byte_count": features.get("unique_byte_count", ""),
            "feature_size_bytes": features.get("size_bytes", ""),
        })

    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more oracle .adc files",
    )
    parser.add_argument(
        "--output",
        default="datasets/phase3/chunk_oracle_dataset.csv",
    )

    args = parser.parse_args()

    all_rows = []

    for item in args.inputs:
        path = Path(item)
        all_rows.extend(extract_rows(path))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "adc_file",
        "source_file",
        "mode",
        "chunk_size",
        "chunk_index",
        "original_offset",
        "original_size",
        "compressed_size",
        "compression_ratio",
        "best_compressor",
        "entropy",
        "text_ratio",
        "zero_ratio",
        "unique_byte_count",
        "feature_size_bytes",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Wrote {len(all_rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
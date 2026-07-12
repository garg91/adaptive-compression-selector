import json
import struct
from collections import Counter
from pathlib import Path


RESULT_DIR = Path("results/phase3_interleaved")
OUTPUT_TXT = RESULT_DIR / "phase3_summary_report.txt"
OUTPUT_JSON = RESULT_DIR / "phase3_summary_report.json"


WHOLE_FILE_BASELINES = {
    "zstd_3": {
        "compressed_mb": 138.08,
        "ratio": 0.269685,
        "compression_time_seconds": 0.31,
    },
    "zstd_10": {
        "compressed_mb": 137.25,
        "ratio": 0.268070,
        "compression_time_seconds": 1.00,
    },
    "zstd_19": {
        "compressed_mb": 135.57,
        "ratio": 0.264783,
        "compression_time_seconds": 47.21,
    },
    "lzma_6": {
        "compressed_mb": 127.26,
        "ratio": 0.248555,
        "compression_time_seconds": 36.41,
    },
    "lzma_9": {
        "compressed_mb": 125.38,
        "ratio": 0.244884,
        "compression_time_seconds": 55.85,
    },
    "bz2_9": {
        "compressed_mb": 148.28,
        "ratio": 0.289605,
        "compression_time_seconds": 42.57,
    },
}


ADC_TIMES = {
    "interleaved_256kb_balanced.adc": 35.73668791493401,
    "interleaved_1mb_balanced.adc": 49.85903374082409,
    "interleaved_4mb_balanced.adc": 60.33451641490683,
    "interleaved_256kb_oracle.adc": 225.3612042570021,
    "interleaved_1mb_oracle.adc": 195.2360240900889,
    "interleaved_4mb_oracle.adc": 191.12742100306787,
    "interleaved_256kb_learned.adc": 67.57923970813863,
    "interleaved_1mb_learned.adc": 64.66129392199218,
    "interleaved_4mb_learned.adc": 68.01219348888844,
}


ORIGINAL_BYTES = 536870912


def mb(n):
    return n / (1024 * 1024)


def pct_change(new, old):
    if old == 0:
        return 0.0
    return ((new - old) / old) * 100.0


def read_adc_summary(path: Path):
    with open(path, "rb") as f:
        magic = f.read(4)
        if magic != b"ADC1":
            raise ValueError(f"{path} is not an ADC1 file")

        header_len = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(header_len))

    table = {
        item["id"]: item["name"]
        for item in header["compressor_table"]
    }

    choices = Counter(
        table[chunk["compressor_id"]]
        for chunk in header["chunks"]
    )

    compressed_bytes = path.stat().st_size
    name = path.name

    if "256kb" in name:
        chunk_label = "256 KB"
    elif "1mb" in name:
        chunk_label = "1 MB"
    elif "4mb" in name:
        chunk_label = "4 MB"
    else:
        chunk_label = str(header["chunk_size"])

    if "balanced" in name:
        method = "adc_balanced"
    elif "learned" in name:
        method = "adc_learned"
    elif "oracle" in name:
        method = "adc_chunk_oracle"
    else:
        method = "adc"

    return {
        "file": name,
        "method": method,
        "chunk_size": chunk_label,
        "chunk_size_bytes": header["chunk_size"],
        "chunks": len(header["chunks"]),
        "compressed_bytes": compressed_bytes,
        "compressed_mb": mb(compressed_bytes),
        "ratio": compressed_bytes / ORIGINAL_BYTES,
        "compression_time_seconds": ADC_TIMES.get(name),
        "choices": dict(choices),
    }


def main():
    adc_rows = []

    for path in sorted(RESULT_DIR.glob("interleaved_*.adc")):
        adc_rows.append(read_adc_summary(path))

    oracle_by_chunk = {
        row["chunk_size"]: row
        for row in adc_rows
        if row["method"] == "adc_chunk_oracle"
    }

    zstd19_mb = WHOLE_FILE_BASELINES["zstd_19"]["compressed_mb"]
    lzma6_mb = WHOLE_FILE_BASELINES["lzma_6"]["compressed_mb"]
    lzma9_mb = WHOLE_FILE_BASELINES["lzma_9"]["compressed_mb"]

    for row in adc_rows:
        oracle = oracle_by_chunk.get(row["chunk_size"])

        row["gap_vs_chunk_oracle_percent"] = (
            pct_change(row["compressed_mb"], oracle["compressed_mb"])
            if oracle
            else None
        )
        row["gap_vs_zstd19_percent"] = pct_change(row["compressed_mb"], zstd19_mb)
        row["gap_vs_lzma6_percent"] = pct_change(row["compressed_mb"], lzma6_mb)
        row["gap_vs_lzma9_percent"] = pct_change(row["compressed_mb"], lzma9_mb)

    summary = {
        "artifact": {
            "name": "phase3_interleaved_ml_artifact_512mb.bin",
            "original_bytes": ORIGINAL_BYTES,
            "original_mb": mb(ORIGINAL_BYTES),
        },
        "whole_file_baselines": WHOLE_FILE_BASELINES,
        "adc_results": adc_rows,
    }

    lines = []

    lines.append("Phase 3 Interleaved ML Artifact Summary")
    lines.append("=" * 110)
    lines.append("")
    lines.append(f"Original size: {mb(ORIGINAL_BYTES):.2f} MB")
    lines.append("")

    lines.append("Whole-file baselines")
    lines.append("-" * 110)
    lines.append(
        f"{'Method':<14} {'Compressed MB':>14} {'Ratio':>10} {'Comp Time s':>14}"
    )
    lines.append("-" * 110)

    for name, item in WHOLE_FILE_BASELINES.items():
        lines.append(
            f"{name:<14} "
            f"{item['compressed_mb']:>14.2f} "
            f"{item['ratio']:>10.6f} "
            f"{item['compression_time_seconds']:>14.2f}"
        )

    lines.append("")
    lines.append("ADC results")
    lines.append("-" * 110)
    lines.append(
        f"{'Method':<18} {'Chunk':<8} {'Compressed MB':>14} {'Ratio':>10} "
        f"{'Comp Time s':>14} {'Gap vs Oracle':>15} {'Gap vs zstd19':>15} {'Choices'}"
    )
    lines.append("-" * 110)

    order = {
        "adc_balanced": 0,
        "adc_learned": 1,
        "adc_chunk_oracle": 2,
    }

    for row in sorted(adc_rows, key=lambda r: (r["chunk_size_bytes"], order.get(r["method"], 99))):
        gap_oracle = row["gap_vs_chunk_oracle_percent"]

        lines.append(
            f"{row['method']:<18} "
            f"{row['chunk_size']:<8} "
            f"{row['compressed_mb']:>14.2f} "
            f"{row['ratio']:>10.6f} "
            f"{row['compression_time_seconds']:>14.2f} "
            f"{gap_oracle:>14.2f}% "
            f"{row['gap_vs_zstd19_percent']:>14.2f}% "
            f"{row['choices']}"
        )

    lines.append("")
    lines.append("Key findings")
    lines.append("-" * 110)
    lines.append(
        "1. The learned selector nearly matches the chunk oracle, especially at 1 MB chunks."
    )
    lines.append(
        "2. At 256 KB chunks, learned ADC uses five compressors and is far smaller than the hand-written balanced selector."
    )
    lines.append(
        "3. Learned ADC beats whole-file zstd_3, zstd_10, and zstd_19 by compressed size on this artifact."
    )
    lines.append(
        "4. Whole-file lzma_6 and lzma_9 still produce smaller outputs than learned ADC on this artifact."
    )
    lines.append(
        "5. Smaller chunks improve routing diversity, while larger chunks preserve more compression context."
    )

    OUTPUT_TXT.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote {OUTPUT_TXT}")
    print(f"Wrote {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
import argparse
import time
from pathlib import Path

from adc_container import compress_bytes, sha256_bytes, write_adc
from chunk_features import extract_chunk_features


COMPRESSORS = [
    "store",
    "zstd_3",
    "zstd_10",
    "zstd_19",
    "lzma_6",
    "lzma_9",
    "bz2_9",
]


def compress_file_oracle(input_path: Path, output_path: Path, chunk_size: int) -> dict:
    chunks = []
    payload_parts = []

    original_offset = 0
    compressed_offset = 0
    index = 0

    choices = {}

    start_time = time.perf_counter()

    with open(input_path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break

            features = extract_chunk_features(data)

            best_name = None
            best_compressed = None
            best_time = None

            for compressor in COMPRESSORS:
                comp_start = time.perf_counter()
                compressed = compress_bytes(data, compressor)
                comp_time = time.perf_counter() - comp_start

                if best_compressed is None:
                    best_name = compressor
                    best_compressed = compressed
                    best_time = comp_time
                    continue

                if len(compressed) < len(best_compressed):
                    best_name = compressor
                    best_compressed = compressed
                    best_time = comp_time
                elif len(compressed) == len(best_compressed) and comp_time < best_time:
                    best_name = compressor
                    best_compressed = compressed
                    best_time = comp_time

            choices[best_name] = choices.get(best_name, 0) + 1

            payload_parts.append(best_compressed)

            chunks.append({
                "index": index,
                "original_offset": original_offset,
                "original_size": len(data),
                "compressed_offset": compressed_offset,
                "compressed_size": len(best_compressed),
                "compressor": best_name,
                "sha256": sha256_bytes(data),
                "features": features,
            })

            original_offset += len(data)
            compressed_offset += len(best_compressed)
            index += 1

    payload = b"".join(payload_parts)

    write_adc(
        input_path=input_path,
        output_path=output_path,
        chunk_size=chunk_size,
        mode="chunk_oracle_best_size",
        chunks=chunks,
        payload=payload,
    )

    elapsed = time.perf_counter() - start_time

    original_size = input_path.stat().st_size
    compressed_size = output_path.stat().st_size

    return {
        "input": str(input_path),
        "output": str(output_path),
        "mode": "chunk_oracle_best_size",
        "chunk_size": chunk_size,
        "chunks": len(chunks),
        "choices": choices,
        "original_size_bytes": original_size,
        "compressed_size_bytes": compressed_size,
        "compression_ratio": compressed_size / original_size if original_size else 1.0,
        "compression_time_seconds": elapsed,
    }


def parse_chunk_size(value: str) -> int:
    value = value.strip().lower()

    if value.endswith("kb"):
        return int(value[:-2]) * 1024

    if value.endswith("mb"):
        return int(value[:-2]) * 1024 * 1024

    return int(value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--chunk-size", default="1MB")

    args = parser.parse_args()

    result = compress_file_oracle(
        input_path=Path(args.input),
        output_path=Path(args.output),
        chunk_size=parse_chunk_size(args.chunk_size),
    )

    print("ADC chunk oracle compression complete")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
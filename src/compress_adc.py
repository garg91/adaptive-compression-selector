import argparse
import time
from pathlib import Path

from adc_container import compress_bytes, sha256_bytes, write_adc
from chunk_features import extract_chunk_features
from chunk_selector import choose_chunk_compressor
from chunk_selector_learned import choose_learned_chunk_compressor


def compress_file(input_path: Path, output_path: Path, chunk_size: int, mode: str) -> dict:
    chunks = []
    payload_parts = []

    original_offset = 0
    compressed_offset = 0
    index = 0

    start_time = time.perf_counter()

    with open(input_path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break

            features = extract_chunk_features(data)
            if mode == "learned":
                compressor = choose_learned_chunk_compressor(features, chunk_size=chunk_size)
            else:
                compressor = choose_chunk_compressor(features, mode=mode)
            compressed = compress_bytes(data, compressor)

            payload_parts.append(compressed)

            chunks.append({
                "index": index,
                "original_offset": original_offset,
                "original_size": len(data),
                "compressed_offset": compressed_offset,
                "compressed_size": len(compressed),
                "compressor": compressor,
                "sha256": sha256_bytes(data),
                "features": features,
            })

            original_offset += len(data)
            compressed_offset += len(compressed)
            index += 1

    payload = b"".join(payload_parts)

    write_adc(
        input_path=input_path,
        output_path=output_path,
        chunk_size=chunk_size,
        mode=mode,
        chunks=chunks,
        payload=payload,
    )

    elapsed = time.perf_counter() - start_time

    original_size = input_path.stat().st_size
    compressed_size = output_path.stat().st_size

    return {
        "input": str(input_path),
        "output": str(output_path),
        "mode": mode,
        "chunk_size": chunk_size,
        "chunks": len(chunks),
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
    parser.add_argument(
        "--mode", 
        default="balanced", 
        choices=["best_size", "balanced", "fast", "learned"],
    )

    args = parser.parse_args()

    result = compress_file(
        input_path=Path(args.input),
        output_path=Path(args.output),
        chunk_size=parse_chunk_size(args.chunk_size),
        mode=args.mode,
    )

    print("ADC compression complete")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
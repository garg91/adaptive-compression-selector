import bz2
import gzip
import json
import lzma
import math
import os
import time
import zlib
import zstandard as zstd
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, List, Tuple


DATA_DIR = Path("data")
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)


def read_file(path: Path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0

    counts = Counter(data)
    total = len(data)

    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log2(p)

    return entropy


def text_ratio(data: bytes) -> float:
    if not data:
        return 0.0

    printable = 0

    for b in data:
        # tab, newline, carriage return, and printable ASCII
        if b in (9, 10, 13) or 32 <= b <= 126:
            printable += 1

    return printable / len(data)


def unique_byte_count(data: bytes) -> int:
    return len(set(data))


def gzip_compress(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=9)


def gzip_decompress(data: bytes) -> bytes:
    return gzip.decompress(data)


def bz2_compress(data: bytes) -> bytes:
    return bz2.compress(data, compresslevel=9)


def bz2_decompress(data: bytes) -> bytes:
    return bz2.decompress(data)


def lzma_compress_preset_6(data: bytes) -> bytes:
    return lzma.compress(data, preset=6)


def lzma_compress_preset_9(data: bytes) -> bytes:
    return lzma.compress(data, preset=9)


def lzma_decompress(data: bytes) -> bytes:
    return lzma.decompress(data)


def zlib_compress(data: bytes) -> bytes:
    return zlib.compress(data, level=9)


def zlib_decompress(data: bytes) -> bytes:
    return zlib.decompress(data)


def zstd_compress_level_3(data: bytes) -> bytes:
    compressor = zstd.ZstdCompressor(level=3)
    return compressor.compress(data)


def zstd_compress_level_10(data: bytes) -> bytes:
    compressor = zstd.ZstdCompressor(level=10)
    return compressor.compress(data)


def zstd_compress_level_19(data: bytes) -> bytes:
    compressor = zstd.ZstdCompressor(level=19)
    return compressor.compress(data)


def zstd_decompress(data: bytes) -> bytes:
    decompressor = zstd.ZstdDecompressor()
    return decompressor.decompress(data)


def store_compress(data: bytes) -> bytes:
    return data


def store_decompress(data: bytes) -> bytes:
    return data


COMPRESSORS: Dict[str, Tuple[Callable[[bytes], bytes], Callable[[bytes], bytes]]] = {
    "store": (store_compress, store_decompress),
    "gzip_9": (gzip_compress, gzip_decompress),
    "zlib_9": (zlib_compress, zlib_decompress),
    "bz2_9": (bz2_compress, bz2_decompress),
    "lzma_6": (lzma_compress_preset_6, lzma_decompress),
    "lzma_9": (lzma_compress_preset_9, lzma_decompress),
    "zstd_3": (zstd_compress_level_3, zstd_decompress),
    "zstd_10": (zstd_compress_level_10, zstd_decompress),
    "zstd_19": (zstd_compress_level_19, zstd_decompress),
}


def infer_category(path: Path) -> str:
    parts = set(path.parts)

    if "logs_json" in parts:
        return "logs_json"
    if "source_packages" in parts:
        return "source_packages"
    if "docker_layers" in parts:
        return "docker_layers"
    if "ml_data" in parts:
        return "ml_data"

    return "unknown"


def benchmark_file(path: Path) -> List[dict]:
    data = read_file(path)

    file_entropy = shannon_entropy(data)
    file_text_ratio = text_ratio(data)
    file_unique_bytes = unique_byte_count(data)
    original_size = len(data)
    category = infer_category(path)

    rows = []

    for name, (compress_fn, decompress_fn) in COMPRESSORS.items():
        try:
            start = time.perf_counter()
            compressed = compress_fn(data)
            compression_time = time.perf_counter() - start

            start = time.perf_counter()
            decompressed = decompress_fn(compressed)
            decompression_time = time.perf_counter() - start

            if decompressed != data:
                raise ValueError(f"Decompressed data mismatch for {name}")

            compressed_size = len(compressed)
            ratio = compressed_size / original_size if original_size else 1.0

            rows.append({
                "file": str(path),
                "category": category,
                "extension": path.suffix.lower(),
                "compressor": name,
                "original_size_bytes": original_size,
                "compressed_size_bytes": compressed_size,
                "compression_ratio": ratio,
                "compression_time_seconds": compression_time,
                "decompression_time_seconds": decompression_time,
                "entropy": file_entropy,
                "text_ratio": file_text_ratio,
                "unique_byte_count": file_unique_bytes,
            })

        except Exception as e:
            rows.append({
                "file": str(path),
                "category": category,
                "extension": path.suffix.lower(),
                "compressor": name,
                "error": str(e),
                "original_size_bytes": original_size,
                "entropy": file_entropy,
                "text_ratio": file_text_ratio,
                "unique_byte_count": file_unique_bytes,
            })

    return rows


def find_files(root: Path) -> List[Path]:
    files = []

    for path in root.rglob("*"):
        if path.is_file():
            files.append(path)

    return files


def main() -> None:
    files = find_files(DATA_DIR)

    if not files:
        print("No files found in data/. Add files under data/logs_json, data/source_packages, data/docker_layers, or data/ml_data.")
        return

    all_rows = []

    for path in files:
        print(f"Benchmarking {path}")
        rows = benchmark_file(path)
        all_rows.extend(rows)

    output_path = RESULTS_DIR / "benchmark_results.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, indent=2)

    print(f"\nSaved results to {output_path}")


if __name__ == "__main__":
    main()
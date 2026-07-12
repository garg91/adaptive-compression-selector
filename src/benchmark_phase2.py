import bz2
import gzip
import json
import lzma
import math
import time
import zlib
import zstandard as zstd
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, List, Tuple


DATA_DIR = Path("data")
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

OUTPUT_PATH = RESULTS_DIR / "benchmark_results_phase2.json"


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

    # Phase 2 categories
    if "databases" in parts:
        return "databases"
    if "small_files" in parts:
        return "small_files"
    if "already_compressed" in parts:
        return "already_compressed"
    if "mixed_binary" in parts:
        return "mixed_binary"
    if "web_assets" in parts:
        return "web_assets"

    return "unknown"


def should_run_compressor(
    compressor_name: str,
    path: Path,
    category: str,
    extension: str,
    original_size_bytes: int,
    entropy: float,
    text_ratio_value: float,
    unique_bytes: int,
) -> bool:
    """
    Phase 2 benchmark guard.

    This keeps the benchmark useful without wasting hours on obviously bad
    combinations like lzma_9 on multi-GB random data.

    Important:
      - Phase 2 oracle means "best among tested compressors"
      - not necessarily "best among all possible compressors"
    """

    size_mb = original_size_bytes / (1024 * 1024)
    ext = extension.lower()

    # Always include these core tradeoff points.
    if compressor_name in {"store", "zstd_3", "zstd_10"}:
        return True

    # For small/medium files, run everything.
    if size_mb <= 256:
        return True

    # gzip/zlib were dominated in Phase 1. Keep them only for small files.
    if compressor_name in {"gzip_9", "zlib_9"}:
        return False

    # Already compressed extensions should not run slow compressors.
    if ext in {".gz", ".bz2", ".xz", ".zip", ".zst", ".7z", ".rar"}:
        return compressor_name in {"store", "zstd_3", "zstd_10"}

    # Already-compressed/media-like high-entropy files.
    if category == "already_compressed":
        if entropy > 7.2 and unique_bytes == 256:
            return compressor_name in {"store", "zstd_3", "zstd_10"}

    # Large high-entropy binary/random data.
    if entropy > 7.2 and unique_bytes == 256 and size_mb > 512:
        return compressor_name in {"store", "zstd_3", "zstd_10", "lzma_6"}

    # Very sparse files are worth trying bz2 and lzma.
    if entropy < 0.2:
        return compressor_name in {
            "store",
            "zstd_3",
            "zstd_10",
            "bz2_9",
            "lzma_6",
            "lzma_9",
        }

    # Large text-like files are worth testing strong compressors.
    if text_ratio_value > 0.80:
        if size_mb > 2048 and compressor_name == "zstd_19":
            return False
        return compressor_name in {
            "store",
            "zstd_3",
            "zstd_10",
            "bz2_9",
            "lzma_6",
            "lzma_9",
            "zstd_19",
        }

    # Structured categories where strong compression may still matter.
    if category in {"logs_json", "source_packages", "web_assets", "databases"}:
        if size_mb > 2048 and compressor_name == "zstd_19":
            return False
        return compressor_name in {
            "store",
            "zstd_3",
            "zstd_10",
            "bz2_9",
            "lzma_6",
            "lzma_9",
            "zstd_19",
        }

    # Mixed binary and large unknown files: avoid the slowest options.
    if size_mb > 1024:
        return compressor_name in {"store", "zstd_3", "zstd_10", "lzma_6"}

    return True


def skipped_row(
    path: Path,
    category: str,
    extension: str,
    compressor_name: str,
    original_size: int,
    entropy: float,
    text_ratio_value: float,
    unique_bytes: int,
) -> dict:
    return {
        "file": str(path),
        "category": category,
        "extension": extension,
        "compressor": compressor_name,
        "skipped": True,
        "skip_reason": "phase2_guard",
        "original_size_bytes": original_size,
        "entropy": entropy,
        "text_ratio": text_ratio_value,
        "unique_byte_count": unique_bytes,
    }


def benchmark_file(path: Path) -> List[dict]:
    data = read_file(path)

    file_entropy = shannon_entropy(data)
    file_text_ratio = text_ratio(data)
    file_unique_bytes = unique_byte_count(data)
    original_size = len(data)
    category = infer_category(path)
    extension = path.suffix.lower()

    rows = []

    for name, (compress_fn, decompress_fn) in COMPRESSORS.items():
        if not should_run_compressor(
            compressor_name=name,
            path=path,
            category=category,
            extension=extension,
            original_size_bytes=original_size,
            entropy=file_entropy,
            text_ratio_value=file_text_ratio,
            unique_bytes=file_unique_bytes,
        ):
            print(f"  Skipping {name}")
            rows.append(
                skipped_row(
                    path=path,
                    category=category,
                    extension=extension,
                    compressor_name=name,
                    original_size=original_size,
                    entropy=file_entropy,
                    text_ratio_value=file_text_ratio,
                    unique_bytes=file_unique_bytes,
                )
            )
            continue

        try:
            print(f"  Running {name}")

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
                "extension": extension,
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
                "extension": extension,
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
            # Skip marker files from dataset generation.
            if path.name.startswith(".phase2_") or path.name == ".complete":
                continue
            files.append(path)

    return files


def main() -> None:
    files = find_files(DATA_DIR)

    if not files:
        print("No files found in data/.")
        return

    print(f"Found {len(files)} files")
    print(f"Saving Phase 2 benchmark results to {OUTPUT_PATH}")
    print()

    all_rows = []

    for index, path in enumerate(files, start=1):
        size_mb = path.stat().st_size / (1024 * 1024)

        print("=" * 100)
        print(f"[{index}/{len(files)}] Benchmarking {path} ({size_mb:.2f} MB)")
        print("=" * 100)

        rows = benchmark_file(path)
        all_rows.extend(rows)

        # Save after every file so progress is not lost.
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(all_rows, f, indent=2)

        print(f"Saved progress to {OUTPUT_PATH}")
        print()

    print(f"\nSaved final Phase 2 results to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
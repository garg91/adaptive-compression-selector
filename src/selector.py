from pathlib import Path


def normalize_mode(mode: str) -> str:
    """
    Backward compatibility:
      - "balanced" behaves like "balanced_size"
    """
    if mode == "balanced":
        return "balanced_size"
    return mode


def choose_compressor(
    file_path: str,
    category: str,
    extension: str,
    original_size_bytes: int,
    entropy: float,
    text_ratio: float,
    unique_byte_count: int,
    mode: str = "balanced_size",
) -> str:
    """
    Choose a compressor based on Phase 1 benchmark results.

    mode:
      - "best_size": prioritize smallest compressed output
      - "balanced_size": prioritize strong compression ratio with moderate time savings
      - "balanced_fast": prioritize large speed gains while still compressing reasonably well
      - "fast": prioritize speed
      - "balanced": alias for "balanced_size"
    """

    mode = normalize_mode(mode)

    path = Path(file_path)
    ext = extension.lower()

    already_compressed_exts = {
        ".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mp3",
        ".zip", ".gz", ".xz", ".7z", ".rar", ".bz2", ".zst", ".pdf"
    }

    if ext in already_compressed_exts:
        return "store"

    # Very high entropy data.
    # Example: random_float32.npy.
    if entropy > 7.2 and unique_byte_count == 256:
        if mode == "best_size":
            return "lzma_9"
        if mode == "balanced_size":
            return "zstd_10"
        if mode == "balanced_fast":
            return "zstd_3"
        return "zstd_3"

    # Logs and JSON.
    # Your benchmark showed bz2_9 wins size, while zstd_3/zstd_10 are much faster.
    if category == "logs_json" or ext in {".log", ".json", ".ndjson"}:
        if mode == "best_size":
            return "bz2_9"
        if mode == "balanced_size":
            return "bz2_9"
        if mode == "balanced_fast":
            return "zstd_10"
        return "zstd_3"

    # Docker layers.
    if category == "docker_layers":
        if mode == "best_size":
            return "lzma_9"
        if mode == "balanced_size":
            # Small Docker layers do not benefit much from lzma_9 over lzma_6.
            if original_size_bytes < 20 * 1024 * 1024:
                return "lzma_6"
            return "lzma_9"
        if mode == "balanced_fast":
            return "zstd_10"
        return "zstd_3"

    # Source packages / tar archives.
    if category == "source_packages" or ext == ".tar":
        if mode == "fast":
            return "zstd_3"
        if mode == "balanced_fast":
            return "zstd_10"
        if mode == "balanced_size":
            # Tiny source packages: lzma_6 is effectively as good as lzma_9.
            if original_size_bytes < 10 * 1024 * 1024:
                return "lzma_6"
            # Lower-entropy source archives showed worthwhile lzma_9 gains.
            if entropy < 6.3:
                return "lzma_9"
            # Large high-entropy source archive: lzma_6 saves meaningful time.
            return "lzma_6"
        if original_size_bytes < 10 * 1024 * 1024:
            return "lzma_6"
        return "lzma_9"

    # ML data is mixed.
    if category == "ml_data":
        # Extremely sparse binary arrays.
        if entropy < 0.2:
            if mode == "best_size":
                return "bz2_9"
            if mode == "balanced_size":
                return "zstd_3"
            if mode == "balanced_fast":
                return "zstd_3"
            return "bz2_9"

        # Low-entropy labels or structured integer arrays.
        if entropy < 2.0:
            if mode == "best_size":
                return "lzma_9"
            if mode == "balanced_size":
                return "bz2_9"
            if mode == "balanced_fast":
                return "zstd_10"
            return "zstd_3"

        # Text-like ML data such as CSV.
        if text_ratio > 0.95:
            if mode == "best_size":
                return "lzma_6"
            if mode == "balanced_size":
                return "bz2_9"
            if mode == "balanced_fast":
                return "zstd_10"
            return "zstd_3"

        # High-entropy ML data.
        if entropy > 7.0:
            if mode == "best_size":
                return "lzma_9"
            if mode == "balanced_size":
                return "zstd_10"
            if mode == "balanced_fast":
                return "zstd_3"
            return "zstd_3"

        if mode == "fast":
            return "zstd_3"
        if mode == "balanced_fast":
            return "zstd_10"
        return "lzma_6"

    # Generic fallback.
    if mode == "fast":
        return "zstd_3"
    if mode == "balanced_fast":
        return "zstd_10"
    if mode == "best_size":
        return "lzma_9"
    return "lzma_6"
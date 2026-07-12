def choose_chunk_compressor(features: dict, mode: str = "balanced") -> str:
    entropy = features["entropy"]
    text_ratio = features["text_ratio"]
    zero_ratio = features["zero_ratio"]
    unique_bytes = features["unique_byte_count"]
    size_bytes = features["size_bytes"]

    if mode not in {"best_size", "balanced", "fast"}:
        raise ValueError(f"Unknown mode: {mode}")

    # Very small chunks should avoid high-overhead slow codecs.
    if size_bytes < 16 * 1024:
        if mode == "best_size":
            return "zstd_19"
        if mode == "balanced":
            return "zstd_10"
        return "zstd_3"

    # High-entropy chunks are unlikely to compress well.
    if entropy > 7.6 and unique_bytes >= 240:
        if mode == "best_size":
            return "zstd_3"
        return "store"

    # Sparse / zero-heavy chunks.
    if zero_ratio > 0.20:
        if mode == "fast":
            return "zstd_10"
        return "lzma_6"

    # Text-like chunks.
    if text_ratio > 0.85:
        if mode == "best_size":
            return "zstd_19"
        if mode == "balanced":
            return "zstd_10"
        return "zstd_3"

    # Low byte diversity chunks.
    if unique_bytes < 64:
        if mode == "fast":
            return "zstd_10"
        return "lzma_6"

    # Default mixed data.
    if mode == "best_size":
        return "zstd_19"
    if mode == "balanced":
        return "zstd_10"
    return "zstd_3"
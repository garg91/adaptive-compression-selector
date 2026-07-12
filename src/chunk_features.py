import math
from collections import Counter


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
        if b in (9, 10, 13) or 32 <= b <= 126:
            printable += 1

    return printable / len(data)


def zero_ratio(data: bytes) -> float:
    if not data:
        return 0.0

    return data.count(0) / len(data)


def unique_byte_count(data: bytes) -> int:
    return len(set(data))


def extract_chunk_features(data: bytes) -> dict:
    return {
        "size_bytes": len(data),
        "entropy": shannon_entropy(data),
        "text_ratio": text_ratio(data),
        "zero_ratio": zero_ratio(data),
        "unique_byte_count": unique_byte_count(data),
    }
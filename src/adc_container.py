import bz2
import hashlib
import json
import lzma
import struct
import zstandard as zstd
from pathlib import Path


MAGIC = b"ADC1"
HEADER_LEN_STRUCT = struct.Struct("<Q")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compress_bytes(data: bytes, compressor: str) -> bytes:
    if compressor == "store":
        return data

    if compressor == "bz2_9":
        return bz2.compress(data, compresslevel=9)

    if compressor == "lzma_6":
        return lzma.compress(data, preset=6)

    if compressor == "lzma_9":
        return lzma.compress(data, preset=9)

    if compressor == "zstd_3":
        return zstd.ZstdCompressor(level=3).compress(data)

    if compressor == "zstd_10":
        return zstd.ZstdCompressor(level=10).compress(data)

    if compressor == "zstd_19":
        return zstd.ZstdCompressor(level=19).compress(data)

    raise ValueError(f"Unknown compressor: {compressor}")


def decompress_bytes(data: bytes, compressor: str) -> bytes:
    if compressor == "store":
        return data

    if compressor == "bz2_9":
        return bz2.decompress(data)

    if compressor in {"lzma_6", "lzma_9"}:
        return lzma.decompress(data)

    if compressor in {"zstd_3", "zstd_10", "zstd_19"}:
        return zstd.ZstdDecompressor().decompress(data)

    raise ValueError(f"Unknown compressor: {compressor}")


def write_adc(
    input_path: Path,
    output_path: Path,
    chunk_size: int,
    mode: str,
    chunks: list,
    payload: bytes,
) -> None:
    used_compressors = []

    for chunk in chunks:
        name = chunk["compressor"]
        if name not in used_compressors:
            used_compressors.append(name)

    compressor_table = [
        {"id": index, "name": name}
        for index, name in enumerate(used_compressors)
    ]

    compressor_to_id = {
        item["name"]: item["id"]
        for item in compressor_table
    }

    header_chunks = []

    for chunk in chunks:
        header_chunks.append({
            "index": chunk["index"],
            "original_offset": chunk["original_offset"],
            "original_size": chunk["original_size"],
            "compressed_offset": chunk["compressed_offset"],
            "compressed_size": chunk["compressed_size"],
            "compressor_id": compressor_to_id[chunk["compressor"]],
            "sha256": chunk["sha256"],
            "features": chunk["features"],
        })

    header = {
        "format": "ADC",
        "version": 1,
        "mode": mode,
        "original_file": str(input_path),
        "original_size": input_path.stat().st_size,
        "chunk_size": chunk_size,
        "compressor_table": compressor_table,
        "chunks": header_chunks,
    }

    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "wb") as f:
        f.write(MAGIC)
        f.write(HEADER_LEN_STRUCT.pack(len(header_bytes)))
        f.write(header_bytes)
        f.write(payload)


def read_adc_header(f):
    magic = f.read(len(MAGIC))
    if magic != MAGIC:
        raise ValueError("Not an ADC1 file")

    header_len_bytes = f.read(HEADER_LEN_STRUCT.size)
    if len(header_len_bytes) != HEADER_LEN_STRUCT.size:
        raise ValueError("Truncated ADC header length")

    header_len = HEADER_LEN_STRUCT.unpack(header_len_bytes)[0]
    header_bytes = f.read(header_len)

    if len(header_bytes) != header_len:
        raise ValueError("Truncated ADC header")

    header = json.loads(header_bytes.decode("utf-8"))
    payload_start = len(MAGIC) + HEADER_LEN_STRUCT.size + header_len

    return header, payload_start
import argparse
import time
from pathlib import Path

from adc_container import decompress_bytes, read_adc_header, sha256_bytes


def decompress_file(input_path: Path, output_path: Path) -> dict:
    start_time = time.perf_counter()

    with open(input_path, "rb") as f:
        header, payload_start = read_adc_header(f)

        compressor_table = {
            item["id"]: item["name"]
            for item in header["compressor_table"]
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "wb") as out:
            for chunk in header["chunks"]:
                compressor = compressor_table[chunk["compressor_id"]]

                f.seek(payload_start + chunk["compressed_offset"])
                compressed = f.read(chunk["compressed_size"])

                data = decompress_bytes(compressed, compressor)

                if len(data) != chunk["original_size"]:
                    raise ValueError(
                        f"Chunk {chunk['index']} size mismatch: "
                        f"expected {chunk['original_size']}, got {len(data)}"
                    )

                if sha256_bytes(data) != chunk["sha256"]:
                    raise ValueError(f"Chunk {chunk['index']} SHA-256 mismatch")

                out.write(data)

    elapsed = time.perf_counter() - start_time

    return {
        "input": str(input_path),
        "output": str(output_path),
        "decompression_time_seconds": elapsed,
        "output_size_bytes": output_path.stat().st_size,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")

    args = parser.parse_args()

    result = decompress_file(
        input_path=Path(args.input),
        output_path=Path(args.output),
    )

    print("ADC decompression complete")
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
# Adaptive Compression Selector

An experimental adaptive compression selector that chooses between compression algorithms based on file features such as entropy, text ratio, extension, category, byte diversity, and file size.

The project benchmarks multiple compressors and evaluates rule-based selector modes against fixed baselines, best-size oracles, and Pareto-aware strategies. The long-term goal is to move from file-level compressor selection to chunk-level mixed compression for heterogeneous machine-learning artifacts.

## Compressors Tested

- `store`
- `gzip_9`
- `zlib_9`
- `bz2_9`
- `lzma_6`
- `lzma_9`
- `zstd_3`
- `zstd_10`
- `zstd_19`

## Selector Modes

### `best_size`

Prioritizes smallest compressed output. In Phase 1, this matched the best-size oracle exactly. In Phase 2, it approached the oracle but exposed the limits of file-level rule-based selection on a much larger and more heterogeneous corpus.

### `balanced_size`

Targets near-archival compression size with meaningful compression-time savings. Phase 2 showed that this mode needs retuning because the larger corpus favored `zstd_19` much more often than the original Phase 1 rules expected.

### `balanced_fast`

Targets `zstd_10`-like practical compression speed and ratio. In Phase 2, this was the strongest practical selector mode, landing close to fixed `zstd_10` while reducing compression time.

### `fast`

Targets `zstd_3`-like throughput-first compression. In Phase 2, fixed `zstd_3` was generally a stronger fast baseline than the current rule-based `fast` selector, so this mode should be simplified or retuned.

## Phase 1 Results

Phase 1 tested a mixed 1.3 GB corpus across Docker layers, logs/JSON, ML data, and source packages.

| Strategy | Compressed MB | Compression Time |
|---|---:|---:|
| Oracle best size | 352.68 MB | 314.06s |
| Selector best size | 352.68 MB | 314.06s |
| Always `lzma_9` | 354.04 MB | 334.40s |
| Selector balanced size | 355.86 MB | 261.38s |
| Selector balanced fast | 414.86 MB | 13.27s |
| Selector fast | 450.07 MB | 3.19s |

Key Phase 1 finding:

> The adaptive best-size selector matched the oracle exactly. The balanced-size mode stayed within 0.51% of fixed `lzma_9` compressed size while reducing compression time by 21.84%.

## Phase 2 Benchmark

Phase 2 scaled the benchmark to a much larger corpus with more categories and many more files.

| Metric | Value |
|---|---:|
| Total files | 120,053 |
| Total input size | 39,874.81 MB |
| Loaded benchmark rows | 1,080,477 |
| Valid benchmark rows | 1,080,385 |
| Skipped rows | 92 |
| Error rows | 0 |
| Malformed rows | 0 |

### Phase 2 Corpus Breakdown

| Category | Files | Original MB |
|---|---:|---:|
| `already_compressed` | 7 | 4,377.74 |
| `databases` | 2 | 1,183.67 |
| `docker_layers` | 40,010 | 3,830.19 |
| `logs_json` | 7 | 6,234.54 |
| `mixed_binary` | 4 | 5,120.00 |
| `ml_data` | 11 | 11,468.48 |
| `small_files` | 50,001 | 1,274.04 |
| `source_packages` | 30,008 | 4,338.16 |
| `web_assets` | 3 | 2,048.00 |

Phase 2 is best described as a near-exhaustive benchmark: only 92 compressor-file combinations were skipped out of more than 1.08 million rows, and no benchmark errors occurred.

## Phase 2 Findings

### 1. `zstd_19` dominated best-size wins by file count

The best-size oracle selected compressors as follows:

| Compressor | Oracle Wins |
|---|---:|
| `zstd_19` | 118,599 |
| `zstd_10` | 1,311 |
| `zstd_3` | 93 |
| `lzma_9` | 32 |
| `bz2_9` | 7 |
| `lzma_6` | 6 |
| `store` | 5 |

This result was mainly driven by categories with many small/source/container-style files:

| Category | Dominant Oracle Winners |
|---|---|
| `small_files` | `zstd_19`: 49,437 wins; `zstd_10`: 563 wins |
| `source_packages` | `zstd_19`: 29,624 wins; `zstd_10`: 283 wins; `zstd_3`: 93 wins |
| `docker_layers` | `zstd_19`: 39,535 wins; `zstd_10`: 465 wins |

### 2. The practical Pareto family was mostly `store` + Zstandard

Global Pareto frontier counts showed that the most frequently useful compressors were:

| Compressor | Pareto Frontier Count |
|---|---:|
| `store` | 120,049 |
| `zstd_10` | 119,971 |
| `zstd_19` | 118,616 |
| `zstd_3` | 2,646 |
| `zlib_9` | 68 |
| `lzma_6` | 34 |
| `lzma_9` | 32 |
| `bz2_9` | 15 |

This suggests that, for many Phase 2 workloads, the practical file-level choice is often among `store`, `zstd_3`, `zstd_10`, and `zstd_19`, while `lzma` and `bz2` matter mostly for specific structured or large files.

### 3. `balanced_fast` was the strongest practical selector mode

The strongest practical selector result was `selector_balanced_fast` compared with fixed `zstd_10`:

| Strategy | Ratio | Compressed MB | Compression Time | Decompression Time |
|---|---:|---:|---:|---:|
| Always `zstd_10` | 0.3239 | 12,914.03 MB | 141.23s | 19.95s |
| Selector `balanced_fast` | 0.3300 | 13,158.37 MB | 120.68s | 20.26s |

Interpretation:

> `balanced_fast` was approximately 1.89% larger than fixed `zstd_10`, but reduced compression time by approximately 14.55%.

### 4. `fast` needs retuning

Fixed `zstd_3` outperformed the current `selector_fast` mode overall:

| Strategy | Ratio | Compressed MB | Compression Time | Decompression Time |
|---|---:|---:|---:|---:|
| Always `zstd_3` | 0.3295 | 13,140.31 MB | 32.33s | 22.05s |
| Selector `fast` | 0.3356 | 13,380.82 MB | 43.10s | 25.97s |

Interpretation:

> The current `fast` selector was both larger and slower than fixed `zstd_3`, so the fast mode should either default more aggressively to `zstd_3` or be redesigned.

### 5. ML data showed the most interesting compressor diversity

The `ml_data` category was the strongest motivation for Phase 3. Unlike small-file, source-package, and Docker-layer categories, where Zstandard variants dominated, ML data showed oracle wins spread across several compressor families:

| Compressor | ML Oracle Wins |
|---|---:|
| `lzma_9` | 4 |
| `lzma_6` | 3 |
| `bz2_9` | 2 |
| `store` | 1 |
| `zstd_19` | 1 |

ML data statistics:

| Metric | Value |
|---|---:|
| Files | 11 |
| Original MB | 11,468.48 |
| Oracle compressed MB | 2,946.18 |
| Oracle ratio | 0.2569 |

Interpretation:

> ML-style data is heterogeneous enough that no single compressor family dominated all files. This supports the Phase 3 direction: chunk-level mixed compression for ML artifacts.

## Important Interpretation Notes

Some fixed-compressor baselines have partial coverage because a small number of compressor-file combinations were skipped by feasibility guards. For example, `zstd_3`, `zstd_10`, and `store` have 100% coverage, while `lzma_9`, `zstd_19`, `gzip_9`, and `zlib_9` are missing a small number of rows.

Because of this, headline comparisons should either:

1. use full-coverage strategies only, or
2. restrict all strategies to a common subset of files where every compared compressor ran.

Phase 2 should therefore be described as a near-exhaustive benchmark with a small number of guarded skips, not as a perfectly complete full matrix.

## Research Direction: Phase 3

Phase 1 and Phase 2 evaluate file-level compressor selection:

```text
one file -> one selected compressor
```

Phase 3 will move to chunk-level mixed compression:

```text
one file -> chunks -> per-chunk compressor selection -> one self-describing compressed container
```

The target domain is machine-learning artifacts, where single files may contain multiple internal data types:

- dense float tensors
- sparse tensors or zero-heavy chunks
- integer labels
- token vocabularies
- JSON/YAML metadata
- optimizer state
- embedding tables
- already-compressed media or binary payloads

### Phase 3 Goals

- Split large ML artifacts into chunks.
- Extract chunk-level features such as entropy, text ratio, zero ratio, byte diversity, and local compressibility.
- Select a compressor per chunk.
- Store all compressed chunks in one self-describing container.
- Include only metadata for compressors actually used in the file.
- Compare chunk-level adaptive compression against whole-file fixed compressors, the Phase 2 file-level selector, and a chunk-level oracle.

### Proposed Container Design

The compressed output should use a local compressor table instead of storing metadata for every supported compressor.

Example:

```json
{
  "format": "ADC1",
  "version": 1,
  "original_size": 987654321,
  "chunk_size": 1048576,
  "compressor_table": [
    {"id": 0, "codec": "zstd", "level": 10},
    {"id": 1, "codec": "lzma", "preset": 6},
    {"id": 2, "codec": "store"}
  ],
  "chunks": [
    {
      "index": 0,
      "offset": 0,
      "original_size": 1048576,
      "compressed_size": 310222,
      "compressor_id": 0,
      "sha256": "..."
    }
  ]
}
```

This keeps each compressed file self-describing but minimal: if a file uses only three compressor configurations, the header records only those three.

### Phase 3 Evaluation Plan

For each ML artifact type, compare:

- whole-file `store`
- whole-file `zstd_3`
- whole-file `zstd_10`
- whole-file `zstd_19`
- whole-file `lzma_6`
- whole-file `lzma_9`
- Phase 2 file-level selector
- Phase 3 chunk-level selector
- Phase 3 chunk-level oracle

Primary metrics:

- compressed size
- compression time
- decompression time
- metadata overhead
- random-access potential
- selector regret versus chunk oracle

## Project Structure

```text
src/
  benchmark.py
  benchmark_phase2.py
  selector.py
  evaluate_selector.py
  evaluate_selector_phase2.py
  evaluate_by_category.py
  evaluate_by_category_phase2.py
  per_file_report.py
  per_file_report_phase2.py
  pareto_report.py
  pareto_report_phase2.py
  evaluate_pareto_selector.py
  evaluate_pareto_selector_phase2.py
  final_summary_report.py
  final_summary_report_phase2.py
  compact_phase2_summary.py

results/
  benchmark_results.json
  benchmark_results_phase2.json
  final_summary_report.txt
  final_summary_report_phase2.txt
  compact_phase2_summary.txt
  selector_evaluation.json
  selector_evaluation_phase2.json
  pareto_selector_evaluation.json
  pareto_selector_evaluation_phase2.json
```

## Setup

This project requires Python 3.10+.

On Ubuntu/Debian, install Python virtual environment support:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
```

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Run Phase 1

Run benchmark:

```bash
python3 src/benchmark.py
```

Evaluate selector:

```bash
python3 src/evaluate_selector.py
```

Generate reports:

```bash
python3 src/evaluate_by_category.py
python3 src/per_file_report.py
python3 src/pareto_report.py
python3 src/evaluate_pareto_selector.py
python3 src/final_summary_report.py
```

## Run Phase 2

Run the Phase 2 benchmark:

```bash
python3 src/benchmark_phase2.py
```

Generate Phase 2 reports:

```bash
python3 src/evaluate_selector_phase2.py
python3 src/evaluate_by_category_phase2.py
python3 src/per_file_report_phase2.py
python3 src/pareto_report_phase2.py
python3 src/evaluate_pareto_selector_phase2.py
python3 src/final_summary_report_phase2.py
python3 src/compact_phase2_summary.py
```

For large Phase 2 outputs, prefer the compact summary:

```text
results/compact_phase2_summary.txt
```

The full per-file and Pareto reports may be hundreds of MB for the 120k-file benchmark.

## Notes

The `data/` directory is intentionally excluded from GitHub because it contains large benchmark input files.

To reproduce the benchmark, users need to create or provide their own `data/` directory with files organized into categories such as:

```text
data/
  already_compressed/
  databases/
  docker_layers/
  logs_json/
  mixed_binary/
  ml_data/
  small_files/
  source_packages/
  web_assets/
```

## Current Conclusion

Phase 1 showed that a simple file-level rule-based selector can match or approach an oracle on a small heterogeneous corpus. Phase 2 showed that, at larger scale, Zstandard variants dominate many small/source/container-style workloads, while ML data exhibits more diverse compressor behavior.

The main research direction is therefore shifting from general file-level selection to adaptive mixed compression for ML artifacts, where different chunks inside a single file may benefit from different compressors.

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

## Phase 3: Mixed-Compression ADC Container

Phase 3 extends the project from file-level compressor selection to chunk-level mixed compression.

Instead of choosing one compressor for an entire file, Phase 3 splits an artifact into chunks, extracts chunk-level features, selects a compressor per chunk, and writes one self-describing `.adc` container that can be decompressed bit-exactly.

```text
one file -> chunks -> per-chunk features -> per-chunk compressor -> one .adc container
```

The target domain is machine-learning artifacts, where single files may contain multiple internal data regimes:

- dense float tensor regions
- sparse or zero-heavy tensor regions
- integer label arrays
- token/text regions
- JSON/YAML-like metadata
- optimizer state
- embedding tables
- already-compressed or high-entropy payloads

### ADC Container Design

The `.adc` format uses:

```text
magic bytes -> header length -> JSON header -> compressed payload bytes
```

Each container stores a file-local compressor table. If a file uses only three compressor configurations, the header records only those three, and chunks reference them by compact local IDs.

Example header shape:

```json
{
  "format": "ADC",
  "version": 1,
  "mode": "learned",
  "original_size": 536870912,
  "chunk_size": 262144,
  "compressor_table": [
    {"id": 0, "name": "lzma_6"},
    {"id": 1, "name": "zstd_19"},
    {"id": 2, "name": "zstd_10"},
    {"id": 3, "name": "store"},
    {"id": 4, "name": "zstd_3"}
  ],
  "chunks": [
    {
      "index": 0,
      "original_offset": 0,
      "original_size": 262144,
      "compressed_offset": 0,
      "compressed_size": 1892,
      "compressor_id": 0,
      "sha256": "...",
      "features": {
        "entropy": 4.7464,
        "text_ratio": 1.0,
        "zero_ratio": 0.0,
        "unique_byte_count": 46
      }
    }
  ]
}
```

The SHA-256 stored per chunk is used to verify exact decompression.

### Phase 3 Synthetic Interleaved ML Artifact

A 512 MB synthetic interleaved ML artifact was generated to simulate frequent data-regime changes inside a single file. The artifact alternates between metadata-like text, sparse tensor-like bytes, dense float-like bytes, label-like integer bytes, high-entropy bytes, and already-compressed regions.

This artifact is intentionally harder than the earlier contiguous mixed artifact because the data regimes switch frequently.

### Phase 3 Whole-File Baselines

| Method | Compressed MB | Ratio | Compression Time |
|---|---:|---:|---:|
| `zstd_3` | 138.08 | 0.269685 | 0.31s |
| `zstd_10` | 137.25 | 0.268070 | 1.00s |
| `zstd_19` | 135.57 | 0.264783 | 47.21s |
| `lzma_6` | 127.26 | 0.248555 | 36.41s |
| `lzma_9` | 125.38 | 0.244884 | 55.85s |
| `bz2_9` | 148.28 | 0.289605 | 42.57s |

### Phase 3 ADC Results

| Method | Chunk Size | Compressed MB | Ratio | Compression Time | Gap vs Chunk Oracle | Codec Choices |
|---|---:|---:|---:|---:|---:|---|
| ADC balanced | 256 KB | 143.85 | 0.280954 | 35.74s | +12.72% | `zstd_10`, `lzma_6`, `store` |
| ADC learned | 256 KB | 127.89 | 0.249793 | 67.58s | +0.22% | `lzma_6`, `zstd_19`, `zstd_10`, `store`, `zstd_3` |
| ADC chunk oracle | 256 KB | 127.61 | 0.249241 | 225.36s | 0.00% | `lzma_6`, `zstd_19`, `zstd_10`, `store`, `zstd_3` |
| ADC balanced | 1 MB | 133.89 | 0.261500 | 49.86s | +4.35% | `lzma_6`, `zstd_10` |
| ADC learned | 1 MB | 128.33 | 0.250645 | 64.66s | +0.02% | `lzma_6`, `zstd_19` |
| ADC chunk oracle | 1 MB | 128.30 | 0.250589 | 195.24s | 0.00% | `lzma_6`, `zstd_19`, `zstd_10` |
| ADC balanced | 4 MB | 128.48 | 0.250930 | 60.33s | +0.01% | `lzma_6` |
| ADC learned | 4 MB | 128.47 | 0.250919 | 68.01s | +0.01% | `lzma_6`, `lzma_9` |
| ADC chunk oracle | 4 MB | 128.46 | 0.250895 | 191.13s | 0.00% | `lzma_6`, `lzma_9` |

### Phase 3 Learned Selector

A chunk-oracle dataset was extracted from the oracle ADC containers. Each row maps chunk-level features to the best compressor found by trying all candidate compressors on that chunk.

Dataset location:

```text
datasets/phase3/chunk_oracle_dataset.csv
```

Dataset size:

| Metric | Value |
|---|---:|
| Rows | 2,688 |
| CSV size | 665 KB |
| Chunk sizes | 256 KB, 1 MB, 4 MB |

Oracle labels by compressor:

| Compressor | Rows |
|---|---:|
| `lzma_6` | 1,128 |
| `zstd_19` | 770 |
| `zstd_10` | 394 |
| `store` | 292 |
| `zstd_3` | 81 |
| `lzma_9` | 23 |

A decision-tree selector was trained on entropy, text ratio, zero ratio, byte diversity, chunk size, and original chunk size.

Training summary:

| Metric | Value |
|---|---:|
| Rows | 2,688 |
| Accuracy | 0.92 |
| Weighted F1 | 0.93 |
| Macro F1 | 0.84 |

The learned selector found a clean top-level rule for incompressible chunks:

```text
if entropy > 7.70:
    store
```

### Phase 3 Findings

1. The `.adc` container successfully supports chunk-level mixed compression and bit-exact decompression.
2. The learned selector nearly matched the chunk oracle. At 256 KB chunks, learned ADC came within 0.22% of the oracle.
3. At 256 KB chunks, learned ADC reduced compressed size by about 11.1% compared with the hand-written balanced selector.
4. Learned ADC beat whole-file `zstd_3`, `zstd_10`, and `zstd_19` in compressed size on the interleaved ML artifact.
5. Learned ADC did not beat whole-file `lzma_6` or `lzma_9`, but the best learned result was within roughly 0.5% of whole-file `lzma_6`.
6. Smaller chunks improved routing diversity, while larger chunks preserved more compression context. This exposes a core tradeoff in chunk-level adaptive compression.

The strongest current Phase 3 result is:

> On a 512 MB interleaved synthetic ML artifact, a learned chunk-level selector used five compressors inside one `.adc` container, reduced compressed size by approximately 11.1% compared with the hand-written balanced selector, came within 0.22% of the chunk oracle, and beat whole-file `zstd_3`, `zstd_10`, and `zstd_19` by compressed size while preserving exact decompression.

## Project Structure

```text
src/
  # Phase 1 / Phase 2 file-level benchmarking
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

  # Phase 3 ADC container and chunk-level selection
  adc_container.py
  chunk_features.py
  chunk_selector.py
  chunk_selector_learned.py
  compress_adc.py
  decompress_adc.py
  compress_adc_oracle.py
  generate_phase3_interleaved_ml_artifact.py
  extract_adc_oracle_dataset.py
  analyze_chunk_oracle_dataset.py
  train_chunk_selector.py
  phase3_summary_report.py

datasets/
  phase3/
    chunk_oracle_dataset.csv

results/
  final_summary_report.txt
  final_summary_report_phase2.txt
  compact_phase2_summary.txt
  phase3_interleaved/
    phase3_summary_report.txt
    phase3_summary_report.json
```

Large generated artifacts such as raw benchmark JSON files, `.adc` containers, decompressed `.out` files, per-file reports, and full Pareto reports should generally stay out of GitHub.

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

## Run Phase 3

Generate the 512 MB interleaved ML artifact:

```bash
python3 src/generate_phase3_interleaved_ml_artifact.py \
  --output data/ml_data/phase3_interleaved_ml_artifact_512mb.bin \
  --target-mb 512 \
  --regime-block-kb 256
```

Compress using the hand-written balanced ADC selector:

```bash
mkdir -p results/phase3_interleaved

python3 src/compress_adc.py \
  data/ml_data/phase3_interleaved_ml_artifact_512mb.bin \
  results/phase3_interleaved/interleaved_256kb_balanced.adc \
  --chunk-size 256KB \
  --mode balanced
```

Compress using the chunk oracle:

```bash
python3 src/compress_adc_oracle.py \
  data/ml_data/phase3_interleaved_ml_artifact_512mb.bin \
  results/phase3_interleaved/interleaved_256kb_oracle.adc \
  --chunk-size 256KB
```

Extract the chunk-oracle dataset:

```bash
python3 src/extract_adc_oracle_dataset.py \
  results/phase3_interleaved/interleaved_256kb_oracle.adc \
  results/phase3_interleaved/interleaved_1mb_oracle.adc \
  results/phase3_interleaved/interleaved_4mb_oracle.adc
```

Train the learned chunk selector:

```bash
python3 src/train_chunk_selector.py
```

Compress using the learned ADC selector:

```bash
python3 src/compress_adc.py \
  data/ml_data/phase3_interleaved_ml_artifact_512mb.bin \
  results/phase3_interleaved/interleaved_256kb_learned.adc \
  --chunk-size 256KB \
  --mode learned
```

Verify exact decompression:

```bash
python3 src/decompress_adc.py \
  results/phase3_interleaved/interleaved_256kb_learned.adc \
  results/phase3_interleaved/interleaved_256kb_learned.out

cmp \
  data/ml_data/phase3_interleaved_ml_artifact_512mb.bin \
  results/phase3_interleaved/interleaved_256kb_learned.out
```

If `cmp` prints nothing, decompression is bit-exact.

Generate the compact Phase 3 summary report:

```bash
python3 src/phase3_summary_report.py
cat results/phase3_interleaved/phase3_summary_report.txt
```

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

Phase 1 showed that a simple file-level rule-based selector can match an oracle on a small heterogeneous corpus. Phase 2 showed that, at larger scale, Zstandard variants dominate many small/source/container-style workloads, while ML data exhibits more diverse compressor behavior.

Phase 3 moved the project from file-level selection to chunk-level mixed compression. The current `.adc` prototype supports per-chunk compressor selection, self-describing containers, exact decompression, chunk-oracle evaluation, and a learned decision-tree selector trained from oracle labels.

The strongest current result is that learned ADC nearly matched the chunk oracle on a 512 MB interleaved ML artifact and beat whole-file `zstd_3`, `zstd_10`, and `zstd_19` by compressed size. Whole-file `lzma_6` and `lzma_9` remain stronger size-only baselines on this artifact, so the next research target is improving learned selection, testing real ML artifacts, and evaluating size-time tradeoffs rather than only compressed size.

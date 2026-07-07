# Adaptive Compression Selector

An experimental adaptive compression selector that chooses between compression algorithms based on file features such as entropy, text ratio, extension, category, and byte diversity.

The project benchmarks multiple compressors and evaluates rule-based selector modes against fixed baselines and Pareto-aware oracle strategies.

## Compressors Tested

- store
- gzip
- zlib
- bz2
- lzma
- zstd

## Selector Modes

### `best_size`

Prioritizes smallest compressed output. In Phase 1, this matched the best-size oracle exactly.

### `balanced_size`

Targets near-`lzma_9` compression size with meaningful compression-time savings.

### `balanced_fast`

Targets `zstd_10`-like practical compression speed and ratio.

### `fast`

Targets `zstd_3`-like throughput-first compression.

## Phase 1 Results

Tested on a mixed 1.3 GB corpus across Docker layers, logs/JSON, ML data, and source packages.

| Strategy | Compressed MB | Compression Time |
|---|---:|---:|
| Oracle best size | 352.68 MB | 314.06s |
| Selector best size | 352.68 MB | 314.06s |
| Always lzma_9 | 354.04 MB | 334.40s |
| Selector balanced size | 355.86 MB | 261.38s |
| Selector balanced fast | 414.86 MB | 13.27s |
| Selector fast | 450.07 MB | 3.19s |

Key result:

> The adaptive best-size selector matched the oracle exactly. The balanced-size mode stayed within 0.51% of fixed `lzma_9` compressed size while reducing compression time by 21.84%.

## Project Structure

```text
src/
  benchmark.py
  selector.py
  evaluate_selector.py
  evaluate_by_category.py
  per_file_report.py
  pareto_report.py
  evaluate_pareto_selector.py
  final_summary_report.py

results/
  final_summary_report.txt
  selector_evaluation.json
  pareto_selector_evaluation.json
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

## Run

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

## Notes

The `data/` directory is intentionally excluded from GitHub because it contains large benchmark input files.

To reproduce the benchmark, users need to create or provide their own `data/` directory with files organized into categories such as:

```text
data/
  docker_layers/
  logs_json/
  ml_data/
  source_packages/
```
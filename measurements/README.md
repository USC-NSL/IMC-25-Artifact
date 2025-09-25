# Measurements Directory

This directory contains scripts and tools for running actual measurements using the `warctradeoff` package in this repository. The measurements are designed to evaluate the efficiency vs. fidelity tradeoffs in web archives by comparing dynamic crawling, static crawling, and hybrid approaches.

## Key Components

### Recording Scripts
- **`auto_record.py`** - Automated recording of web pages using webrecorder
- **`auto_replay.py`** - Automated replay of recorded dynamic pages using pywb
- **`auto_replay_static.py`** - Automated replay of recorded static (with dynamic companied) pages using pywb
- **`auto_replay_patch.py`** - Replay with patching capabilities for resource augmentation


### Analysis Scripts
- **`infer_diff.py`** - Analyze differences in inferred resources
- **`layout_diff.py`** - Compare layout differences between original and replayed pages
- **`patch_diff.py`** - Analyze differences introduced by patching
- **`fetch_inferrable.py`** - Fetch resources that can be inferred from dynamic crawls

### Data Management
- **`extract_upload.py`** - Extract and upload measurement data
- **`patch_upload.py`** - Upload patched resources
- **`utils.py`** - Utility functions for measurement coordination

### Data Directories
- **`data/`** - Input dataset URLs
- **`diffs/`** - Layout tree comparison results
- **`e2e/`** - End-to-end measurement bootstrap scripts
- **`metadata/`** - Metadata for input data

## Measurement Workflow

### 1. Recording Phase
1. Use webrecorder extension to record web pages
2. Download WARC files from webrecorder
3. Import WARC files into pywb for replay
4. Collect execution and request information
5. Gather screenshots and fidelity measurements

### 2. Replay Phase
1. Load pages using pywb
2. Remove Wayback banners for fidelity consistency
3. Collect execution and request information
4. Gather screenshots and fidelity measurements
5. Compare with original recordings

### 3. Analysis Phase
1. Extract differences between original and replayed content
2. Analyze layout and resource differences
3. Evaluate the effectiveness of resource patching
4. Generate measurement reports

## Example usages

> Most measurement tasks have end-to-end (e2e) scripts available in the `e2e/` directory.

1. **Run recording measurements**:
   ```bash
   python auto_record.py --ts 202502020008
   ```

2. **Run replay measurements**:
   ```bash
   python auto_replay.py --ts 202502020008
   ```

3. **Analyze differences**:
   ```bash
   python infer_diff.py
   python layout_diff.py
   ```

### Distributed Measurements

The measurement system supports distributed execution across multiple machines:
- Set `SPLIT=1` environment variable

## Key Features

- **Resource Reuse**: Reuse crawled resources across pages and multiple crawls
- **Dynamic Augmentation**: Use dynamic crawls to augment subsequent static crawls
- **Fidelity Measurement**: Comprehensive measurement of page fidelity including layout trees and network requests
- **Automated Pipeline**: End-to-end automation from recording to analysis
- **Distributed Execution**: Support for running measurements across multiple machines

## Metadata & Results
Measurement results and metadata are compiled and made available on Azure Blob Storage.

[Download measurements.tar.gz](https://imc25dataset.blob.core.windows.net/dataset/measurements.tar.gz)

After downloading, extract the contents of `measurements.tar.gz` into this `measurements/` directory to obtain all necessary subdirectories and files.

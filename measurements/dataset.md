# IMC-25 Artifact: Dataset Overview

This directory contains a **sampled version** of the full dataset used in our experiments. The complete dataset exceeds 8TB in size and is not practical for direct distribution. Instead, we provide representative splits for download and analysis.

## Dataset Splits

The dataset is divided into four splits. Each split can be downloaded from the following Azure Blob Storage links:

(Links to be provided)
- **Split 1:** [Download Link](https://imc25dataset.blob.core.windows.net/dataset/static-replay-files-0.tar.gz)
- **Split 2:** [Download Link](https://imc25dataset.blob.core.windows.net/dataset/static-replay-files-1.tar.gz)
- **Split 3:** [Download Link](https://imc25dataset.blob.core.windows.net/dataset/static-replay-files-2.tar.gz)
- **Split 4:** [Download Link](https://imc25dataset.blob.core.windows.net/dataset/static-replay-files-3.tar.gz)

## Directory Structure

Each split follows this directory structure:

```
static-replay-files-<split>/
├── instrumentations/
│   ├── site_replay/
│   │   └── <page>.../
│   └── static_replay/
│       └── <page>.../
└── warcs/
    ├── site_replay/
    │   └── pagexxx.warc
    └── static_replay/
        └── pagexxx.warc
```
- The `warcs/` directory stores the raw WARC files: web archive files for each archived copy.
- The `instrumentations/` directory contains measurements collected during page loads, such as the layout tree, screenshots taken. Measurements contains both after the `onload` event, and after each triggered interaction.

- Each `site_replay` directories contain data for the **cross-sectional dataset**, which captures a wide variety of sites at a single point in time.
- Each `static_replay` directories contain data for the **longitudinal dataset**, which tracks the same set of sites across multiple points in time.

### Instrumentations

Each `<page>` directory in the instrumentations folder has the following example structure:

```
<page>/
├── metadata.json
├── record-<ts>_<idx>.json
├── record-<ts>_<idx>.jpg
├── record-<ts>_events.json
├── replay-<ts>_<idx>.json
├── replay-<ts>_<idx>.jpg
├── replay-<ts>_events.json
├── replay-static-<ts1>-<ts>_<idx>.json
├── replay-static-<ts1>-<ts>_<idx>.jpg
├── replay-static-<ts1>-<ts>_events.json
└── ...
```

- **`metadata.json`** - Contains metadata about the page measurements (URL, timestamp, etc.)
- **`record`** &  **`replay`** 
  - **`record`**: Crawl of live web page when archiving the page, 
  - **`replay`**: Replay of the archived page with pywb.
- **`idx`**: Index of interaction triggered. If no idx, it is onload.
- **`ts`**: Timestamp of the page being archived.
- **`events`**: Page's events.
- **`dom`**: Layout tree.
- **`screenshot`**: Screenshot.
- **`replay-static`**: Replay on static crawled warc files.
- **`ts1`**: Timestamp of dynamic crawled warc files to accompany with during load.
- **`ts2`**: Timestamp of static crawled warc files.

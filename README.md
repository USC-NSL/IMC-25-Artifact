# IMC-25 Artifact: Toward Better Efficiency vs. Fidelity Tradeoffs in Web Archives

This repository contains the source code, datasets, and experimental results for the IMC 2025 paper ["Toward Better Efficiency vs. Fidelity Tradeoffs in Web Archives"](https://doi.org/10.1145/3730567.3764507).

## Overview

In this paper, we make the case that a web archive does not have to make a binary choice between dynamic or static crawling. Instead, by using a browser for a carefully chosen small subset of crawls, an archive can significantly improve its ability to serve statically crawled pages with high fidelity. First, we show how to reuse crawled resources, both across pages and across multiple crawls of the same page over time. Second, by leveraging a dynamic crawl of a page, we show that subsequent static crawls of the page can be augmented to fetch resources without executing the scripts which request them.  


## Prerequisites

- Python 3.8
- Node.js 22 
- Chrome 130
  - [Chrome for testing](https://developer.chrome.com/blog/chrome-for-testing) is recommended
  -  [webrecorder](https://chromewebstore.google.com/detail/webrecorder-archivewebpag/fpeoodllldobpkbkabpblcfaogecpndd) extension need to be installed

## Installation

```bash
git clone https://github.com/[your-username]/IMC-25-Artifact.git
cd IMC-25-Artifact

# Install Python dependencies
pip install -r requirements.txt
pip install -e .

# Install Node.js dependencies
npm install
```

### Configuration Setup

After installation, you need to update the configuration file to match your environment:

Edit `warctradeoff/config.json` and update the following settings:

```json
{
    "host": "localhost:8080",
    "host_proxy": "localhost:8079", 
    "host_proxy_test": "localhost:8078",
    "host_proxy_patch": "localhost:8078",
    "collection": "static_replay",
    "pywb_env": ". /path/to/your/pywb/env/bin/activate",
    "chrome_data_dir": "/path/to/your/chrome/data/",
    "archive_dir": "/path/to/your/archive/files/"
}
```

**Note**: Make sure the directories specified in `chrome_data_dir` and `archive_dir` exist and are writable.

## Usage

Basic usage examples and command-line instructions can be found in [measurements/README.md](measurements/README.md). This includes information on recording, replaying, analyzing differences, and distributed measurement workflows. Please refer to that file for detailed usage and measurement instructions.



## Datasets
For detailed information about the available datasets, please refer to [measurements/dataset.md](measurements/dataset.md).


## Citation

If you use this code or datasets in your research, please cite our paper:

```bibtex
@inproceedings{zhu2025toward,
  title={Toward Better Efficiency vs. Fidelity Tradeoffs in Web Archives},
  author={Zhu, Jingyuan and Sun, Huanchen and Madhyastha, Harsha V},
  booktitle={Proceedings of the 2025 ACM Internet Measurement Conference (IMC)},
  year={2025}
}
```

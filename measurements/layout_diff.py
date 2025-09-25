import os
import json
import pandas as pd
import random
import requests
import sys
import glob
import time
import logging
import traceback
import re
import argparse
from urllib.parse import urlsplit, urlunsplit
from concurrent import futures
from collections import defaultdict

# sys.path.append(os.path.abspath('..'))
from warctradeoff.fidelity_check import layout_tree_patch, missing_resources
from fidex.fidelity_check import fidelity_detect
from fidex.utils import logger
from warctradeoff.config import CONFIG
from warctradeoff.utils import url_utils
# supress warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import utils
from sklearn.metrics import confusion_matrix, classification_report

# * Prefix
PREFIX = 'static_replay'
PREFIX = PREFIX if os.environ.get('PREFIX') is None else os.environ.get('PREFIX')
PREFIX_SUB = PREFIX
if not os.path.exists(f'diffs/{PREFIX_SUB}'):
    os.makedirs(f'diffs/{PREFIX_SUB}', exist_ok=True)

# * Left and Right
parser = argparse.ArgumentParser(description='Flags for the script')
parser.add_argument('--left', type=str, help='Left file prefix to compare layout tree')
parser.add_argument('--right', type=str, help='Right file prefix to compare layout tree')
parser.add_argument('operation', type=str, help='Operation to perform')
args = parser.parse_args()
LEFT_ARG = args.left
RIGHT_ARG = args.right
operation = args.operation
assert LEFT_ARG is not None, "Left prefix must be provided"
assert RIGHT_ARG is not None, "Right prefix must be provided"
assert operation in ['fidelity', 'missing_scripts', 'merge', 'ground_truth'], f"Invalid operation {operation}"
idx = utils.get_idx()
LEFT = utils.closest_ts(LEFT_ARG, idx, PREFIX)
RIGHT = utils.closest_ts(RIGHT_ARG, idx, PREFIX)
SUFFIX = "" if idx < 0 else f"_{idx}"

# Get the timestamp for locating the directory
LEFT_UNI = utils.closest_ts_uniform(LEFT_ARG, PREFIX)
RIGHT_UNI = utils.closest_ts_uniform(RIGHT_ARG, PREFIX)
DIR = f'diffs/{PREFIX_SUB}/{LEFT_UNI}_{RIGHT_UNI}'
if not os.path.exists(DIR):
    os.makedirs(DIR, exist_ok=True)

counter = 0
timeout = 10 * 60
writes_dir = f'{CONFIG.archive_dir}/writes/{PREFIX}'
warc_dir = f'{CONFIG.archive_dir}/warcs/{PREFIX}'
EXCLUDE_DIRS = {} # Used for avoiding long running directories


def fidelity_issue_wrapper(idx, url, dirr, left_prefix='live', right_prefix='archive', screenshot=False, more_errs=False, html_text=False, meaningful=True):
    """Check if all the data is available and then run the fidelity check"""
    logging.info(f"Processing {idx} {dirr}")
    if not os.path.exists(f'{dirr}/{left_prefix}_done'):
        return None
    if not os.path.exists(f'{dirr}/{right_prefix}_done'):
        return None
    
    try:
        return fidelity_detect.fidelity_issue_all(dirr, left_prefix=left_prefix, 
                                                        right_prefix=right_prefix,
                                                        screenshot=screenshot,
                                                        more_errs=more_errs,
                                                        html_text=html_text, 
                                                        meaningful=meaningful,
                                                        need_exist=False)
    except Exception as e:
        logging.error(f"Error in {idx} {dirr}: {e}")
        logging.error(traceback.format_exc())
        return None

def process_fidelity():
    global counter
    dirs = os.listdir(writes_dir)
    random.shuffle(dirs)
    num_workers = 31

    def list_len(l):
        total = 0
        for ll in l:
            if isinstance(ll, list):
                total += len(ll)
        return total

    print("Available dirs:", len(dirs))
    hostname_url = {}
    results = []
    with futures.ProcessPoolExecutor(num_workers) as executor:
        rs = []
        last_ts = time.time()
        for d in dirs:
            metadata = json.load(open(f'{writes_dir}/{d}/metadata.json'))
            prefix, ts = LEFT.rsplit('-', 1)
            if metadata.get(prefix, {}).get(ts) is None:
                continue
            url = metadata[prefix][ts]['url']
            hostname_url[d] = url
            rs.append(executor.submit(fidelity_issue_wrapper, counter, url, f'{writes_dir}/{d}', LEFT, RIGHT, True, False, False, True))
            counter += 1
        while len(rs):
            try:
                for finished in futures.as_completed(rs, timeout=timeout):
                    logging.info(f"Processed {len(results)}")
                    r = finished.result()
                    rs.remove(finished)
                    last_ts = time.time()
                    if r is None:
                        continue
                    r.info['hostname'] = r.info['hostname'].split('/')[-1]
                    r.info['url'] = hostname_url.get(r.info['hostname'])
                    r.info['live_unique'] = list_len(r.live_unique)
                    r.info['archive_unique'] = list_len(r.archive_unique)
                    results.append(r.info)
                    if len(results) % 2 == 0:
                        json.dump(results, open(f'{DIR}/layout_diff{SUFFIX}.json', 'w+'), indent=2)
            except Exception as e:
                logging.error(f"Exception: {e}")
                if time.time() - last_ts > timeout:
                    logging.error(f"Timeout {time.time() - last_ts}")
                    break 
    json.dump(results, open(f'{DIR}/layout_diff{SUFFIX}.json', 'w+'), indent=2)


def missing_scripts():
    dirs = os.listdir(writes_dir)
    results = []
    for i, d in enumerate(dirs):
        print(i, d, flush=True)
        ff_scripts = missing_resources.missing_scripts(writes_dir, d, LEFT, RIGHT)
        if ff_scripts:
            results.append(ff_scripts)
        if i % 5 == 0:
            json.dump(results, open(f'{DIR}/missing_scripts{SUFFIX}.json', 'w+'), indent=2)
    json.dump(results, open(f'{DIR}/missing_scripts{SUFFIX}.json', 'w+'), indent=2)

def missing_scripts_xhr_content():
    """Beyond just check missing fetched scripts. Also checks for if XHR content is different between crawls"""
    dirs = os.listdir(writes_dir)
    results = []
    def get_ts(ts):
        ts_split = ts.split('-')
        tss = []
        for t in ts_split:
            if len(t) >= 12 and t.isdigit():
                tss.append(t)
        return tss
    left_ts = get_ts(LEFT)[-1]
    right_ts = get_ts(RIGHT)[0]
    print(left_ts, right_ts)

    for i, d in enumerate(dirs):
        print(i, d, flush=True)
        right_ff_scripts = missing_resources.missing_updated_scripts(writes_dir, warc_dir, d, LEFT, RIGHT, left_ts, right_ts)
        if right_ff_scripts:
            results.append(right_ff_scripts)
        if i % 5 == 0:
            json.dump(results, open(f'{DIR}/missing_scripts{SUFFIX}.json', 'w+'), indent=2)
    json.dump(results, open(f'{DIR}/missing_scripts{SUFFIX}.json', 'w+'), indent=2)


def merge():
    diffed = {d['hostname']:d  for d in json.load(open(f'{DIR}/layout_diff{SUFFIX}.json')) if d['diff']}
    missing_script = {d['hostname']: d for d in json.load(open(f'{DIR}/missing_scripts{SUFFIX}.json'))}
    print("Number of diff=True:", len(diffed))
    print("Number of missing scripts:", len(missing_script)) 
    print("Number of intersection:", len(set(diffed) & set(missing_script)))
    merged = []
    for hostname in diffed:
        if hostname not in missing_script:
            continue
        merged.append({
            'hostname': hostname,
            'diff': diffed[hostname],
            'missing_script': missing_script[hostname],
        })
    json.dump(merged, open(f'{DIR}/diff{SUFFIX}.json', 'w'), indent=2)


def ground_truth_eval():
    layout_diff_gt = {}
    for i in range(4):
        layout_diff_gt_part = json.load(open(f'diffs/{PREFIX}/{LEFT}_{RIGHT}/layout_diff_{i}.json'))
        layout_diff_gt_part = {d['hostname']: d['diff'] for d in layout_diff_gt_part}
        layout_diff_gt.update(layout_diff_gt_part)
    layout_diff_test = {}
    screenshot_diff_test = {}
    for i in range(4):
        layout_diff_test_part = json.load(open(f'diffs/{PREFIX}/{LEFT}_{RIGHT}_layout/layout_diff_{i}.json'))
        screenshot_diff_test_part = {d['hostname']: d['screenshot_diff'] for d in layout_diff_test_part}
        screenshot_diff_test.update(screenshot_diff_test_part)
        layout_diff_test_part = {d['hostname']: d['diff'] for d in layout_diff_test_part}
        layout_diff_test.update(layout_diff_test_part)
    common_hosts = set(layout_diff_gt) & set(layout_diff_test)
    layout_diff_gt = {h: layout_diff_gt[h] for h in common_hosts}
    layout_diff_test = {h: layout_diff_test[h] for h in common_hosts}
    # Flatten the ground truth and test values into binary lists
    gt_values = [1 if layout_diff_gt[h] else 0 for h in common_hosts]
    test_values = [1 if layout_diff_test[h] else 0 for h in common_hosts]
    screenshot_values = [1 if screenshot_diff_test[h] else 0 for h in common_hosts]

    # Generate confusion matrix
    cm = confusion_matrix(gt_values, test_values)
    print("Confusion Matrix:")
    print(cm)
    # Optionally, print a classification report for more details
    report = classification_report(gt_values, test_values, target_names=["No Diff", "Diff"])
    print("\nClassification Report:")
    print(report)

    cm2 = confusion_matrix(gt_values, screenshot_values)
    print("Screenshot Confusion Matrix:")
    print(cm2)
    report2 = classification_report(gt_values, screenshot_values, target_names=["No Diff", "Diff"])
    print("\nScreenshot Classification Report:")
    print(report2)

if __name__ == "__main__":
    if operation == 'fidelity':
        process_fidelity()
    elif operation == 'missing_scripts':
        missing_scripts()
    elif operation == 'merge':
        merge()
    elif operation == 'ground_truth':
        ground_truth_eval()
    else:
        assert False, f"Invalid operation {operation}"
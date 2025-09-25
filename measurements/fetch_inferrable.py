import os
import json
import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

# sys.path.append(os.path.abspath('..'))
from warctradeoff.inference import source_trace
from warctradeoff.config import CONFIG
from warctradeoff.utils import url_utils
# supress warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import utils

os.environ['SPLIT'] = '1'

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
args = parser.parse_args()
LEFT_ARG = args.left
RIGHT_ARG = args.right
# LEFT_ARG = 'replay-202503230005'
# RIGHT_ARG = 'replay-static-202501200202-exxhr1-X-202503230005'


assert LEFT_ARG is not None, "Left prefix must be provided"
assert RIGHT_ARG is not None, "Right prefix must be provided"
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

warc_dir = f'{CONFIG.archive_dir}/warcs/{PREFIX}'
LEFT_TSS = utils.get_tss(LEFT, idx, PREFIX)
RIGHT_TSS = utils.get_tss(RIGHT, idx, PREFIX)
print(f"RIGHT_TSS: {RIGHT_TSS}")

def get_critical_ff_xhr():
    diffs = json.load(open(f'{DIR}/diff{SUFFIX}.json', 'r'))
    ff_xhrs = []
    for diff in diffs:
        hostname = diff['hostname']
        # if hostname != 'www.google.sc_9180725947':
        #     continue
        failed_fetches = diff['missing_script']['failFetchScripts']
        for ff in failed_fetches:
            if ff['mime'] not in ['Fetch', 'XHR', 'Script']:
                continue
            if ff['url'] == 'about:blank':
                continue
            ff_xhrs.append({
                'hostname': hostname,
                'url': ff['url'],
                'left_ts': RIGHT_TSS[0],
                'right_ts': RIGHT_TSS[-1]
            })
    return ff_xhrs


def check_inferrable_worker(ff, i, total):
    print(f"Processing [{i+1}/{total}]: {ff['url']}")
    url = ff['url']
    hostname = ff['hostname']
    right_url_src_tracer = source_trace.URLSrcTracer(url, hostname, ff['right_ts'])
    most_similar_urls = right_url_src_tracer.most_similar_urls(hostname, ff['left_ts'])
    if len(most_similar_urls) == 0:
        return {
            'hostname': hostname,
            'url': url,
            'inferrable': False,
            'most_similar_url': most_similar_urls
        }
        
    most_similar_url = most_similar_urls[0][1]
    left_url_src_tracer = source_trace.URLSrcTracer(most_similar_url, hostname, ff['left_ts'])
    inferrable, matches = right_url_src_tracer.inferrable(left_url_src_tracer)
    return {
        'hostname': hostname,
        'url': url,
        'inferrable': inferrable,
        'most_similar_url': most_similar_urls,
        'matches': matches
    }


def check_inferrable(failed_fetches):
    results = []
    num_infer = 0
    load_able_infer = defaultdict(lambda: True)
    with ProcessPoolExecutor(max_workers=31) as executor:
        rs = []
        for i, ff in enumerate(failed_fetches):
            rs.append(executor.submit(check_inferrable_worker, ff, i, len(failed_fetches)))
        for i, r in enumerate(rs):
            r = r.result()
            results.append(r)
            inferrable = r['inferrable']
            hostname = r['hostname']
            num_infer += inferrable
            load_able_infer[hostname] &= inferrable
            if i % 500 == 0:
                json.dump(results, open(f'{DIR}/inferrable{SUFFIX}.json', 'w'), indent=4)
    total = len(results)
    print(f"Total: {total}, Inferrable: {num_infer}")
    print(f"Total loads: {len(load_able_infer)}, Inferrable loads: {len([l for l, v in load_able_infer.items() if v])} ")
    json.dump(results, open(f'{DIR}/inferrable{SUFFIX}.json', 'w'), indent=4)
    

if __name__ == "__main__":
    ff_xhrs = get_critical_ff_xhr()
    check_inferrable(ff_xhrs)
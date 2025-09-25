import json
import sys
import os
import sys
import argparse

from warctradeoff.crawl import autorun
from warctradeoff.config import CONFIG
import utils

parser = argparse.ArgumentParser(description='Flags for the script')
parser.add_argument('--ts', type=str, help='Timestamp argument')
parser.add_argument('--dynamic_ts', type=str, help='Suffix argument')

args = parser.parse_args()
timestamp = '202502020008'
timestamp = timestamp if args.ts is None else args.ts
dynamic_ts = args.dynamic_ts


arguments = ['-s', '--scroll', '-t', '-w', '-e', '--headless', '-i']

HOME = os.path.expanduser("~")
chrome_data_dir = f'/x/jingyz/chrome_data'

PREFIX = 'static_replay'
PREFIX = PREFIX if os.environ.get('PREFIX') is None else os.environ.get('PREFIX')
if os.environ.get('SEPARATE_COLLECTION') is not None:
    CONFIG.separate_collection = os.environ['SEPARATE_COLLECTION']
idx = utils.get_idx()
timestamp = utils.closest_ts(timestamp, idx, PREFIX)
dynamic_ts = utils.closest_ts(dynamic_ts, idx, PREFIX)

prefix = 'replay-patch' if dynamic_ts is None else f'replay-patch-{dynamic_ts}'
pw_archive = f'{PREFIX}_patch' if CONFIG.separate_collection is None else CONFIG.separate_collection


# * Get URLs
if idx < 0:
    patch_info = json.load(open(f'metadata/{PREFIX}_patch_info.json', 'r'))
else:
    patch_info = json.load(open(f'metadata/{PREFIX}_patch_info_{idx}.json', 'r'))

urls = []
for archive_obj in patch_info['archives']:
    if isinstance(archive_obj, dict):
        archive = archive_obj['hostname']
    else:
        archive = archive_obj
    metadata = json.load(open(f'{CONFIG.archive_dir}/writes/{PREFIX}/{archive}/metadata.json', 'r'))
    url = metadata['record'][timestamp]['url']
    urls.append(url)

# urls = urls[:1]
print("Total URLs:", len(urls), flush=True)
# exit(0)

# # * Used for temp
# LEFT = 'record-nojs-0'
# RIGHT = 'replay-archive-0'
# urls = json.load(open(f'diffs/{PREFIX}_{LEFT}_{RIGHT}_diff.json'))
# urls = [u['diff']['url'] for u in urls]


# * 3
autorun.record_replay_all_urls_multi(urls, timestamp, 8,
                                    file_prefix=prefix,
                                    chrome_data_dir=chrome_data_dir,
                                    pw_archive=pw_archive,
                                    upload_write_archive=PREFIX,
                                    record_live=False,
                                    replay_archive=False,
                                    replay_archive_patch=True,
                                    replay_ts=timestamp,
                                    patch_ts=dynamic_ts,
                                    arguments=arguments,
                                    trials=1)

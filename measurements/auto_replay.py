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

args = parser.parse_args()
timestamp = '202502020008'
timestamp = timestamp if args.ts is None else args.ts


arguments = ['-s', '--scroll', '-t', '-w', '-e', '--headless', '-i']

HOME = os.path.expanduser("~")
chrome_data_dir = f'/x/jingyz/chrome_data'

PREFIX = 'static_replay'
PREFIX = PREFIX if os.environ.get('PREFIX') is None else os.environ.get('PREFIX')
if os.environ.get('SEPARATE_COLLECTION') is not None:
    CONFIG.separate_collection = os.environ['SEPARATE_COLLECTION']
idx = utils.get_idx()
timestamp = utils.closest_ts(timestamp, idx, PREFIX)

# * 1
if idx < 0:
    extract_info = json.load(open(f'metadata/{PREFIX}_extract_info.json', 'r'))
else:
    extract_info = json.load(open(f'metadata/{PREFIX}_extract_info_{idx}.json', 'r'))

urls = []
for archive in extract_info['archives']:
    if isinstance(archive, dict):
        archive = archive['hostname']
    metadata = json.load(open(f'{CONFIG.archive_dir}/writes/{PREFIX}/{archive}/metadata.json', 'r'))
    if timestamp not in metadata['record']:
        continue
    url = metadata['record'][timestamp]['url']
    urls.append(url)

urls = urls[:1]

print("Total URLs:", len(urls), flush=True)
# exit(0)

# * 3
pw_archive = PREFIX if CONFIG.separate_collection is None else CONFIG.separate_collection
autorun.record_replay_all_urls_multi(urls, timestamp, 16,
                                    file_prefix='replay',
                                    chrome_data_dir=chrome_data_dir,
                                    metadata=metadata,
                                    pw_archive=pw_archive,
                                    upload_write_archive=PREFIX,
                                    record_live=False,
                                    replay_archive=True,
                                    replay_ts=timestamp,
                                    arguments=arguments,
                                    trials=1)

import json
import sys
import os
import sys
import argparse

from warctradeoff.crawl import autorun, warcprocess
from warctradeoff.config import CONFIG
import utils

parser = argparse.ArgumentParser(description='Flags for the script')
parser.add_argument('--ts', type=str, help='Timestamp argument')
parser.add_argument('--dynamic_ts', type=str, help='Suffix argument')
parser.add_argument('--resource_match_type', type=str, help='For extract_resource_warcs, which type of resource to match')
parser.add_argument('--run_id', type=str, help='Run ID for the current run. Only used if resource_match_type is specified')
parser.add_argument('--cache', action='store_true', default=False, help='Whether a cache dynamic warc is used')
parser.add_argument('--inferrable', action='store_true', default=False, help='Whether to use inferrable information')

args = parser.parse_args()
timestamp = args.ts
dynamic_ts = args.dynamic_ts
dynamic_tss = dynamic_ts.split(',') if dynamic_ts is not None else []
resource_match_type = args.resource_match_type
if resource_match_type is not None:
    resource_match_type = warcprocess.ResourceMatchType.from_str(args.resource_match_type)
    if args.inferrable:
        resource_match_type = resource_match_type.short_str('inferrable')
    else:
        resource_match_type = resource_match_type.short_str(args.run_id)
assert timestamp is not None, 'Timestamp argument is required'

arguments = ['-s', '--scroll', '-t', '-w', '-e', '--headless', '-i']

HOME = os.path.expanduser("~")
chrome_data_dir = f'/x/jingyz/chrome_data'

PREFIX = 'static_replay'
PREFIX = PREFIX if os.environ.get('PREFIX') is None else os.environ.get('PREFIX')
if os.environ.get('SEPARATE_COLLECTION') is not None:
    CONFIG.separate_collection = os.environ['SEPARATE_COLLECTION']
idx = utils.get_idx()
timestamp = utils.closest_ts(timestamp, idx, PREFIX)
dynamic_tss = [utils.closest_ts(dynamic_ts, idx, PREFIX) for dynamic_ts in dynamic_tss]
dynamic_ts = ','.join(dynamic_tss) if dynamic_tss else None

# * 1 Prepare prefix and suffix
if dynamic_ts is None:
    prefix = 'replay-static'
else:
    if args.cache:
        prefix = f'replay-static-cache-{dynamic_ts}'
    else:
        prefix = f'replay-static-{dynamic_ts}'
if resource_match_type is None:
    suffix = timestamp
else:
    suffix = f'{resource_match_type}-{timestamp}'
pw_archive = f'{PREFIX}_static' if CONFIG.separate_collection is None else CONFIG.separate_collection
print("Prefix:", prefix, 'Suffix:', suffix, flush=True)


# * 2 Get URLs
if idx < 0:
    extract_info = json.load(open(f'metadata/{PREFIX}_extract_info.json', 'r'))
else:
    extract_info = json.load(open(f'metadata/{PREFIX}_extract_info_{idx}.json', 'r'))

urls = []
for archive_obj in extract_info['archives']:
    if isinstance(archive_obj, dict):
        archive = archive_obj['hostname']
    else:
        archive = archive_obj
    metadata = json.load(open(f'{CONFIG.archive_dir}/writes/{PREFIX}/{archive}/metadata.json', 'r'))
    url = metadata['record'][timestamp]['url']
    urls.append(url)
    if archive_obj.get('dynamic_warc_info'):
        json.dump(archive_obj['dynamic_warc_info'], open(f'{CONFIG.archive_dir}/writes/{PREFIX}/{archive}/{prefix}-{suffix}_dynamic_warc_info.json', 'w'), indent=2)

# urls = urls[:1]
print("Total URLs:", len(urls), flush=True)
# exit(0)

# * 4 Run the replay
autorun.record_replay_all_urls_multi(urls, suffix, 16,
                                    file_prefix=prefix,
                                    chrome_data_dir=chrome_data_dir,
                                    metadata=metadata,
                                    pw_archive=pw_archive,
                                    upload_write_archive=PREFIX,
                                    record_live=False,
                                    replay_archive=True,
                                    replay_ts=timestamp,
                                    arguments=arguments,
                                    trials=1)

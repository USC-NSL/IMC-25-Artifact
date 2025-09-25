"""
To only upload dynamic warcs, specify static_ts as None
"""

import argparse
import os
import glob
import json
import re
from datetime import datetime
from subprocess import call

from warctradeoff.crawl import warcprocess
from warctradeoff.config import CONFIG
from warctradeoff.utils import logger, upload
import utils

parser = argparse.ArgumentParser(description='Flags for the script')
parser.add_argument('--static_ts', type=str, help='Timestamp for dynamic warcs to extract static warcs from')
parser.add_argument('--bypass_static', action='store_true', help='If true, static warcs are not extracted')
parser.add_argument('--bypass_replay', action='store_true', help='If true, only select archives that has been replayed')
parser.add_argument('--static_prefix', type=str, help='Prefix for static warcs to extract from dynamic warcs')

parser.add_argument('--dynamic_ts', type=str, help='Timestamp to upload dynamic warcs')
parser.add_argument('--dynamic_other_url', type=int, help='Number of other URLs to extract from dynamic warcs')
parser.add_argument('--dynamic_prefix', type=str, help='Prefix for dynamic warcs to extract static warcs from')
parser.add_argument('--cache_static_ts', type=str, help='Timestamp for static_ts that is used for valid cache extraction')
parser.add_argument('--select_extract_info', type=str, help='JSON File of extract info containing the list of archives to select')
parser.add_argument('--resource_match_type', type=str, help='For extract_resource_warcs, which type of resource to match')
parser.add_argument('--num_throw_resources', type=int, help='Number of resources to throw away. Only used if resource_match_type is specified')
parser.add_argument('--run_id', type=int, help='Run ID for the current run. Only used if resource_match_type/dynamic_other_url is specified')
parser.add_argument('--inferrable_dir', type=str, help='Directory to load URL inferrable information')
parser.add_argument('--failed_fetch_dir', type=str, help='Directory to load URL failed fetch information')
parser.add_argument('--collection', type=str, help='Collection name')
args = parser.parse_args()

PREFIX = 'static_replay'
PREFIX = PREFIX if os.environ.get('PREFIX') is None else os.environ.get('PREFIX')
COLLECTION = args.collection if args.collection is not None else PREFIX
idx = utils.get_idx()
SUFFIX = '' if idx < 0 else f'_{idx}'

# * Dynamic ts extraction flags
dynamic_ts = None if args.dynamic_ts is None else args.dynamic_ts
dynamic_tss = dynamic_ts.split(',') if dynamic_ts is not None else [None]
cache_static_ts = None if args.cache_static_ts is None else args.cache_static_ts
dynamic_other_url = args.dynamic_other_url
dynamic_prefix = args.dynamic_prefix

# * Static ts extraction flags
static_ts = None if args.static_ts is None else args.static_ts
bypass_static = args.bypass_static
bypass_replay = args.bypass_replay
static_prefix = args.static_prefix

selected_archives = None
if args.select_extract_info is not None:
    select_extract_info = json.load(open(f'{args.select_extract_info}{SUFFIX}.json', 'r'))
    call(f'cp {args.select_extract_info}{SUFFIX}.json {args.select_extract_info}_selected{SUFFIX}.json', shell=True)
    selected_archives = [o['hostname'] for o in select_extract_info['archives']]
resource_match_type = warcprocess.ResourceMatchType.from_str(args.resource_match_type) if args.resource_match_type is not None else None
num_throw_resources = args.num_throw_resources if args.num_throw_resources is not None else float('Inf')
run_id = int(args.run_id) if args.run_id is not None else None
inferrable_dir = args.inferrable_dir
failed_fetch_dir = args.failed_fetch_dir

idx = utils.get_idx()
SUFFIX = '' if idx < 0 else f'_{idx}'
inferrable_file = f'{inferrable_dir}/inferrable{SUFFIX}.json' if inferrable_dir is not None else None
failed_fetch_file = f'{failed_fetch_dir}/diff{SUFFIX}.json' if failed_fetch_dir is not None else None
if os.environ.get('SEPARATE_COLLECTION') is not None:
    CONFIG.separate_collection = os.environ['SEPARATE_COLLECTION']
    call(f'rm -rf {CONFIG.archive_dir}/collections/{CONFIG.separate_collection}_*', shell=True)
    COLLECTION = CONFIG.separate_collection

# * 1 Find the closest timestamp within certain gap
static_ts = utils.closest_ts(static_ts, idx, PREFIX)
dynamic_tss = [utils.closest_ts(dts, idx, PREFIX) for dts in dynamic_tss]
cache_static_ts = utils.closest_ts(cache_static_ts, idx, PREFIX)

NUM_WORKERS = 32
# * 2 Extract static warcs from dynamic warcs
static_extracted = {}
if static_ts:
    if resource_match_type:
        if inferrable_dir:
            static_extracted = warcprocess.extract_inferrable_warcs(col=PREFIX, file_suffix=static_ts, resource_match_type=resource_match_type,
                                                                    inferrable_file=inferrable_file, file_prefix=static_prefix, num_workers=NUM_WORKERS)
        else:
            static_extracted = warcprocess.extract_resource_warcs(col=PREFIX, file_suffix=static_ts, resource_match_type=resource_match_type,
                                                              num_throw_resources=num_throw_resources, run_id=run_id, 
                                                              failed_fetch_file=failed_fetch_file, num_workers=NUM_WORKERS)
        static_extracted = {s[0]: s[1] for s in static_extracted}
    elif bypass_static:
        static_extracted = warcprocess.list_static_warcs(col=PREFIX, file_suffix=static_ts, bypass_replay=bypass_replay)
        static_extracted = {s[0]: s[1] for s in static_extracted}
    else:
        static_extracted = warcprocess.extract_static_warcs(col=PREFIX, file_suffix=static_ts, file_prefix=static_prefix, num_workers=NUM_WORKERS)
        static_extracted = {s[0]: s[1] for s in static_extracted}
else:
    print("No static ts specified, skipping extraction", flush=True)

# * 3 Extract dynamic warcs (either original or processed)
dynamic_extracted_all = {}
for dynamic_ts in dynamic_tss:
    if dynamic_ts is None:
        dynamic_extracted = static_extracted
        dynamic_extracted = {d: None for d in dynamic_extracted}
    elif dynamic_other_url:
        dynamic_extracted = warcprocess.extract_dynamic_other_url_warcs(col=PREFIX, file_suffix=dynamic_ts, 
                                                                        static_extracted=static_extracted, file_prefix=dynamic_prefix, 
                                                                        num_others=dynamic_other_url, cache_static_ts=cache_static_ts, num_workers=NUM_WORKERS)
        dynamic_extracted = {d[0]: d[1] for d in dynamic_extracted}
    elif cache_static_ts:
        dynamic_extracted = warcprocess.extract_valid_cached_warcs(col=PREFIX, file_suffix=dynamic_ts, static_ts=cache_static_ts, 
                                                                    num_workers=NUM_WORKERS)
        dynamic_extracted = {d: None for d in dynamic_extracted}
    else:
        dynamic_extracted = warcprocess.extract_dynamic_warcs(col=PREFIX, file_suffix=dynamic_ts, selected_archives=selected_archives, num_workers=NUM_WORKERS)
        dynamic_extracted = {d: None for d in dynamic_extracted}
    if len(dynamic_extracted_all) == 0:
        # First time initializing
        dynamic_extracted_all = {d: None for d in dynamic_extracted}
    dynamic_extracted_all.update(dynamic_extracted)  # Union of all dynamic warcs extracted

# * 4  Calculate intersection between dynamic nad static warcs
common, warc_paths = [], {}
for archive_name, archive_info in dynamic_extracted_all.items():
    warcs = []
    for dynamic_ts in dynamic_tss:
        if dynamic_ts is None:
            continue
        elif dynamic_other_url:
            cache_adapt = "" if cache_static_ts is None else f'.{cache_static_ts}.cache'
            for an in archive_info:
                warcs.append(f'{CONFIG.archive_dir}/warcs/{PREFIX}/{an}_{dynamic_ts}{cache_adapt}.warc')
        elif cache_static_ts:
            warc = f'{CONFIG.archive_dir}/warcs/{PREFIX}/{archive_name}_{dynamic_ts}.{cache_static_ts}.cache.warc'
            warcs.append(warc)
        else:
            warc = f'{CONFIG.archive_dir}/warcs/{PREFIX}/{archive_name}_{dynamic_ts}.warc'
            warcs.append(warc)
    if resource_match_type:
        if inferrable_dir:
            static_warc = f'{CONFIG.archive_dir}/warcs/{PREFIX}/{archive_name}_{static_ts}.{resource_match_type.short_str("inferrable")}.warc'
        else:    
            static_warc = f'{CONFIG.archive_dir}/warcs/{PREFIX}/{archive_name}_{static_ts}.{resource_match_type.short_str(run_id)}.warc'
    else:
        static_warc = f'{CONFIG.archive_dir}/warcs/{PREFIX}/{archive_name}_{static_ts}.static.warc'
    if static_ts:
        if archive_name not in static_extracted:
            continue
        if not os.path.exists(static_warc):
            continue
        warcs.append(static_warc)
    obj = {'hostname': archive_name, 
           'static_warc_info': static_extracted.get(archive_name, None), 
           'dynamic_warc_info': dynamic_extracted_all.get(archive_name, None)}  
    common.append(obj)
    warc_paths[archive_name] = warcs
print("Common warcs:", len(common), flush=True)

# * 5 Add warcs to pywb
result = {
    'dynamic_ts': dynamic_tss,
    'static_ts': static_ts,
    'archives': common,
}
if idx < 0:
    json.dump(result, open(f'metadata/{PREFIX}_extract_info.json', 'w+'), indent=2)
else:
    json.dump(result, open(f'metadata/{PREFIX}_extract_info_{idx}.json', 'w+'), indent=2)

# May need to tweak as ssh version later
client = upload.LocalUploadManager()
separate_collection = CONFIG.separate_collection is not None
finished = client.upload_warcs_to_archive(warc_paths, col_name=COLLECTION, 
                                          lock=(not separate_collection),
                                          separate_collection=separate_collection)
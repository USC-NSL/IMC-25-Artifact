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

from warctradeoff.patch import patch
from warctradeoff.config import CONFIG
from warctradeoff.utils import logger, upload
import utils

parser = argparse.ArgumentParser(description='Flags for the script')
parser.add_argument('--static_ts', type=str, help='Timestamp for static warcs patch')
parser.add_argument('--dynamic_ts', type=str, help='Timestamp of dynamic crawl to refer the patch')
parser.add_argument('--collection', type=str, help='Collection name to upload patched warcs on')
parser.add_argument('--separate_collection', action='store_true', help='Use separate collection for each URL load')
args = parser.parse_args()

PREFIX = 'static_replay'
PREFIX = PREFIX if os.environ.get('PREFIX') is None else os.environ.get('PREFIX')
COLLECTION = args.collection if args.collection is not None else PREFIX
CONFIG.separate_collection = args.separate_collection if args.separate_collection is not None else False


dynamic_ts = '202501200202'
static_ts = '202502020008'
dynamic_ts = dynamic_ts if args.dynamic_ts is None else args.dynamic_ts
static_ts = static_ts if args.static_ts is None else args.static_ts
idx = utils.get_idx()

static_ts = utils.closest_ts(static_ts, idx, PREFIX)
dynamic_ts = utils.closest_ts(dynamic_ts, idx, PREFIX)

if os.environ.get('SEPARATE_COLLECTION') is not None:
    CONFIG.separate_collection = os.environ['SEPARATE_COLLECTION']
    call(f'rm -rf {CONFIG.archive_dir}/collections/{CONFIG.separate_collection}_*', shell=True)
    COLLECTION = CONFIG.separate_collection

# * Extract static warcs from dynamic warcs
call(f'rm {CONFIG.archive_dir}/warcs/{PREFIX}/*_{static_ts}.static.patched.warc', shell=True)
patched = patch.patch_warcs(col=PREFIX, 
                            dynamic_suffix=dynamic_ts, 
                            static_suffix=static_ts, 
                            num_workers=31)
patched = set(patched)

# * 3 Add warcs to pywb, calculate intersection between dynamic nad static warcs
common, warc_paths = [], {}
for warc in glob.glob(f'{CONFIG.archive_dir}/warcs/{PREFIX}/*_{dynamic_ts}.warc'):
    archive_name = re.match(f'{CONFIG.archive_dir}/warcs/{PREFIX}/(.*)_{dynamic_ts}.warc', warc).group(1)
    warcs = [warc]
    static_patched_warc = f'{CONFIG.archive_dir}/warcs/{PREFIX}/{archive_name}_{static_ts}.static.patched.warc'
    if archive_name not in patched:
        continue
    if not os.path.exists(static_patched_warc):
        continue
    obj = {'hostname': archive_name,
           'patch_warc_info': static_patched_warc,
           'dynamic_warc_info': warc}
    common.append(obj)
    warcs.append(static_patched_warc)
    warc_paths[archive_name] = warcs

result = {
    'dynamic_ts': dynamic_ts,
    'static_ts': static_ts,
    'archives': common,
}
if idx < 0:
    json.dump(result, open(f'metadata/{PREFIX}_patch_info.json', 'w+'), indent=2)
else:
    json.dump(result, open(f'metadata/{PREFIX}_patch_info_{idx}.json', 'w+'), indent=2)


# May need to tweak as ssh version later
client = upload.LocalUploadManager()
separate_collection = CONFIG.separate_collection is not None
client.upload_warcs_to_archive(warc_paths, col_name=COLLECTION,
                               lock=(not separate_collection),
                               separate_collection=separate_collection)
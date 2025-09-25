#!/usr/bin/env python3
import json
import os
import sys
import socket

from subprocess import call

sys.path.append('../')
import utils
from warctradeoff.crawl import warcprocess
from warctradeoff.config import CONFIG

hostname = socket.gethostname()
os.environ['SPLIT']='1'
os.environ['PREFIX']='static_replay'
env = os.environ.copy()
env['SEPARATE_COLLECTION']='replay_static'

collection='replay_static'

dynamicTS='202501200202'
staticTS='202503230005'
resourceMatchType='exclude_xhr'
num_throw_resources=1

idx = utils.get_idx()
diff_dir = f'diffs/static_replay/replay-{staticTS}_replay-static-{dynamicTS}-{staticTS}'
write_dir = f'{CONFIG.archive_dir}/writes/{os.environ["PREFIX"]}/'

for run_id in range(0, 5):
    cmd = (f'python3 extract_upload.py  --collection={collection} '
        f'--dynamic_ts={dynamicTS} --static_ts={staticTS} '
        f'--resource_match_type={resourceMatchType} '
        f'--num_throw_resources={num_throw_resources} '
        f'--failed_fetch_dir={diff_dir} '
        f'--run_id={run_id}')
    call(cmd, shell=True, cwd='../', env=env)

    # * Copy extract_info since it could be override in the future
    extract_info = json.load(open(f'../metadata/{os.environ["PREFIX"]}_extract_info_{idx}.json', 'r'))
    strip_resources = {o['hostname']: o['static_warc_info'] for o in extract_info['archives']}
    short_str = warcprocess.ResourceMatchType.from_str(resourceMatchType).short_str(run_id)
    dts, sts = utils.closest_ts(dynamicTS, idx, os.environ['PREFIX']), utils.closest_ts(staticTS, idx, os.environ['PREFIX'])
    for hostname, exclude_urls in strip_resources.items():
        json.dump(exclude_urls, open(f'{write_dir}/{hostname}/replay-static-{dts}-{short_str}-{sts}_excludeURLs.json', 'w+'), indent=2)
    json.dump(strip_resources, open(f'../extract_info/{os.environ["PREFIX"]}_extract_info_{short_str}_{idx}_runid-{run_id}.json', 'w'), indent=2)

    # * Run replay
    cmd = (f'python3 auto_replay_static.py --ts={staticTS} '
        f'--dynamic_ts={dynamicTS} '
        f'--resource_match_type={resourceMatchType} '
        f'--run_id={run_id} ')
    call(f'{cmd} 2>&1 | tee logs/auto_replay_static_{hostname}.log', shell=True, cwd='../', env=env)

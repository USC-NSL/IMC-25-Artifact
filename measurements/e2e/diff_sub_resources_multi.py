#!/usr/bin/env python3
import json
import os
import sys
import socket

from subprocess import call

sys.path.append('../')
import utils
from warctradeoff.config import CONFIG
from warctradeoff.crawl import warcprocess

hostname = socket.gethostname()
os.environ['PREFIX']='static_replay'
os.environ['SPLIT']='1'
env = os.environ.copy()

TIMEOUT = 60*30

num_runs = 5
resourceMatchType = 'exclude_xhr'
left='replay-202503230005'
right = 'replay-static-202501200202-exxhr-X-202503230005'
rights=[right.replace('-X-', f'-{i}-') for i in range(num_runs)]
idx = utils.get_idx()


def add_exclude_urls(objs, exclude_urls):
    for o in objs:
        o['exclude_urls'] = exclude_urls.get(o['hostname'], [])
    return objs

all_layout_diffs = []
call(f'rm -rf diffs/static_replay/{left}_{right}', shell=True, cwd='../')
call(f'mkdir -p diffs/static_replay/{left}_{right}', shell=True, cwd='../')

for i in range(num_runs):
    short_str = warcprocess.ResourceMatchType.from_str(resourceMatchType).short_str(i)
    exclude_urls = json.load(open(f'../extract_info/{os.environ["PREFIX"]}_extract_info_{short_str}_{idx}_runid-{i}.json', 'r'))
    right_i = rights[i]
    cmd = (f'python3 layout_diff.py '
        f'--left={left} '
        f'--right={right_i} ')
    call(f'{cmd} missing_scripts 2>&1 | tee logs/layout_diff_{hostname}.log', shell=True, cwd='../', env=env)
    
    missing_scripts = json.load(open(f'../diffs/static_replay/{left}_{right_i}/missing_scripts_{idx}.json', 'r'))
    missing_scripts = add_exclude_urls(missing_scripts, exclude_urls)
    json.dump(missing_scripts, open(f'../diffs/static_replay/{left}_{right_i}/missing_scripts_{idx}.json', 'w+'), indent=2)

    call(f'timeout -k 5s {TIMEOUT} {cmd} fidelity 2>&1 | tee logs/layout_diff_{hostname}.log', shell=True, cwd='../', env=env)
    layout_diffs = json.load(open(f'../diffs/static_replay/{left}_{right_i}/layout_diff_{idx}.json', 'r'))
    layout_diffs = add_exclude_urls(layout_diffs, exclude_urls)
    json.dump(layout_diffs, open(f'../diffs/static_replay/{left}_{right_i}/layout_diff_{idx}.json', 'w+'), indent=2)
    
    call(f'{cmd} merge', shell=True, cwd='../', env=env)
    diff = json.load(open(f'../diffs/static_replay/{left}_{right_i}/diff_{idx}.json', 'r'))
    all_layout_diffs += diff
    
    call(f'mv diffs/static_replay/{left}_{right_i}/missing_scripts_{idx}.json diffs/static_replay/{left}_{right}/missing_scripts_{idx}_{i}.json', shell=True, cwd='../')
    call(f'mv diffs/static_replay/{left}_{right_i}/layout_diff_{idx}.json diffs/static_replay/{left}_{right}/layout_diff_{idx}_{i}.json', shell=True, cwd='../')
    
json.dump(all_layout_diffs, open(f'../diffs/static_replay/{left}_{right}/diff_{idx}.json', 'w+'), indent=2)

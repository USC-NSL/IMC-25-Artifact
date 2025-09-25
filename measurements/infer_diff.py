import json
import os
import argparse
import pandas as pd
from collections import defaultdict

import utils
import plotly_utils
from missing_resources import missing_resources
from fidex.fidelity_check.fidelity_detect import FidelityResult
from warctradeoff.config import CONFIG
from warctradeoff.utils import diff_utils


PREFIX = 'static_replay'
PREFIX = PREFIX if os.environ.get('PREFIX') is None else os.environ.get('PREFIX')

parser = argparse.ArgumentParser(description='Flags for the script')
parser.add_argument('--ground_truth', type=str, help='Ground truth prefix to compare layout tree')
parser.add_argument('--static', type=str, help='Static prefix to compare layout tree')
parser.add_argument('--tag', type=str, help='Tag to plot')
parser.add_argument('--infer', type=str, help='Patch prefix to compare layout tree')
parser.add_argument('operation', type=str, help='Operation to perform')
args = parser.parse_args()
ground_truth = args.ground_truth
static = args.static
infer = args.infer
tag = args.tag
operation = args.operation
assert operation in ['diff', 'merge'], f"Invalid operation {operation}"

idx = utils.get_idx()
SUFFIX = "" if idx < 0 else f"_{idx}"

LEFT = f'{ground_truth}_{static}'
RIGHT = f'{ground_truth}_{infer}'

ground_truth_sub = utils.closest_ts(ground_truth, idx, PREFIX)
static_sub = utils.closest_ts(static, idx, PREFIX)
infer_sub = utils.closest_ts(infer, idx, PREFIX)
LEFT_SUB = f'{ground_truth_sub}_{static_sub}'
RIGHT_SUB = f'{ground_truth_sub}_{infer_sub}'

def has_target_fetch(diffs, layout_diffs, match_diffs):
    total_diff = {}
    for d in diffs:
        has_script = False
        candidates = ['Script', 'XHR', 'Fetch']
        # candidates = ['Script']
        for ff in diffs[d]['missing_script']['failFetchScripts']:
            if ff['mime'] in candidates:
                has_script = True
                break
        if not has_script:
            continue
        if d not in match_diffs:
            continue
        total_diff[d] = layout_diffs[d]['diff']
    return total_diff

def diff_eliminated():
    left_layout_diff = json.load(open(f'diffs/{PREFIX}/{LEFT}/layout_diff{SUFFIX}.json'))
    left_layout_diff = {d['hostname']: d for d in left_layout_diff}
    left_missing_script = json.load(open(f'diffs/{PREFIX}/{LEFT}/missing_scripts{SUFFIX}.json'))
    left_missing_script = {d['hostname']: d for d in left_missing_script}
    # # * 1. Pure diff
    left_diff = json.load(open(f'diffs/{PREFIX}/{LEFT}/diff{SUFFIX}.json'))
    left_diff = {d['hostname']: d for d in left_diff}
    left_ff_diff = left_diff.copy()
    # # * 2 Select diff
    # left_ff_diff = []
    # missing_script_kf = json.load(open(f'diffs/{PREFIX}/{LEFT}/missing_scripts_keyfilter{SUFFIX}.json'))
    # for mskf in missing_script_kf:
    #     hostname = mskf['diff']['hostname']
    #     if hostname not in left_missing_script:
    #         continue
    #     left_ff_diff.append({
    #         'hostname': hostname,
    #         'diff': mskf['diff'],
    #         'missing_script': left_missing_script[hostname]
    #     })
    # left_ff_diff = {d['hostname']: d for d in left_ff_diff}

    left_unrelated_diff = set([d for d, v in left_layout_diff.items() if v['diff']]) - set(left_ff_diff)
    right_diff = json.load(open(f'diffs/{PREFIX}/{RIGHT}/layout_diff{SUFFIX}.json'))
    right_diff = {d['hostname']: d for d in right_diff}
    total_diff = {}
    
    print("Left diff", len(left_ff_diff))
    print("Right diff", len(right_diff))
    # * Test 2
    total_diff = has_target_fetch(left_ff_diff, left_layout_diff, right_diff)
    # all_diff = has_target_fetch(left_diff, left_layout_diff, right_diff)
    # print("Kept diff", len([f for f in total_diff.values() if f])/len(all_diff))
    # exit(0)
    eliminates = {}
    unbreaks = {}
    for hostname in total_diff:
        dirr = f'{CONFIG.archive_dir}/writes/{PREFIX}/{hostname}'
        try:
            diff_eliminated = diff_utils.diff_eliminated(dirr, LEFT_SUB, RIGHT_SUB, filter_apply=True)
        except Exception as e:
            print(f"Error in diff_eliminated for {hostname}: {e}")
            continue
        # print(hostname, diff_eliminated)
        if not total_diff[hostname]:
            unbreaks[hostname] = diff_eliminated is None
        else:
            if diff_eliminated is None:
                continue   
            eliminates[hostname] = diff_eliminated
    json.dump(eliminates, open(f'diffs/{PREFIX}/{RIGHT}/diff_eliminated{SUFFIX}.json', 'w'), indent=2)
    # json.dump(unbreaks, open(f'diffs/{PREFIX}/{RIGHT}/diff_unbreak{SUFFIX}.json', 'w'), indent=2)
    eliminates_ones = [e for e in eliminates.values() if e >= 1]
    unbreak_ones = [e for e in unbreaks.values() if e >= 1]
    print("Total diff", len(eliminates), "ones", len(eliminates_ones)/len(eliminates))
    # print("Total undiff", len(unbreaks), "ones", len(unbreak_ones)/len(unbreaks))


def merge():
    def category(x):
        if x >= 1:
            return 'fixed'
        elif x > 0:
            return 'partially fixed'
        else:
            return 'no effect'

    def static_dir(DIR):
        NEW_DIR = DIR.replace('inferrable-', '')
        return NEW_DIR
    
    DIRS_MAP = {
        'replay-202501260006_replay-static-202501200202-inferrable-202501260006': ['1 week', 'Infer'],
        # 'replay-202502020008_replay-static-202501200202-inferrable-202502020008': ['2 weeks', 'Infer'],
        'replay-202502230017_replay-static-202501200202-inferrable-202502230017': ['5 weeks', 'Infer'],
        'replay-202503230005_replay-static-202501200202-inferrable-202503230005': ['10 weeks', 'Infer'],
        'replay-202505061710_replay-static-202501200202-inferrable-202505061710': ['15 weeks', 'Infer'],
    }
    rows = list(set([tag[0].split(' ')[0] for tag in DIRS_MAP.values()]))
    columns = ['Infer']
    eli = pd.DataFrame(index=rows, columns=['Base'] + columns)
    timegaps = pd.read_csv('fidelity_timegaps.csv', dtype={"timegap": str})
    timegaps = {row['timegap']: 100 - row['Past Dynamic'] for _, row in timegaps.iterrows()}
    for i, _ in eli.iterrows():
        eli.at[i, 'Base'] = timegaps[i] / 100
    for dirr, tag in DIRS_MAP.items():
        eliminates, unbreak = {}, {}
        diff = {}
        tag_0 = tag[0].split(' ')[0]
        static_dirr = static_dir(dirr)
        total = 0
        for i in range(4):
            eliminate_parts = json.load(open(f'diffs/{PREFIX}/{dirr}/diff_eliminated_{i}.json'))
            eliminates.update(eliminate_parts)
            diff_parts = json.load(open(f'diffs/{PREFIX}/{static_dirr}/diff_{i}.json'))
            diff.update({d['hostname']: d for d in diff_parts})
            total += len(json.load(open(f'diffs/{PREFIX}/{static_dirr}/layout_diff_{i}.json')))
        eliminates = list(eliminates.values())
        eliminates = [category(e) for e in eliminates if e is not None]
        fixed = eliminates.count('fixed')
        fixed_ex = fixed 
        print(f'{fixed=} {len(eliminates)=} {len(diff)=}')
        eli.at[tag_0, tag[1]] = fixed_ex / total
        eli.index.name = 'timegap'
        eli = eli.sort_values(by='timegap', key=lambda col: col.apply(int), ascending=True)
        
    eli.to_csv('infer.csv')
        

if __name__ == '__main__':
    if operation == 'diff':
        diff_eliminated()
    elif operation == 'merge':
        merge()

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
parser.add_argument('--patch', type=str, help='Patch prefix to compare layout tree')
parser.add_argument('operation', type=str, help='Operation to perform')
args = parser.parse_args()
ground_truth = args.ground_truth
static = args.static
patch = args.patch
tag = args.tag
operation = args.operation
assert operation in ['missing', 'diff', 'plot', 'merge'], f"Invalid operation {operation}"

idx = utils.get_idx()
SUFFIX = "" if idx < 0 else f"_{idx}"

LEFT = f'{ground_truth}_{static}'
RIGHT = f'{ground_truth}_{patch}'

ground_truth_sub = utils.closest_ts(ground_truth, idx, PREFIX)
static_sub = utils.closest_ts(static, idx, PREFIX)
patch_sub = utils.closest_ts(patch, idx, PREFIX)
LEFT_SUB = f'{ground_truth_sub}_{static_sub}'
RIGHT_SUB = f'{ground_truth_sub}_{patch_sub}'

def has_target_fetch(diffs, layout_diffs, match_diffs):
    total_diff = {}
    for d in diffs:
        has_script = False
        # candidates = ['Script', 'XHR', 'Fetch']
        candidates = ['Script']
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
    # * 2 Select diff
    left_ff_diff = []
    missing_script_kf = json.load(open(f'diffs/{PREFIX}/{LEFT}/missing_scripts_keyfilter{SUFFIX}.json'))
    for mskf in missing_script_kf:
        hostname = mskf['diff']['hostname']
        if hostname not in left_missing_script:
            continue
        left_ff_diff.append({
            'hostname': hostname,
            'diff': mskf['diff'],
            'missing_script': left_missing_script[hostname]
        })
    left_ff_diff = {d['hostname']: d for d in left_ff_diff}

    left_unrelated_diff = set([d for d, v in left_layout_diff.items() if v['diff']]) - set(left_ff_diff)
    right_diff = json.load(open(f'diffs/{PREFIX}/{RIGHT}/layout_diff{SUFFIX}.json'))
    right_diff = {d['hostname']: d for d in right_diff}
    total_diff = {}
    
    print("Left diff", len(left_ff_diff))
    print("Right diff", len(right_diff))
    # * Test 2
    total_diff = has_target_fetch(left_ff_diff, left_layout_diff, right_diff)
    all_diff = has_target_fetch(left_diff, left_layout_diff, right_diff)
    print("Kept diff", len([f for f in total_diff.values() if f])/len(all_diff))
    # exit(0)
    eliminates = {}
    unbreaks = {}
    for hostname in total_diff:
        dirr = f'{CONFIG.archive_dir}/writes/{PREFIX}/{hostname}'
        try:
            diff_eliminated = diff_utils.diff_eliminated(dirr, LEFT_SUB, RIGHT_SUB, filter_apply='fuzzy' not in patch)
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
    json.dump(unbreaks, open(f'diffs/{PREFIX}/{RIGHT}/diff_unbreak{SUFFIX}.json', 'w'), indent=2)
    eliminates_ones = [e for e in eliminates.values() if e >= 1]
    unbreak_ones = [e for e in unbreaks.values() if e >= 1]
    print("Total diff", len(eliminates), "ones", len(eliminates_ones)/len(eliminates))
    print("Total undiff", len(unbreaks), "ones", len(unbreak_ones)/len(unbreaks))

def plot():
    eliminates = {}
    for i in range(4):
        eliminate_parts = json.load(open(f'diffs/{PREFIX}/{RIGHT}/diff_eliminated_{i}.json'))
        eliminates.update(eliminate_parts)
    eliminates = list(eliminates.values())
    print("Total diff to plot", len(eliminates))
    df = pd.DataFrame(eliminates)
    fig = plotly_utils.plot_CDF(df, 'Frac of diff eliminated', 'CDF of diffed pages')
    fig.update_layout(width=600, height=450)
    fig.write_image(f'figures/diff_eliminated_{tag}.pdf')


def merge():
    def category(x):
        if x >= 1:
            return 'fixed'
        elif x > 0:
            return 'partially fixed'
        else:
            return 'no effect'

    def has_script(failed_fetches):
        for ff in failed_fetches['failFetchScripts']:
            if ff['mime'] in ['Script']:
                return True
        return False
    
    def static_dir(DIR):
        # replace either replay-static-fuzzy or replay-patch to replay-static
        NEW_DIR = DIR.replace('replay-static-fuzzy', 'replay-static')
        NEW_DIR = NEW_DIR.replace('replay-patch', 'replay-static')
        return NEW_DIR

    DIRS_MAP = {
        'replay-202501260006_replay-static-fuzzy-202501200202-202501260006': ['1 week', 'Fuzzy Match'],
        # 'replay-202502020008_replay-static-fuzzy-202501200202-202502020008': ['2 weeks', 'Fuzzy Match'],
        'replay-202502230017_replay-static-fuzzy-202501200202-202502230017': ['5 weeks', 'Fuzzy Match'],
        'replay-202503230005_replay-static-fuzzy-202501200202-202503230005': ['10 weeks', 'Fuzzy Match'],
        'replay-202505061710_replay-static-fuzzy-202501200202-202505061710': ['15 weeks', 'Fuzzy Match'],
        'replay-202501260006_replay-patch-202501200202-202501260006': ['1 week', 'HTML Patch'],
        # 'replay-202502020008_replay-patch-202501200202-202502020008': ['2 weeks', 'HTML Patch'],
        'replay-202502230017_replay-patch-202501200202-202502230017': ['5 weeks', 'HTML Patch'],
        'replay-202503230005_replay-patch-202501200202-202503230005': ['10 weeks', 'HTML Patch'],
        'replay-202505061710_replay-patch-202501200202-202505061710': ['15 weeks', 'HTML Patch'],
    }
    rows = list(set([tag[0].split(' ')[0] for tag in DIRS_MAP.values()]))
    columns = ['Fuzzy Match', 'HTML Patch']
    eli = pd.DataFrame(index=rows, columns=columns)
    brk = pd.DataFrame(index=rows, columns=columns)
    overall = pd.DataFrame(index=rows, columns=['Base'] + columns)
    
    timegaps = pd.read_csv('fidelity_timegaps.csv', dtype={"timegap": str})
    timegaps = {row['timegap']: 100 - row['Past Dynamic'] for _, row in timegaps.iterrows()}
    for i, _ in overall.iterrows():
        overall.at[i, 'Base'] = timegaps[i] / 100
    for dirr, tag in DIRS_MAP.items():
        print(f"Processing {dirr}")
        tag_0 = tag[0].split(' ')[0]
        eliminates, unbreak = {}, {}
        orig_diff, orig_non_diff = {}, {}
        total = 0
        static_dirr = static_dir(dirr)
        for i in range(4):
            eliminate_parts = json.load(open(f'diffs/{PREFIX}/{dirr}/diff_eliminated_{i}.json'))
            eliminates.update(eliminate_parts)
            unbreak_parts = json.load(open(f'diffs/{PREFIX}/{dirr}/diff_unbreak_{i}.json'))
            unbreak.update(unbreak_parts)
            miss_scripts_part = json.load(open(f'diffs/{PREFIX}/{static_dirr}/missing_scripts_{i}.json'))
            miss_scripts_part = {d['hostname']: has_script(d) for d in miss_scripts_part}
            # print("after missing scripts", len(miss_scripts_part))
            diff_parts = json.load(open(f'diffs/{PREFIX}/{static_dirr}/diff_{i}.json'))
            diff_parts = {d['hostname']: d for d in diff_parts}
            orig_diff.update({k: v for k, v in miss_scripts_part.items() if k in diff_parts})
            orig_non_diff.update({k: v for k, v in miss_scripts_part.items() if k not in diff_parts})
            total += len(json.load(open(f'diffs/{PREFIX}/{static_dirr}/layout_diff_{i}.json')))
        eliminates = list(eliminates.values())
        unbreak = list(unbreak.values())
        eliminates = [category(e) for e in eliminates if e is not None]
        fixed = eliminates.count('fixed') / len(eliminates) * len(orig_diff)
        breaks = unbreak.count(False) / len(unbreak) * len(orig_non_diff)
        print(f'{len(orig_diff)=} {len(orig_non_diff)=} {fixed=} {breaks=} {total=}')
        overall.at[tag_0, tag[1]] = (fixed - breaks) / total
        # sort rows in timegap
        overall.index.name = 'timegap'
        overall = overall.sort_values(by='timegap', key=lambda col: col.apply(int), ascending=True)
        #  frac = eliminates.count('fixed') / len(eliminates)
        # eli.at[tag_0, tag[1]] = frac
        # eli.index.name = 'timegap'
        # frac = unbreak.count(True) / len(unbreak)
        # brk.at[tag_0, tag[1]] = 1 - frac
        # brk.index.name = 'timegap'
    # eli.to_csv('patch_eli.csv')
    # brk.to_csv('patch_brk.csv')
    overall.to_csv('patch_overall.csv')

if __name__ == '__main__':
    if operation == 'missing':
        missing_resources.missing_resources_categories(ground_truth, static)
    if operation == 'diff':
        diff_eliminated()
    elif operation == 'plot':
        plot()
    elif operation == 'merge':
        merge()

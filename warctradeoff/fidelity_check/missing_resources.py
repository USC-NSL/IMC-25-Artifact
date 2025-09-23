
import json
import os

from warctradeoff.utils import url_utils, warc_utils


def missing_scripts(writes_dir, dirr, LEFT, RIGHT):
    if not os.path.exists(f'{writes_dir}/{dirr}/{LEFT}_fetches.json') or \
        not os.path.exists(f'{writes_dir}/{dirr}/{RIGHT}_exception_failfetch.json'):
        return
    left_fetches = json.load(open(f'{writes_dir}/{dirr}/{LEFT}_fetches.json'))
    left_urls = set(lf['url'] for lf in left_fetches)
    left_nds = set(url_utils.netloc_dir(lf['url']) for lf in left_fetches)
    right_fetches = json.load(open(f'{writes_dir}/{dirr}/{RIGHT}_exception_failfetch.json'))
    
    right_ff_scripts = {}
    for right_fetch in right_fetches:
        ff = right_fetch['failedFetches']
        for f in ff:
            # * Filter failed fetches that are not related to 404
            if f.get('blockedReason') in ['mixed-content']:
                continue
            if f['mime'] not in ['Script', 'StyleSheet', 'XHR', 'Fetch']:
                continue
            nd = url_utils.netloc_dir(f['url'])
            if f['url'] in left_urls:
                f['jscrawlMatch'] = 'exact'
                right_ff_scripts[(f['url'], f['method'])] = f
            # elif nd in left_nds:
            #     f['jscrawlMatch'] = 'netloc_dir'
            #     right_ff_scripts[(f['url'], f['method'])] = f
    if len(right_ff_scripts) == 0:
        return None
    return {
        'hostname': dirr,
        'failFetchScripts': list(right_ff_scripts.values()),
    }
    

def missing_updated_scripts(writes_dir, warc_dir, dirr, LEFT, RIGHT, left_ts, right_ts):
    if not os.path.exists(f'{writes_dir}/{dirr}/{LEFT}_fetches.json') or \
            not os.path.exists(f'{writes_dir}/{dirr}/{RIGHT}_fetches.json'):
            return
    left_fetches = json.load(open(f'{writes_dir}/{dirr}/{LEFT}_fetches.json'))
    left_urls = set(lf['url'] for lf in left_fetches)
    left_nds = set(url_utils.netloc_dir(lf['url']) for lf in left_fetches)
    right_fetches = json.load(open(f'{writes_dir}/{dirr}/{RIGHT}_fetches.json'))
    right_fail_fetches = json.load(open(f'{writes_dir}/{dirr}/{RIGHT}_exception_failfetch.json'))
    right_fail_fetches = {f['url']: f for obj in right_fail_fetches for f in obj['failedFetches']}
    
    left_content = warc_utils.read_warc_responses(f'{warc_dir}/{dirr}_{left_ts}.warc')
    right_content = warc_utils.read_warc_responses(f'{warc_dir}/{dirr}_{right_ts}.warc')
    right_ff_scripts = {}
    for right_fetch in right_fetches:
        url = right_fetch['url']
        if url in right_fail_fetches:
            f = right_fail_fetches[url]
            # * Filter failed fetches that are not related to 404
            if f.get('blockedReason') in ['mixed-content']:
                continue
            if f['mime'] not in ['Script', 'StyleSheet', 'XHR', 'Fetch']:
                continue
            if f['url'] in left_urls:
                f['jscrawlMatch'] = 'exact'
                right_ff_scripts[(f['url'], f['method'])] = f
            # elif nd in left_nds:
            #     f['jscrawlMatch'] = 'netloc_dir'
            #     right_ff_scripts[(f['url'], f['method'])] = f
        elif right_fetch['resourceType'] in ['XHR', 'Fetch']:
            url_strip = strip_url(url)
            if url_strip in left_content and url_strip in right_content:
                if len(left_content[url_strip] & right_content[url_strip]) <= 0:
                    right_ff_scripts[(url, right_fetch['method'])] = {
                        'url': url,
                        'method': right_fetch['method'],
                        'mime': right_fetch['resourceType'],
                        'jscrawlMatch': 'updated_content',
                    }
    if len(right_ff_scripts) == 0:
        return None
    return {
        'hostname': dirr,
        'failFetchScripts': list(right_ff_scripts.values()),
    }
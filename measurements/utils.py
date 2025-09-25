import os
import socket
import re
from datetime import datetime
import json

DEFAULT_TIMEGAP = 30 * 60

def get_idx():
    HOSTNAMES = ['redwings', 'pistons', 'wolverines', 'lions']
    if os.environ.get('SPLIT') is not None:
        assert os.environ.get('SPLIT') == '1'
        hostname = socket.gethostname()
        idx = HOSTNAMES.index(hostname)
        assert 0 <= idx < 4
        return idx
    else:
        return -1

def get_tss(ts, idx, PREFIX, gap=DEFAULT_TIMEGAP):
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    if ts is None:
        return None
    if idx < 0:
        metadata = json.load(open(f'{cur_dir}/metadata/{PREFIX}_metadata.json'))
    else:
        metadata = json.load(open(f'{cur_dir}/metadata/{PREFIX}_metadata_{idx}.json'))
    DELIMITERS = ['-', ',']
    pattern = f"([{re.escape(''.join(DELIMITERS))}]+)"
    ts_split = re.split(pattern, ts)
    found_ts, i = [], len(ts_split) - 1
    while i >= 0:
        if i % 2 == 1: # delimiter
            i -= 1
            continue
        ts = ts_split[i]
        if len(ts) < 8 or not ts.isdigit():
            i -= 1
            continue
        if len(ts) < 12:
            ts += '0'*(12 - len(ts))
        datetime_ts = datetime.strptime(ts, '%Y%m%d%H%M')
        for obj in metadata:
            obj['suffix'] = str(obj['suffix'])
            suffix_ts = datetime.strptime(obj['suffix'], '%Y%m%d%H%M')
            delta = abs((datetime_ts - suffix_ts).total_seconds())
            if delta <= gap:
                ts = obj['suffix']
                found_ts.insert(0, ts)
                found = True
                break
        i -= 1
        assert found, f'No timestamp found for {ts[-i]} within {gap} seconds'
    return found_ts

def closest_ts(ts, idx, PREFIX, gap=DEFAULT_TIMEGAP):
    """
    num_ts: Number of ts to extract from ts (split by '-')
    gap: in seconds
    """
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    if ts is None:
        return None
    if idx < 0:
        metadata = json.load(open(f'{cur_dir}/metadata/{PREFIX}_metadata.json'))
    else:
        metadata = json.load(open(f'{cur_dir}/metadata/{PREFIX}_metadata_{idx}.json'))
    DELIMITERS = ['-', ',']
    pattern = f"([{re.escape(''.join(DELIMITERS))}]+)"
    ts_split = re.split(pattern, ts)
    found_ts, i = 0, len(ts_split) - 1
    while i >= 0:
        if i % 2 == 1: # delimiter
            i -= 1
            continue
        ts = ts_split[i]
        if len(ts) < 8 or not ts.isdigit():
            i -= 1
            continue
        if len(ts) < 12:
            ts += '0'*(12 - len(ts))
        datetime_ts = datetime.strptime(ts, '%Y%m%d%H%M')
        found_ts += 1
        for obj in metadata:
            obj['suffix'] = str(obj['suffix'])
            suffix_ts = datetime.strptime(obj['suffix'], '%Y%m%d%H%M')
            delta = abs((datetime_ts - suffix_ts).total_seconds())
            if delta <= gap:
                ts = obj['suffix']
                ts_split[i] = ts
                found = True
                break
        i -= 1
        assert found, f'No timestamp found for {ts[-i]} within {gap} seconds'
    return ''.join(ts_split)

def closest_ts_uniform(ts, PREFIX, gap=DEFAULT_TIMEGAP):
    return closest_ts(ts, 1, PREFIX, gap=gap)
    
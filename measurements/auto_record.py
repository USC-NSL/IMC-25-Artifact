import json
import sys
import os
import sys
import argparse

sys.path += ['/vault-swift/jingyz', '..']
from warctradeoff.crawl import autorun
from warctradeoff.config import CONFIG
import utils

parser = argparse.ArgumentParser(description='Flags for the script')
parser.add_argument('--ts', type=str, help='Timestamp argument')

args = parser.parse_args()
timestamp = args.ts if args.ts is not None else int(CONFIG.ts)

print("Timestamp:", timestamp, flush=True)

arguments = ['-s', '--scroll', '-t', '-w', '-e', '--headless', '-i']

HOME = os.path.expanduser("~")
chrome_data_dir = f'/x/jingyz/chrome_data'

PREFIX = 'static_replay'
PREFIX = PREFIX if os.environ.get('PREFIX') is None else os.environ.get('PREFIX')
idx = utils.get_idx()

# * 1
if idx < 0:
    metadata = f'metadata/{PREFIX}_metadata'
    data = json.load(open(f'data/{PREFIX}_urls.json', 'r'))
else:
    metadata = f'metadata/{PREFIX}_metadata_{idx}'
    data = json.load(open(f'data/split_inputs/{PREFIX}_urls_{idx}.json', 'r'))

# * 2
urls = [d['url'] for d in data]

# urls = urls[:1]

# urls = [
#     "https://google.com",
# ]
print("Total URLs:", len(urls), flush=True)


# * 3
autorun.record_replay_all_urls_multi(urls, timestamp, 8,
                                    chrome_data_dir=chrome_data_dir,
                                    metadata=metadata,
                                    pw_archive=PREFIX,
                                    record_live=True,
                                    replay_archive=False,
                                    replay_ts=None,
                                    arguments=arguments,
                                    trials=1)

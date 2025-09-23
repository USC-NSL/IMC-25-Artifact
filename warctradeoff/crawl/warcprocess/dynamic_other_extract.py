import logging
import os
import json
import random
import glob
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

from warctradeoff.config import CONFIG
from .warc_extract import BaseWarcExtractor
from .valid_cached_warc_extract import valid_cached_warc_worker

class DynamicWarcOtherURLExtractor(BaseWarcExtractor):
    def __init__(self, archive_dir, col, archive_name, other_archive_names, file_suffix, file_prefix='record'):
        super().__init__(archive_dir, col, archive_name, file_suffix, file_prefix)
        self.other_archive_names = other_archive_names
        self.input_warcs = [f'{archive_dir}/warcs/{col}/{an}_{file_suffix}.warc' for an in other_archive_names]
        self.dirrs = [f'{archive_dir}/writes/{col}/{an}' for an in other_archive_names]

    def extract(self) -> "(str, list) | None":
        other_archive_names = []
        for i in range(len(self.other_archive_names)):
            if not os.path.exists(self.input_warcs[i]):
                logging.error("No input warc file")
                return
            if not os.path.exists(f'{self.dirrs[i]}/metadata.json'):
                logging.error("No metadata at the corresponding write directory")
                return
            metadata = json.load(open(f'{self.dirrs[i]}/metadata.json', 'r'))
            if self.file_prefix not in metadata or self.file_suffix not in metadata['record']:
                logging.error(f"No file suffix {self.file_suffix} found in metadata")
                return
            other_archive_names.append(self.other_archive_names[i])
        return self.archive_name, other_archive_names

def dynamic_warc_other_url_worker(col, archive_name, other_archive_names, file_suffix, file_prefix):
    archive_dir = CONFIG.archive_dir
    dyn_ou_extractor = DynamicWarcOtherURLExtractor(archive_dir, col, archive_name, other_archive_names, file_suffix, file_prefix)
    return dyn_ou_extractor.extract()

def valid_cached_warc_worker_adapter(col, archive_name, other_archive_names, file_suffix, static_ts):
    archive_dir = CONFIG.archive_dir
    success_other_archive_names = []
    for oan in other_archive_names:
        if os.path.exists(f'{archive_dir}/warcs/{col}/{oan}_{file_suffix}.{static_ts}.cache.warc'):
            result = oan
        else:
            result = valid_cached_warc_worker(col, oan, file_suffix, static_ts)
        if result:
            success_other_archive_names.append(result)
    return archive_name, success_other_archive_names


def extract_dynamic_other_url_warcs(col, file_suffix, static_extracted, file_prefix=None, num_others=1, cache_static_ts=None, num_workers=1) -> "list[(str, list[str])]":
    """Extract dynamic warcs from other urls but under the same site"""
    target_hostnames = defaultdict(list)
    for an in static_extracted:
        hostname = an.split('_')[0]
        target_hostnames[hostname].append(an)
    target_archive_names = {random.choice(v): k for k, v in target_hostnames.items()}

    dirrs = glob.glob(f'{CONFIG.archive_dir}/writes/{col}/*')
    hostname_dirrs_all = defaultdict(list)
    for dirr in dirrs:
        archive_name = os.path.basename(dirr)
        if archive_name in target_archive_names:
            continue
        hostname = archive_name.split('_')[0]
        hostname_dirrs_all[hostname].append(dirr)
    hostname_dirrs = {}
    for hostname, dirrs in hostname_dirrs_all.items():
        random.shuffle(dirrs)
        new_dirrs = []
        for dirr in dirrs:
            archive_name = os.path.basename(dirr)
            if not os.path.exists(f'{CONFIG.archive_dir}/warcs/{col}/{archive_name}_{file_suffix}.warc'):
                continue
            # if not os.path.exists(f'{CONFIG.archive_dir}/writes/{col}/{archive_name}/replay-{file_suffix}_done'):
            #     continue
            new_dirrs.append(dirr)
            if len(new_dirrs) >= num_others:
                break
        if len(new_dirrs) < num_others:
            continue
        hostname_dirrs[hostname] = new_dirrs[:num_others]

    success = []
    results = []
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        for archive_name in target_archive_names:
            hostname = archive_name.split('_')[0]
            if hostname not in hostname_dirrs:
                continue
            dirrs = hostname_dirrs[hostname]
            other_archive_names = [os.path.basename(dirr) for dirr in dirrs]
            if cache_static_ts is None:
                results.append(executor.submit(dynamic_warc_other_url_worker,
                                               col=col,
                                               archive_name=archive_name,
                                               other_archive_names=other_archive_names,
                                               file_suffix=file_suffix,
                                               file_prefix=file_prefix))
            else:
                results.append(executor.submit(valid_cached_warc_worker_adapter,
                                                col=col,
                                                archive_name=archive_name,
                                                other_archive_names=other_archive_names,
                                                file_suffix=file_suffix,
                                                static_ts=cache_static_ts))
        for r in results:
            try:
                res = r.result()
                if res is not None:
                    success.append(res)
            except Exception as e:
                print(f"Exception occurred: {e}", flush=True)
    return success
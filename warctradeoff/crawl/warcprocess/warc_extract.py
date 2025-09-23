import os
import glob

from warctradeoff.config import CONFIG


class BaseWarcExtractor:
    def __init__(self, archive_dir, col, archive_name, file_suffix, file_prefix=None):
        self.archive_dir = archive_dir
        self.col = col
        self.archive_name = archive_name
        self.file_suffix = file_suffix
        self.dirr = f'{archive_dir}/writes/{col}/{archive_name}'
        if file_prefix is not None:
            self.file_prefix = file_prefix
        elif os.path.exists(f'{archive_dir}/writes/{col}/{archive_name}/record-{file_suffix}_done'):
            self.file_prefix = 'record'
        else:
            self.file_prefix = 'replay'

def extract_dynamic_warcs(col, file_suffix, selected_archives=None, num_workers=1) -> list:
    """Dummy functions, just get the available warcs"""
    dirrs = glob.glob(f'{CONFIG.archive_dir}/writes/{col}/*')

    success = []
    for dirr in dirrs:
        archive_name = os.path.basename(dirr)
        if selected_archives is not None and archive_name not in selected_archives:
            continue
        if os.path.exists(f'{CONFIG.archive_dir}/warcs/{col}/{archive_name}_{file_suffix}.warc'):
            success.append(archive_name)
    return success

def list_static_warcs(col, file_suffix, bypass_replay=False) -> list:
    warcs = glob.glob(f'{CONFIG.archive_dir}/warcs/{col}/*_{file_suffix}.static.warc')
    available_hostnames = set()
    if bypass_replay:
        available_replays = glob.glob(f'{CONFIG.archive_dir}/writes/{col}/*/replay-{file_suffix}_done')
        available_hostnames = set([os.path.dirname(r).split('/')[-1] for r in available_replays])
    success = []
    for warc in warcs:
        archive_name = os.path.basename(warc)
        archive_name = archive_name.split('_')[:2]
        archive_name = '_'.join(archive_name)
        if bypass_replay and archive_name not in available_hostnames:
            continue
        success.append((archive_name, []))
    return success
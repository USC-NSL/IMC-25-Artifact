import logging
import json
import os
import glob
from urllib.parse import urlsplit, unquote
from collections import defaultdict
from warcio.archiveiterator import ArchiveIterator
from warcio.warcwriter import WARCWriter
from concurrent.futures import ProcessPoolExecutor

from .static_warc_extract import StaticWarcExtractor
from .resource_warc_extract import ResourceMatchType, ResourceTypeWARCExtractor
from warctradeoff.config import CONFIG
from warctradeoff.utils import url_utils

host_extractor = url_utils.HostExtractor()

class InferrableWARCExtractor(StaticWarcExtractor):
    def __init__(self, archive_dir, col, archive_name, file_suffix,
                 resource_match_type: ResourceMatchType, non_inferrable_urls: list,
                 file_prefix='record'):
        super().__init__(archive_dir, col, archive_name, file_suffix, file_prefix)
        self.resource_match_type = resource_match_type
        self.non_inferrable_urls = non_inferrable_urls
        self.input_warc = f'{archive_dir}/warcs/{col}/{archive_name}_{file_suffix}.warc'
        self.output_warc = f'{archive_dir}/warcs/{col}/{archive_name}_{file_suffix}.{resource_match_type.short_str("inferrable")}.warc'

    def inferrable_extract(self):
        metadata = json.load(open(f'{self.dirr}/metadata.json', 'r'))
        fetches = {f['url']: f for f in json.load(open(f'{self.dirr}/{self.file_prefix}-{self.file_suffix}_fetches.json'))}
        page_url = metadata[self.file_prefix][self.file_suffix]['url']
        static_urls = self.static_fetches(page_url)
        input_num, output_num = 0, 0
        include_urls, exclude_urls = set(), []
        with open(self.input_warc, 'rb') as iw:
            for record in ArchiveIterator(iw):
                url = record.rec_headers.get_header('WARC-Target-URI')
                if record.rec_type == 'response':
                    if not static_urls.get(url, True) \
                       and not ResourceTypeWARCExtractor.target_resource(self.resource_match_type, 
                                                                     url, page_url, record.http_headers,
                                                                     fetches.get(url)) \
                       and url in self.non_inferrable_urls:
                        exclude_urls.append(url)
                        continue
                    include_urls.add(url)
        with open(self.input_warc, 'rb') as iw, open(self.output_warc, 'wb') as fw:
            writer = WARCWriter(fw)
            for record in ArchiveIterator(iw):
                input_num += record.rec_type == 'response'
                url = record.rec_headers.get_header('WARC-Target-URI')
                if url in exclude_urls:
                    continue
                writer.write_record(record)
                output_num += record.rec_type == 'response'
        logging.info(f'InferrableWARCExtractor: Extracted {output_num} responses from {input_num} responses in {self.input_warc} to {self.output_warc}')
        return exclude_urls
    
    def extract(self) -> "(str, list) | None":
        if not os.path.exists(self.input_warc):
            logging.error("No input warc file")
            return
        if not os.path.exists(f'{self.dirr}/metadata.json'):
            logging.error("No metadata at the corresponding write directory")
            return
        metadata = json.load(open(f'{self.dirr}/metadata.json', 'r'))
        if self.file_prefix not in metadata or self.file_suffix not in metadata['record']:
            logging.error(f"No file suffix {self.file_suffix} found in metadata")
            return
        exclude_urls = self.inferrable_extract()
        return self.archive_name, exclude_urls


def inferrable_warc_worker(col, archive_name, file_suffix, resource_match_type, non_inferrable_urls, file_prefix=None):
    archive_dir = CONFIG.archive_dir
    rtw_extractor = InferrableWARCExtractor(archive_dir, col, archive_name,
                                          file_suffix, resource_match_type, non_inferrable_urls, file_prefix)
    return rtw_extractor.extract()


def extract_inferrable_warcs(col, file_suffix, resource_match_type, inferrable_file, select_archives=None, file_prefix=None, num_workers=1) -> "list[(str, list[str])]":
    """Extract warcs that only contain certain types of resources (exclude certain types of resources)"""
    dirrs = glob.glob(f'{CONFIG.archive_dir}/writes/{col}/*')
    inferrable_list = json.load(open(inferrable_file, 'r'))
    inferrable_urls = defaultdict(lambda: {True: [], False: []})
    for inferrable_obj in inferrable_list:
        hostname = inferrable_obj['hostname']
        inferrable = inferrable_obj['inferrable']
        inferrable_urls[hostname][inferrable].append(inferrable_obj['url'])
    if select_archives is None:
        select_archives = set([h for h in inferrable_urls])
    dirrs = [d for d in dirrs if os.path.basename(d) in select_archives]

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        results = []
        success = []
        for dirr in dirrs:
            archive_name = os.path.basename(dirr) 
            results.append(executor.submit(inferrable_warc_worker, 
                                           col=col, 
                                           archive_name=archive_name, 
                                           file_suffix=file_suffix,
                                           resource_match_type=resource_match_type,
                                           non_inferrable_urls=inferrable_urls[archive_name][False],
                                           file_prefix=file_prefix))
        for r in results:
            try:
                res = r.result()
                if res is not None:
                    success.append(res)
            except Exception as e:
                print(f"Exception occurred: {e}")
    return success
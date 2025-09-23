import logging
import json
import os
import re
import glob
import datetime
from enum import Enum
from urllib.parse import urlsplit, unquote
from warcio.archiveiterator import ArchiveIterator
from warcio.warcwriter import WARCWriter
from concurrent.futures import ProcessPoolExecutor

from .static_warc_extract import StaticWarcExtractor
from warctradeoff.config import CONFIG
from warctradeoff.utils import url_utils

host_extractor = url_utils.HostExtractor()

class ResourceMatchType(Enum):
    """Enum for resource match type"""
    EXCLUDE_NONE = 0
    EXCLUDE_JS = 1
    EXCLUDE_XHR = 2
    EXCLUDE_XHR_FIRST_PARTY = 3
    EXCLUDE_XHR_THIRD_PARTY = 4
    EXCLUDE_ALL = 5

    @classmethod
    def from_str(cls, type_str: str):
        """Convert string to ResourceMatchType"""
        print(f"ResourceMatchType: {type_str}")
        if 'exclude_none' in type_str:
            return cls.EXCLUDE_NONE
        elif 'exclude_js' in type_str:
            return cls.EXCLUDE_JS
        elif 'exclude_xhr_first_party' in type_str:
            return cls.EXCLUDE_XHR_FIRST_PARTY
        elif 'exclude_xhr_third_party' in type_str:
            return cls.EXCLUDE_XHR_THIRD_PARTY
        elif 'exclude_xhr' in type_str:
            return cls.EXCLUDE_XHR
        elif 'exclude_all' in type_str:
            return cls.EXCLUDE_ALL
        else:
            raise ValueError(f"Unknown resource match type: {type_str}")

    def __str__(self):
        return super().__str__().split('.')[-1].lower()
    
    def short_str(self, run_id=None):
        mapping = {
            ResourceMatchType.EXCLUDE_NONE: '',
            ResourceMatchType.EXCLUDE_JS: 'exjs',
            ResourceMatchType.EXCLUDE_XHR_FIRST_PARTY: 'exxhr1',
            ResourceMatchType.EXCLUDE_XHR_THIRD_PARTY: 'exxhr3',
            ResourceMatchType.EXCLUDE_XHR: 'exxhr',
            ResourceMatchType.EXCLUDE_ALL: ''
        }
        assert self in mapping, f"Unknown resource match type: {self}"
        if run_id is None:
            return mapping[self]
        else:
            return f'{mapping[self]}-{run_id}' if mapping[self] != '' else f'{run_id}'

class ResourceTypeWARCExtractor(StaticWarcExtractor):
    def __init__(self, archive_dir, col, archive_name, file_suffix,
                 resource_match_type: ResourceMatchType, failed_fetches=None,
                 num_throw_resources=float('inf'), run_id=None,
                 file_prefix='record'):
        super().__init__(archive_dir, col, archive_name, file_suffix, file_prefix)
        self.resource_match_type = resource_match_type
        self.failed_fetches = failed_fetches
        self.num_throw_resources = num_throw_resources
        self.run_id = run_id
        self.input_warc = f'{archive_dir}/warcs/{col}/{archive_name}_{file_suffix}.warc'
        self.output_warc = f'{archive_dir}/warcs/{col}/{archive_name}_{file_suffix}.{resource_match_type.short_str(self.run_id)}.warc'

    @staticmethod
    def target_resource(resource_match_type: ResourceMatchType,
                        url, page_url, response_headers,
                        fetch: None):
        def is_xhr(response_headers, fetch):
            xhr_keywords = ['json', 'plain']
            if fetch and fetch['resourceType'] in ['XHR', 'Fetch']:
                return True
            mime = response_headers.get('Content-Type', response_headers.get('content-type', ''))
            for keyword in xhr_keywords:
                if keyword in mime:
                    return True
            return False
        # print(resource_match_type,ResourceMatchType.EXCLUDE_JS, resource_match_type == ResourceMatchType.EXCLUDE_JS)
        if resource_match_type == ResourceMatchType.EXCLUDE_NONE:
            return True
        elif resource_match_type == ResourceMatchType.EXCLUDE_ALL:
            return False
        elif resource_match_type == ResourceMatchType.EXCLUDE_JS:
            if fetch:
                return fetch['resourceType'] not in ['Script']
            mime = response_headers.get('Content-Type', response_headers.get('content-type', ''))
            if 'javascript' in mime:
                return False
            _, ext = os.path.splitext(urlsplit(url).path)
            if ext in ['js']:
                return False
            return True
        elif resource_match_type == ResourceMatchType.EXCLUDE_XHR_FIRST_PARTY:
            if not is_xhr(response_headers, fetch):
                return True
            site = host_extractor.extract(url)
            page_site = host_extractor.extract(page_url)
            return site != page_site
        elif resource_match_type == ResourceMatchType.EXCLUDE_XHR_THIRD_PARTY:
            if not is_xhr(response_headers, fetch):
                return True
            site = host_extractor.extract(url)
            page_site = host_extractor.extract(page_url)
            return site == page_site
        elif resource_match_type == ResourceMatchType.EXCLUDE_XHR:
            return not is_xhr(response_headers, fetch)
        else:
            return True

    def resource_match_extract(self):
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
                       and (self.failed_fetches is None or url not in self.failed_fetches):
                        exclude_urls.append(url)
                        continue
                    include_urls.add(url)
        size = min(self.num_throw_resources, len(exclude_urls))
        if size == 0:
            logging.info(f'ResourceTypeWarcExtractor: No resources to exclude in {self.input_warc}')
            return []
        exclude_urls = [exclude_urls[i:i+size] for i in range(0, len(exclude_urls), size)]
        if self.run_id is None:
            exclude_urls = exclude_urls[0]
        elif self.run_id >= len(exclude_urls):
            logging.info(f'ResourceTypeWarcExtractor: run_id {self.run_id} exceeds the number of exclude urls')
            return []
        else:
            exclude_urls = exclude_urls[self.run_id]
        with open(self.input_warc, 'rb') as iw, open(self.output_warc, 'wb') as fw:
            writer = WARCWriter(fw)
            for record in ArchiveIterator(iw):
                input_num += record.rec_type == 'response'
                url = record.rec_headers.get_header('WARC-Target-URI')
                if url in exclude_urls:
                    continue
                writer.write_record(record)
                output_num += record.rec_type == 'response'
        logging.info(f'ResourceTypeWarcExtractor: Extracted {output_num} responses from {input_num} responses in {self.input_warc} to {self.output_warc}')
        return exclude_urls
    
    def extract(self) -> "str, list | None":
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
        exclude_urls = self.resource_match_extract()
        if len(exclude_urls) == 0:
            return None
        return self.archive_name, exclude_urls


def resource_warc_worker(col, archive_name, file_suffix, resource_match_type, 
                         failed_fetches, num_throw_resources, run_id):
    archive_dir = CONFIG.archive_dir
    rtw_extractor = ResourceTypeWARCExtractor(archive_dir, col, archive_name,
                                          file_suffix, resource_match_type, 
                                          failed_fetches, num_throw_resources, run_id)
    return rtw_extractor.extract()


def extract_resource_warcs(col, file_suffix, resource_match_type, num_throw_resources=float('inf'), 
                           run_id=None, failed_fetch_file=None, select_archives=None, num_workers=1) -> "list[(str, list[str])]":
    """Extract warcs that only contain certain types of resources (exclude certain types of resources)"""
    dirrs = glob.glob(f'{CONFIG.archive_dir}/writes/{col}/*')
    failed_fetches = {}
    if failed_fetch_file is not None:
        failed_fetches = json.load(open(failed_fetch_file, 'r'))
        failed_fetches = {f['hostname']: f['missing_script']['failFetchScripts'] for f in failed_fetches}
    if select_archives is None:
        if failed_fetch_file:
            select_archives = set([h for h in failed_fetches])
        
    if select_archives is not None:
        dirrs = [d for d in dirrs if os.path.basename(d) in select_archives]
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        results = []
        success = []
        for dirr in dirrs:
            archive_name = os.path.basename(dirr) 
            ff = failed_fetches.get(archive_name)
            if ff:
                ff = [f['url'] for f in ff]
            results.append(executor.submit(resource_warc_worker, 
                                           col=col, 
                                           archive_name=archive_name, 
                                           file_suffix=file_suffix,
                                           resource_match_type=resource_match_type,
                                           failed_fetches=ff,
                                           num_throw_resources=num_throw_resources,
                                           run_id=run_id))
        for r in results:
            try:
                res = r.result()
                if res is not None:
                    success.append(res)
            except Exception as e:
                print(f"Exception occurred: {e}")
    return success
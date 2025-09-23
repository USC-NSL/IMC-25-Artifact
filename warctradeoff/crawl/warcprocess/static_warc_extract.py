import logging
import json
import os
import glob
from urllib.parse import urlsplit, unquote
from warcio.archiveiterator import ArchiveIterator
from warcio.warcwriter import WARCWriter
from concurrent.futures import ProcessPoolExecutor

from warctradeoff.config import CONFIG
from .warc_extract import BaseWarcExtractor

class StaticWarcExtractor(BaseWarcExtractor):
    def __init__(self, archive_dir, col, archive_name, file_suffix, file_prefix='record'):
        super().__init__(archive_dir, col, archive_name, file_suffix, file_prefix)
        self.input_warc = f'{archive_dir}/warcs/{col}/{archive_name}_{file_suffix}.warc'
        self.output_warc = f'{archive_dir}/warcs/{col}/{archive_name}_{file_suffix}.static.warc'

    @staticmethod
    def is_static(url, fetches, stackInfo, html_url):
        target_fetch = fetches[url]
        
        exclude_method = ['POST']
        if target_fetch['method'] in exclude_method:
            return False

        exclude_prefix = ['blob:', 'chrome-extension:', 'javascript:']
        for prefix in exclude_prefix:
            if url.startswith(prefix):
                return False

        if len(stackInfo) == 0:
            return True # * Likely to be initiated by Others, which is static
        for request_stack in stackInfo:
            
            static_initiator_mime = ['css']
            static_initiator_ext = ['.css']
            if  len(request_stack['callFrames']) > 0 \
                and request_stack['callFrames'][0]['functionName'] == '':
                initiator_url = request_stack['callFrames'][0]['url']
                # initiator_url = unquote(initiator_url)
                if unquote(initiator_url) == html_url:
                    return True # * Initiated by the page itself
                initiator_fetch = fetches.get(initiator_url, {'mime': ''})
                for sie in static_initiator_mime:
                    if sie in initiator_fetch['mime']:
                        return True
                initiator_path = urlsplit(initiator_url).path
                initiator_ext = os.path.splitext(initiator_path)[1]
                if initiator_ext in static_initiator_ext:
                    return True
        return False

    def static_fetches(self, html_url) -> dict:
        fetches = {f['url']: f for f in json.load(open(f'{self.dirr}/{self.file_prefix}-{self.file_suffix}_fetches.json'))}
        request_stacks = json.load(open(f'{self.dirr}/{self.file_prefix}-{self.file_suffix}_requestStacks.json'))
        initiators = {}
        for rs in request_stacks:
            for url in rs['urls']:
                if url not in initiators:
                    initiators[url] = rs['stackInfo']
                else:
                    initiators[url] = min([initiators[url], rs['stackInfo']], key=lambda x: len(x))
        fetches_static = {}
        for fetch in fetches.values():
            url = fetch['url']
            is_static = StaticWarcExtractor.is_static(url, fetches, initiators.get(url, []), html_url)
            fetches_static[url] = is_static
        return fetches_static

    def static_warc(self):
        metadata = json.load(open(f'{self.dirr}/metadata.json'))
        url = metadata[self.file_prefix][self.file_suffix]['url']
        self.url = url
        include_urls = self.static_fetches(url)
        input_num, output_num = 0, 0
        with open(self.input_warc, 'rb') as iw, open(self.output_warc, 'wb') as fw:
            writer = WARCWriter(fw)
            for record in ArchiveIterator(iw):
                input_num += record.rec_type == 'response'
                url = record.rec_headers.get_header('WARC-Target-URI')
                if not include_urls.get(url, True):
                    continue
                writer.write_record(record)
                output_num += record.rec_type == 'response'
        logging.info(f'StaticWarcExtractor: Extracted {output_num} responses from {input_num} responses in {self.input_warc} to {self.output_warc}')
    
    def extract(self) -> "str, list | None":
        if not os.path.exists(self.input_warc):
            logging.error("No input warc file")
            return
        if not os.path.exists(f'{self.dirr}/metadata.json'):
            logging.error("No metadata at the corresponding write directory")
            return
        metadata = json.load(open(f'{self.dirr}/metadata.json', 'r'))
        if self.file_prefix not in metadata or self.file_suffix not in metadata['record']:
            logging.error("No file suffix found in metadata")
            return
        self.static_warc()
        return self.archive_name, [self.url]


def static_warc_worker(col, archive_name, file_suffix, file_prefix=None):
    archive_dir = CONFIG.archive_dir
    sw_extractor = StaticWarcExtractor(archive_dir, col, archive_name, file_suffix, file_prefix)
    return sw_extractor.extract()


def extract_static_warcs(col, file_suffix, file_prefix=None, num_workers=1) -> list:
    dirrs = glob.glob(f'{CONFIG.archive_dir}/writes/{col}/*')

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        results = []
        success = []
        for dirr in dirrs:
            archive_name = os.path.basename(dirr) 
            results.append(executor.submit(static_warc_worker, 
                                           col=col, 
                                           archive_name=archive_name, 
                                           file_suffix=file_suffix,
                                           file_prefix=file_prefix))
        for r in results:
            try:
                res = r.result()
                if res is not None:
                    success.append(res)
            except Exception as e:
                print(f"Exception occurred: {e}")
    return success
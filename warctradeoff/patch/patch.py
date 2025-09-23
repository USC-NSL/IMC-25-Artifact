import os, io
import json
import logging
import glob
from urllib.parse import quote
from warcio.archiveiterator import ArchiveIterator
from warcio.warcwriter import WARCWriter
from concurrent.futures import ProcessPoolExecutor

from warctradeoff.patch import match as patch_match
from warctradeoff.patch import parse as patch_parse
from warctradeoff.patch.initiator import build_initiators
from warctradeoff.utils import logger, upload
from warctradeoff.config import CONFIG

class Patcher:
    def __init__(self, 
                 dynamic_prefix,
                 dynamic_warc, 
                 static_prefix,
                 static_warc):
        self.dynamic_prefix = dynamic_prefix
        self.dynamic_warc = dynamic_warc
        self.static_prefix = static_prefix
        self.static_warc = static_warc
        
        self.d_page_url = self._get_page_url(dynamic_prefix)
        self.s_page_url = self._get_page_url(static_prefix)
        self.d_page_ts = self._get_page_ts(dynamic_prefix)
        self.s_page_ts = self._get_page_ts(static_prefix)

        self.d_html = self._get_html(dynamic_warc, self.d_page_url)
        self.s_html = self._get_html(static_warc, self.s_page_url)
        
        self.d_parser = patch_parse.HTMLParser(self.d_html)
        self.s_parser = patch_parse.HTMLParser(self.s_html)

    def _get_page_url(self, prefix):
        dirname = os.path.dirname(prefix)
        filename = os.path.basename(prefix)
        file_prefix, file_suffix = filename.split('-', 1)
        metadata = json.load(open(os.path.join(dirname, 'metadata.json')))
        url = metadata[file_prefix][file_suffix]['url']
        return quote(url, safe=':/?&=') # Encode URL to be valid for WARC
    
    def _get_html(self, warc, url):
        with open(warc, 'rb') as iw:
            for record in ArchiveIterator(iw):
                if record.rec_type == 'response':
                    if record.rec_headers.get('WARC-Target-URI') == url:
                        return record.content_stream().read().decode()
        raise Exception(f'Target URL not found in {warc} for {url}')

    def _get_page_ts(self, prefix):
        dirname = os.path.dirname(prefix)
        filename = os.path.basename(prefix)
        file_prefix, file_suffix = filename.split('-', 1)
        metadata = json.load(open(os.path.join(dirname, 'metadata.json')))
        return metadata[file_prefix][file_suffix]['ts']

    def _build_initiators(self, prefix, url) -> set:
        dirname = os.path.dirname(prefix)
        prefix = os.path.basename(prefix)
        initiators = build_initiators(dirname, prefix, url, 
                                      content_type=['html', 'js', 'javascript', 'json', 'plain'])
        all_initiators = set()
        for initiator in initiators.values():
            if not initiator.is_root:
                all_initiators |= set(initiator.root_initiators)
        return all_initiators
    
    @property
    def _patched_warc(self):
        warc_dir, warc_file = os.path.split(self.static_warc)
        warc_file, _ = os.path.splitext(warc_file)
        return f'{warc_dir}/{warc_file}.patched.warc'
    
    def build_initiators(self):
        """Separate method out for easy testing"""
        # # * Approach 1: Seletive patch
        # self.d_initiators = self._build_initiators(self.dynamic_prefix, self.d_page_url)
        # * Approach 2: Full patch
        pass

    def patch(self):
        tag_matches = patch_match.match_tag_list(self.s_parser, self.d_parser)
        s_taglists, d_taglists = [], []
        for s_tag_list, d_tag_list in tag_matches:
            # # * Approach 1: Selective patch
            # for i_tag in self.d_initiators:
            #     if d_tag_list.contains(i_tag):
            #         old_taglists.append(s_tag_list)
            #         new_taglists.append(d_tag_list)
            #         break
            # * Approach 2: Full patch
            s_taglists.append(s_tag_list)
            d_taglists.append(d_tag_list)
        logging.debug(f"Old (static) tags: {s_taglists}")
        # for old_taglist, new_taglist in zip(old_taglists, new_taglists):
        #     # # ! Test 1: Simple soup in soup out
        #     # self.s_parser.html = str(self.s_parser.soup)
        #     # break
        #     # ! Test 2: Do nothing
        #     break
        #     # ! Normal case
        #     self.s_parser.replace_tags(old_taglist, new_taglist, ts=self.d_page_ts)
        logging.debug(f"New (dynamic) tags: {d_taglists}")
        static_html = self.s_parser.replace_tags(s_taglists, d_taglists)
        static_html = static_html.encode('utf-8')
        static_html_length = str(len(static_html))
        with open(self.static_warc, 'rb') as iw, open(self._patched_warc, 'wb') as fw:
            writer = WARCWriter(fw)
            for record in ArchiveIterator(iw):
                if record.rec_type == 'response' and record.rec_headers.get('WARC-Target-URI') == self.s_page_url:
                    # Change content to s_html_new, and content-length
                    record.http_headers.replace_header('Content-Length', static_html_length)
                    warc_headers_dict = {
                        'WARC-Type': 'response',
                        'WARC-Target-URI': record.rec_headers.get('WARC-Target-URI'),
                        'WARC-Date': record.rec_headers.get('WARC-Date'),
                    }
                    new_record = writer.create_warc_record(self.s_page_url,
                                                            'response',
                                                            payload=io.BytesIO(static_html),
                                                            warc_headers_dict=warc_headers_dict,
                                                            http_headers=record.http_headers)
                    writer.write_record(new_record)
                else:
                    writer.write_record(record)
        return self._patched_warc


def patch_warc_worker(col, archive_name, dynamic_suffix, static_suffix):
    logging.info(f"Patching {archive_name}")
    archive_dir = CONFIG.archive_dir
    dynamic_warc = f'{archive_dir}/warcs/{col}/{archive_name}_{dynamic_suffix}.warc'
    static_warc = f'{archive_dir}/warcs/{col}/{archive_name}_{static_suffix}.static.warc'
    if not os.path.exists(dynamic_warc) or not os.path.exists(static_warc):
        logging.error(f"No input warc file: dynamic={os.path.exists(dynamic_warc)} static={os.path.exists(static_warc)}")
        return
    dirr = f'{archive_dir}/writes/{col}/{archive_name}'
    if not os.path.exists(f'{dirr}/metadata.json'):
        logging.error(f"No metadata at the corresponding write directory {dirr}")
        return
    metadata = json.load(open(f'{dirr}/metadata.json', 'r'))
    if 'record' not in metadata:
        logging.error(f"No record found in metadata")
        return
    if dynamic_suffix not in metadata['record'] or static_suffix not in metadata['record']:
        logging.error(f"No file suffix found in metadata dynamic={dynamic_suffix in metadata['record']} static={static_suffix in metadata['record']}")
        return
    try:
        patcher = Patcher(
            dynamic_prefix=f'{dirr}/record-{dynamic_suffix}',
            dynamic_warc=dynamic_warc,
            static_prefix=f'{dirr}/record-{static_suffix}',
            static_warc=static_warc
        )
        patcher.build_initiators()
        patcher.patch()
        return archive_name
    except Exception as e:
        logging.error(f"Exception occurred in patching: {e}")
        return None


def patch_warcs(col, dynamic_suffix, static_suffix, num_workers=1):
    dirrs = glob.glob(f'{CONFIG.archive_dir}/writes/{col}/*')

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        results = []
        success = []
        for dirr in dirrs:
            archive_name = os.path.basename(dirr) 
            results.append(executor.submit(patch_warc_worker, 
                                           col=col, 
                                           archive_name=archive_name,
                                           dynamic_suffix=dynamic_suffix,
                                           static_suffix=static_suffix))
        for r in results:
            try:
                res = r.result()
                if res is not None:
                    success.append(res)
            except Exception as e:
                logging.error(f"Exception occurred: {e}")
    return success
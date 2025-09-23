import logging
import os
import glob
import datetime
from warcio.archiveiterator import ArchiveIterator
from warcio.warcwriter import WARCWriter
from concurrent.futures import ProcessPoolExecutor

from warctradeoff.config import CONFIG
from .warc_extract import BaseWarcExtractor

class CacheController:
    """Logic referred from github.com/psf/cachecontrol/blob/master/cachecontrol/controller.py"""
    def __init__(self, warc_record, static_ts: datetime.datetime):
        self.warc_record = warc_record
        self.date = warc_record.rec_headers.get_header('WARC-Date')
        self.date = datetime.datetime.fromisoformat(self.date.rstrip('Z')).replace(tzinfo=datetime.timezone.utc)
        self.static_ts = static_ts
        self.http_headers = warc_record.http_headers
        self.cache_control = None

    def parse_cache_control(self):
        known_directives = {
            # https://tools.ietf.org/html/rfc7234#section-5.2
            "max-age": (int, True),
            "max-stale": (int, False),
            "min-fresh": (int, True),
            "no-cache": (None, False),
            "no-store": (None, False),
            "no-transform": (None, False),
            "only-if-cached": (None, False),
            "must-revalidate": (None, False),
            "public": (None, False),
            "private": (None, False),
            "proxy-revalidate": (None, False),
            "s-maxage": (int, True),
        }
        http_headers = self.warc_record.http_headers
        cache_control = http_headers.get('Cache-Control', http_headers.get('cache-control', ''))
        
        retval: dict[str, "int | None"] = {}
        
        for cc_directive in cache_control.split(','):
            if not cc_directive.strip():
                continue
            parts = cc_directive.split("=", 1)
            directive = parts[0].strip()
            try:
                typ, required = known_directives[directive]
            except KeyError:
                continue

            if not typ or not required:
                retval[directive] = None
            if typ:
                try:
                    retval[directive] = typ(parts[1].strip())
                except:
                    pass
        return retval

    @property
    def cacheable(self):
        self.cache_control = self.parse_cache_control()
        if not self.cache_control:
            return False
        if "no-store" in self.cache_control:
            return False
        if "*" in self.http_headers.get("vary", ""):
            return False    
        max_age = self.cache_control.get("max-age")
        expire_time = None
        if max_age is not None and max_age > 0:
            expire_time = self.date + datetime.timedelta(seconds=max_age)
        elif 'expires' in self.http_headers:
            expire_time = self.http_headers.get("expires")
            try:
                expire_time =datetime.datetime.strptime(expire_time, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=datetime.timezone.utc) 
            except:
                expire_time = None
        if expire_time and self.date <= self.static_ts <= expire_time:
            return True

class ValidCachedWarcExtractor(BaseWarcExtractor):
    def __init__(self, archive_dir, col, archive_name, file_suffix, static_ts: str, file_prefix='record'):
        super().__init__(archive_dir, col, archive_name, file_suffix, file_prefix)
        self.static_ts = datetime.datetime.strptime(static_ts, '%Y%m%d%H%M').replace(tzinfo=datetime.timezone.utc)
        self.input_warc = f'{archive_dir}/warcs/{col}/{archive_name}_{file_suffix}.warc'
        self.output_warc = f'{archive_dir}/warcs/{col}/{archive_name}_{file_suffix}.{static_ts}.cache.warc'
        
    def valid_cached_warc(self):
        input_num, output_num = 0, 0
        with open(self.input_warc, 'rb') as iw, open(self.output_warc, 'wb') as fw:
            writer = WARCWriter(fw)
            for record in ArchiveIterator(iw):
                input_num += record.rec_type == 'response'
                if record.rec_type == 'response' and not CacheController(record, self.static_ts).cacheable:
                    continue
                writer.write_record(record)
                output_num += record.rec_type == 'response'
        logging.info(f'ValidCachedWarcExtractor: Extracted {output_num} responses from {input_num} responses in {self.input_warc} to {self.output_warc}')

    def extract(self) -> "str | None":
        if not os.path.exists(self.input_warc):
            logging.error("No input warc file")
            return
        self.valid_cached_warc()
        return self.archive_name

def valid_cached_warc_worker(col, archive_name, file_suffix, static_ts):
    archive_dir = CONFIG.archive_dir
    vcw_extractor = ValidCachedWarcExtractor(archive_dir, col, archive_name,
                                             file_suffix, static_ts)
    return vcw_extractor.extract()

def extract_valid_cached_warcs(col, file_suffix, static_ts, num_workers=1) -> list:
    dirrs = glob.glob(f'{CONFIG.archive_dir}/writes/{col}/*')

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        results = []
        success = []
        for dirr in dirrs:
            archive_name = os.path.basename(dirr) 
            results.append(executor.submit(valid_cached_warc_worker, 
                                           col=col, 
                                           archive_name=archive_name, 
                                           file_suffix=file_suffix,
                                           static_ts=static_ts))
        for r in results:
            try:
                res = r.result()
                if res is not None:
                    success.append(res)
            except Exception as e:
                print(f"Exception occurred: {e}")
    return success
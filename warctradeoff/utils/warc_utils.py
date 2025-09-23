import os

from warcio.archiveiterator import ArchiveIterator
from collections import defaultdict

def strip_url(url):
    return url
    us = urlsplit(url)
    us = us._replace(query='', fragment='')
    return urlunsplit(us)

def read_warc_responses(warc_file):
    url_response = defaultdict(set)
    if not os.path.exists(warc_file):
        return url_response
    with open(warc_file, 'rb') as f:
        for record in ArchiveIterator(f):
            if record.rec_type == 'response':
                url = record.rec_headers.get_header('WARC-Target-URI')
                content = record.content_stream().read()
                url_response[strip_url(url)].add(content)
    return url_response
"""
Trace the source of a URL token
"""
import re
import json
import functools
from urllib.parse import urlsplit, unquote
from collections import defaultdict

from warctradeoff.config import CONFIG
from warctradeoff.utils import warc_utils, url_utils

WARC_PATH = f'{CONFIG.archive_dir}/warcs/{CONFIG.collection}'

WARC_CACHE = {}
KEYWORDS_CACHE = {}

def cache_read_warc(hostname, ts):
    path = f'{WARC_PATH}/{hostname}_{ts}.warc'
    if path in WARC_CACHE:
        return WARC_CACHE[path]
    warc = warc_utils.read_warc_responses(path)
    WARC_CACHE[path] = warc
    return warc

def split_text(text):
    """Split text into words and filter out non-words"""
    # tokens = nltk.word_tokenize(text)
    DELIMITERS = [' ', '\n', '\t', 
                  ',', '.', '!', '?', ';', ':', 
                  '(', ')', '[', ']', '{', '}', '\'', '\"',
                  '/', '\\', '-', '_', '=', '+', '*', 
                  '&', '^', '%', '$', '#', '@', '!', '~']
    pattern = f"[{re.escape(''.join(DELIMITERS))}]+"
    tokens = re.split(pattern, text)
    return tokens

def cache_keywords_parse(hostname, ts):
    path = f'{WARC_PATH}/{hostname}_{ts}.warc'
    if path in KEYWORDS_CACHE:
        return KEYWORDS_CACHE[path]
    warc = cache_read_warc(hostname, ts)
    url_keywords = {}
    for url, response in warc.items():
        try:
            response = list(response)[0]
            text_response = response.decode()
        except Exception as e:
            # print(f"Error decoding response for {url}: {e}")
            continue
        keywords = split_text(text_response)

        keywords = set(keywords)
        url_keywords[url] = keywords
    KEYWORDS_CACHE[path] = url_keywords
    return url_keywords

class URLTokens(url_utils.URLTokens):
    def simi_scores(self, other):
        if self.ext != other.ext:
            return 0
        if len(self.tokens) != len(other.tokens):
            return 0
        scores = 0
        for self_t, other_t in zip(self.tokens, other.tokens):
            if len(self_t) != len(other_t):
                return 0
            if self_t == other_t:
                scores += 10
                continue
            for st, ot in zip(self_t, other_t):
                if st == ot:
                    scores += 1
                elif self.string_type(st) == self.string_type(ot):
                    scores += 0.1
        return scores

    def is_update_url(self, other):
        """Detect if this URL is an update/older version of the other URL"""
        if self.hostname != other.hostname:
            return False
        if self.ext != other.ext:
            return False
        if len(self.tokens) != len(other.tokens):
            return False
        for s_tokens, o_tokens in zip(self.tokens, other.tokens):
            if len(s_tokens) != len(o_tokens):
                return False
            if s_tokens == o_tokens:
                continue
            for s_token, o_token in zip(s_tokens, o_tokens):
                if self.string_type(s_token) != self.string_type(o_token):
                    return False
        return True


class URLSrcTracer:
    def __init__(self, url, hostname, ts):
        self.url = url
        self.url_tokens = URLTokens(url)
        self.hostname = hostname
        self.ts = ts
        self.warc = cache_read_warc(hostname, ts)
    
    def most_similar_urls(self, other_hostname, other_ts, n=10):
        # TODO: Maybe can return multiple same similar URLs
        other_warc = cache_read_warc(other_hostname, other_ts)
        simi_scores = []
        for other_url in other_warc:
            other_tokens = URLTokens(other_url)
            score = self.url_tokens.simi_scores(other_tokens)
            simi_scores.append((score, other_url)) 
        simi_scores.sort(reverse=True)
        # print(f"Most similar URL: {json.dumps(simi_scores[:10], indent=2)}")
        if len(simi_scores) == 0:
            return []
        simi_scores = [(s[0], s[1]) for s in simi_scores if s[0] > 0]
        return simi_scores[:min(n, len(simi_scores))]

    @functools.cached_property
    def sources(self):
        """
        All sources that has the keywords in the URL
        """
        url_keywords = cache_keywords_parse(self.hostname, self.ts)
        sources = []
        for tokens in self.url_tokens.tokens:
            sources.append([])
            for token in tokens:
                sources[-1].append([])
                for url, keywords in url_keywords.items():
                    if token in keywords:
                        sources[-1][-1].append((URLTokens(url)))
        return sources
    
    def inferrable(self, other_tracer) -> "Tuple(bool, list)": 
        self_tokens, other_tokens = self.url_tokens, other_tracer.url_tokens
        self_sources, other_sources = self.sources, other_tracer.sources
        matches = []
        for i, (s_tokens, o_tokens) in enumerate(zip(self_tokens.tokens, other_tokens.tokens)):
            matches.append([])
            for j, (s_token, o_token) in enumerate(zip(s_tokens, o_tokens)):
                matches[-1].append([])
                if s_token == o_token:
                    continue
                s_keyword_urls, o_keyword_urls = self_sources[i][j], other_sources[i][j]
                matched_pairs = []
                for s_keyword_url in s_keyword_urls:
                    for o_keyword_url in o_keyword_urls:
                        if s_keyword_url.is_update_url(o_keyword_url):
                            matched_pairs.append({
                                'this_token': s_token,
                                'other_token': o_token,
                                'this_src': s_keyword_url.url, 
                                'other_src': o_keyword_url.url
                            })
                if len(matched_pairs) == 0:
                    return False, matches
                matches[-1][-1] = matched_pairs
        return True, matches
                
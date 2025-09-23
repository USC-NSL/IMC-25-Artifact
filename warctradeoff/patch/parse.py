import os
import re
import time
import functools
import nltk
import json
from nltk.corpus import words
from bs4 import BeautifulSoup
from collections import defaultdict
from urllib.parse import urlsplit

import logging
from warctradeoff.utils import logger, url_utils

# Download the corpus if you haven't already
try:
    nltk.data.find('corpora/words.zip')  # Check for zipped version
except LookupError:
    nltk.download('words')
word_list = set(words.words())

def is_word(word):
    return word.lower() in word_list

@functools.cache
def tags(text):
    # 1 is_closing
    # 2 tag_name
    # 3 attributes
    tag_pattern = re.compile(r'<\s*(/?)([a-zA-Z0-9\-]+)([\s\n][^<>]*)?>')
    return list(tag_pattern.finditer(text))

@functools.cache
def comment_tags(text):
    # 1 comment
    tag_pattern = re.compile(r'<!--(.*?)-->')
    return list(tag_pattern.finditer(text))

def self_closing(tag):
    if tag.group().endswith('/>'):
        return True
    closing_tags = {'br', 'img', 'input', 'link', 'meta', 'base', 'hr', 'area', 'col', 'embed', 'keygen', 'param', 'source', 'track'}
    return tag.group(2) in closing_tags

def preprocess_tag(tag: "bs4.element.Tag", old_tag: "bs4.element.Tag",) -> "bs4.element.Tag":
    """Preprocess a tag before insertion."""
    # * preserve some attributes if they appears in both tags
    p_attrs = ['nonce', 'crossorigin']
    for p_attr in p_attrs:
        if old_tag.has_attr(p_attr) and tag.has_attr(p_attr):
            tag[p_attr] = old_tag[p_attr]
    return tag


class URLTokens(url_utils.URLTokens):
    def same_func_script(self, other):
        """Check if self's URL is essentially the same as the other URL.
        Currently done by heuristics, that only some hash or date should be different
        """
        if self.ext != other.ext:
            return False
        if len(self.tokens) != len(other.tokens):
            return False
        for self_ts, other_ts in zip(self.tokens, other.tokens):
            if len(self_ts) != len(other_ts):
                return False
            if self_ts == other_ts:
                continue
            for st, ot in zip(self_ts, other_ts):
                if len(st) != len(ot):
                    return False
                # * For pure alpha token, if they are different, unlike for the URL to serve the same purpose
                if is_word(st) and st != ot:
                    return False
        return True

class Tag:
    def __init__(self, text: str, start_loc: tuple, full_loc: tuple, is_comment: bool):
        self.text = text
        self.start_loc = start_loc
        self.full_loc = full_loc
        self.is_comment = is_comment
        self.unique_attrs = set()

    @functools.cached_property
    def soup(self):
        soup = BeautifulSoup(self.text, 'html.parser').find()
        if soup is None:
            logging.debug(f"Got None soup for {self.text}")
        return soup

    @functools.cached_property
    def id(self):
        assert self.is_comment == False, "id should not be used for comment tags"
        return self.soup.attrs.get('id', None)
        
    def contains(self, offset, start=False):
        if start:
            return self.star_loc[0] <= offset < self.start_loc[1]
        else:
            return self.full_loc[0] <= offset < self.full_loc[1]

    def match(self, tag: "str | bs4.element.Tag") -> bool:
        if self.is_comment:
            return self.text == tag
        if isinstance(tag, str):
            tag = BeautifulSoup(tag, 'html.parser').find()
        return str(self.soup) == str(tag)

    def __str__(self):
        return self.text
    
    def __repr__(self):
        tag_str = str(self.text).replace('\n', '')
        return f"{tag_str[:50]}..."

    def __eq__(self, other):
        """Function for deciding if two tags are the same
        Based on multiple heuristics:
        - Same tag id
        - Attributes' keys are the same
        - Similar src name
        """
        if set(self.soup.attrs.keys()) != set(other.soup.attrs.keys()):
            return False
        if self.id and self.id == other.id:
            return True
        if len(self.unique_attrs) > 0 and self.unique_attrs == other.unique_attrs:
            return True
        if self.soup.has_attr('src') and other.soup.has_attr('src'):
            tokens_0 = URLTokens(self.soup['src'])
            tokens_1 = URLTokens(other.soup['src'])
            if tokens_0.same_func_script(tokens_1):
                return True
        # * Comparing inline script
        if self.text and self.text == other.text:
            return True
        return False

    def __hash__(self):
        if self.id:
            return hash((self.soup.name, self.id))
        return hash(self.text)


class TagList:
    def __init__(self, tags: "list[Tag]", prev_tag:"Tag"=None, next_tag:"Tag"=None):
        self.tags = tags
        self.prev_tag = prev_tag
        self.next_tag = next_tag

    def construct_unique_attrs(self):
        attr_list = defaultdict(list)
        for tag in self.tags:
            tag.unique_attrs = set()
            for attr in tag.soup.attrs.keys():
                attr_list[attr].append(tag)
        for attr, tag_list in attr_list.items():
            if len(tag_list) == 1:
                tag_list[0].unique_attrs.add(attr)
    
    def contains(self, target_tag):
        for tag in self.tags:
            if tag.match(target_tag):
                return True
        return False

    @property
    def length(self):
        return len(self.tags)

    def __str__(self):
        return ''.join([str(tag)for tag in self.tags])
    
    def __repr__(self):
        tag_list = [repr(tag)for tag in self.tags]
        return json.dumps(tag_list, indent=2)


class HTMLParser:
    @staticmethod
    def norm_html(html):
        replacements = [
            (r'<a([^>]*)/>', r'<a\1>'), # Fix <a ... /> to <a ...></a>
            (r'<br\s*/>', '<br>'), # Fix <br/> or <br /> to <br>
        ]
        for pattern, replacement in replacements:
            html = re.sub(pattern, replacement, html)
        return html

    def __init__(self, html, url=None):
        """
        tags_comment: list [(tag, start, end)] comment tags
        Use tag (re.Match) object to identify if the string is the same
        """
        self.url = url
        self.html = html
        self.tags = []
        self._parse_tags()

        self.tag_info_map = {}
        self.tag_info_list = {}

    @property
    def tags_start(self):
        """return tags ordered in starting range"""
        return sorted(self.tags, key=lambda x: x.start_loc[0])
    
    @property
    def tags_full(self):
        """return tags ordered in full range end. 
        If multiple tags have the same end, prefer one starts later (inner)"""
        return sorted(self.tags, key=lambda x: (x.full_loc[1], -x.full_loc[0]))
    
    def loc_2_offset(self, loc):
        row, col = loc
        lines = self.html.split('\n')
        return sum(len(l) + 1 for l in lines[:row]) + col
    
    def in_comment(self, offset):
        for tag in self.tags:
            if tag.is_comment and tag.contains(offset):
                return True
        return False

    def _parse_tags(self):
        stack = []

        for tag in comment_tags(self.html):
            start, end = tag.start(), tag.end()
            self.tags.append(Tag(text=tag.group(0), 
                                 start_loc=(start, end), 
                                 full_loc=(start, end), 
                                 is_comment=True))       
        for tag in tags(self.html):
            start, end = tag.start(), tag.end()
            is_closing = tag.group(1)
            tag_name = tag.group(2)
            if self.in_comment(start):
                continue
            if is_closing:
                while len(stack):
                    start_tag, start_st, start_ed = stack.pop()
                    start_tag_name = start_tag.group(2)
                    start_loc = (start_st, start_ed)
                    if start_tag_name != tag_name:
                        # * Some HTML has tags without closing
                        # * If see such case, first backfill the tag
                        full_loc = (start_st, start)
                        self.tags.append(Tag(text=self.html[full_loc[0]:full_loc[1]],
                                            start_loc=start_loc, 
                                            full_loc=full_loc,
                                            is_comment=False))
                    else:
                        full_loc = (start_st, end)
                        self.tags.append(Tag(text=self.html[full_loc[0]:full_loc[1]],
                                            start_loc=start_loc, 
                                            full_loc=full_loc,
                                            is_comment=False))
                        break                        
            elif self_closing(tag):
                self.tags.append(Tag(text=self.html[start:end], 
                                    start_loc=(start, end),
                                    full_loc=(start, end),
                                    is_comment=False))
            else:
                stack.append((tag, start, end))

    def find_minimal_tag(self, offset):
        for tag in self.tags_full:
            if tag.contains(offset):
                return tag.text
        assert False, f"Could not find tag at offset {offset}"
    
    def match_tag_list(self, tag_match_func):
        matched_list = TagList([])
        for tag in self.tags:
            if tag.is_comment:
                continue
            # tag.prev_tag = self.tags[i - 1] if i > 0 else None
            # tag.next_tag = self.tags[i + 1] if i < len(self.tags) - 1 else None
            if tag_match_func(tag.soup):
                matched_list.tags.append(tag)
        matched_list.construct_unique_attrs()
        return matched_list.tags

    def tag_by_loc(self, loc:"tuple(int, int)") -> str:
        """Bind given loc to corresponding source tag""" 
        row, col = loc
        logging.debug(f"HTMLParser.tag_by_loc: {row}, {col}")

        offset = self.loc_2_offset(loc)
        return self.find_minimal_tag(offset)

    @functools.cache
    def _src_by_keyword(self, keyword: str) -> str | None:
        """Bind given keywords to corresponding source tags"""
        logging.debug(f"Source._src_by_keyword: {keyword}")
        regex = re.compile(re.escape(keyword))
        matches = regex.finditer(self.html)
        tags = set()
        for match in matches:
            start = match.start()
            tag = self.find_minimal_tag(start)
            tags.add(tag)
        # * Heuristic: if there are multiple tags, the keyworkd is likely to be not unique
        if len(tags) > 1 or len(tags) == 0:
            return None
        return tags.pop()
    
    def src_by_keywords(self, keywords:"list[str]") -> set[str]:
        """Bind given keywords to corresponding source tags"""
        start = time.time()
        all_tags = set()
        for keyword in keywords:
            tag = self._src_by_keyword(keyword)
            if tag is not None:
                all_tags.add(tag)
        logging.debug(f"Source.src_by_keywords: {time.time() - start:.2f}s. Num keywords: {len(keywords)}")
        return all_tags

    def replace_tags(self, old_tag_lists: "list[TagList]", new_tag_lists: "list[TagList]"):
        """Replace tags in html.
        Note that the old_tags should come from the same soup as self.soup
        And the replacement is irreversible
        """
        new_html = ''
        cursor = 0
        for old_tag_list, new_tag_list in zip(old_tag_lists, new_tag_lists):
            idx = 0
            for idx in range(min(old_tag_list.length, new_tag_list.length)):
                old_tag = old_tag_list.tags[idx]
                new_tag = new_tag_list.tags[idx]
                new_html += self.html[cursor:old_tag.start_loc[0]]
                new_html += str(preprocess_tag(new_tag.soup, old_tag.soup))
                cursor = old_tag.full_loc[1]
            for o_idx in range(idx+1, old_tag_list.length):
                old_tag = old_tag_list.tags[o_idx]
                new_html += self.html[cursor:old_tag.start_loc[0]]
                cursor = old_tag.full_loc[1]
            for n_idx in range(idx+1, new_tag_list.length):
                new_tag = new_tag_list.tags[n_idx]
                new_html += str(preprocess_tag(new_tag.soup, old_tag_list.tags[-1].soup))
        return new_html + self.html[cursor:]
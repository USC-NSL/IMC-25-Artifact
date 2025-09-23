import re
import bs4
from urllib.parse import urlsplit, parse_qs, urlunsplit, urlencode

from difflib import SequenceMatcher

from warctradeoff.patch.parse import TagList, Tag, HTMLParser

def string_type(string):
    """Check if a string  is pure alpha, pure numeric, or alphanumeric"""
    if string.isalpha():
        return 'alpha'
    if string.isnumeric():
        return 'numeric'
    return 'alphanumeric'

def add_query_param(url, param_key, param_value):
    """Adds or updates a query parameter in a URL."""
    us = urlsplit(url)
    query = parse_qs(us.query)
    query[param_key] = param_value
    new_query = urlencode(query, doseq=True)
    return urlunsplit(us._replace(query=new_query))

def add_ts(tag_str, ts):
    """Finds URLs in a tag string and appends a query parameter."""
    # # Regex pattern for URLs (supports absolute, protocol-relative, and relative URLs)
    # url_pattern = re.compile(r'(["\'])(https?:\/\/[^\s"\'<>]+|\/[^\s"\'<>]+)(["\'])')
    # Option 2, remove related URLs
    url_pattern = re.compile(r'(["\'])((?:https?:)?\/\/[^\s"\'<>]+\/[^\s"\'<>]+)(["\'])')
    def replace_url(match):
        quote, url, end_quote = match.groups()
        # * Deal with URL encoded in JSON
        if url.endswith('\\'):
            url = url[:-1]
            end_quote = '\\' + end_quote
        modified_url = add_query_param(url, 'pywb_ts', ts)
        return f'{quote}{modified_url}{end_quote}'
    # Replace all URLs found in the tag string
    return url_pattern.sub(replace_url, tag_str)

def is_script(tag):
    """Default function for tag_match_func"""
    if isinstance(tag, str):
        tag = bs4.BeautifulSoup(tag, 'html.parser').find()
    if tag is None:
        return False
    assert isinstance(tag, bs4.element.Tag), f"Expected a BeautifulSoup Tag, got {type(tag)}"
    if tag.name == 'script':
        return True
    if tag.name == 'link' and tag.get('as') == 'script':
        return True
    return False

def is_in_body(tag):
    if isinstance(tag, str):
        tag = bs4.BeautifulSoup(tag, 'html.parser').find()
    if tag is None:
        return False
    assert isinstance(tag, bs4.element.Tag), f"Expected a BeautifulSoup Tag, got {type(tag)}"
    if tag.name == 'div':
        return True
    return False

def match_tag_list(left: "parse.HTMLParser", right: "parse.HTMLParser", tag_match_func: "func(str)"=None) -> "[tuple(TagList, TagList)]":
    """Match tag list between left and right based on LCS
    Returns:
        [(TagList, TagList)]: Each tuple is a pair of matched taglists
    """
    if tag_match_func is None:
        tag_match_func = is_script
    left_seq, right_seq = left.match_tag_list(tag_match_func), right.match_tag_list(tag_match_func)
    if len(left_seq) == 0:
        first_div = left.match_tag_list(is_in_body)[0]
        loc = first_div.start_loc[0]
        dummy_tag = Tag(text='',
                        start_loc=(loc, loc),
                        full_loc=(loc, loc),
                        is_comment=False)
        return [(TagList([dummy_tag]), TagList(right_seq))]
    matcher = SequenceMatcher(None, left_seq, right_seq)
    

    result = []
    
    last_i2 = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            result += [(TagList([left_seq[i]]), TagList([right_seq[j]])) for i, j in zip(range(i1, i2), range(j1, j2))]
        elif tag == 'replace':
            result.append((TagList(left_seq[i1:i2]), TagList(right_seq[j1:j2])))
        elif tag == 'delete':
            result.append((TagList(left_seq[i1:i2]), TagList([])))
        elif tag == 'insert':
            result.append((TagList([], next_tag=left_seq[last_i2]), TagList(right_seq[j1:j2])))
        last_i2 = i2
    
    return result
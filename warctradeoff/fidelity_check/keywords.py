"""
Extracting and matching keywords from fidelity information such as layout trees
"""
import nltk
import json
import functools
import bs4
import re
from collections import Counter

words = nltk.corpus.words.words()

def has_dimension(element):
    xpath = element['xpath']
    tag_name = xpath.split('/')[-1].split('[')[0]
    if tag_name == '#text':
        return True
    dimension = element.get('dimension', None)
    if dimension is None:
        return False
    width = dimension.get('width', 0)
    height = dimension.get('height', 0)
    return width * height > 0

class KeywordMapper:
    def __init__(self, dirr, prefix):
        self.dirr = dirr
        self.prefix = prefix
        self.resource_contents = {}
        self.resource_keywords = Counter()
        
    @staticmethod
    def split_text(text):
        """Split text into words and filter out non-words"""
        # tokens = nltk.word_tokenize(text)
        DELIMITERS = [' ', '\n', '\t', ',', '.', '!', '?', ';', ':']
        pattern = f"[{re.escape(''.join(DELIMITERS))}]+"
        tokens = re.split(pattern, text)
        return tokens

    @functools.cached_property
    def layout_tree_keywords(self):
        dom = json.load(open(f'{self.dirr}/{self.prefix}_dom.json', 'r'))
        all_texts = ''
        target_attrs = {
            'a': ['href'],
            'img': ['src'],
        }
        for e in dom:
            if not has_dimension(e):
                continue
            text = e.get('text', '')
            try:
                soup = bs4.BeautifulSoup(text, 'html.parser').find()
                text = soup.get_text()
                tag_name = e['xpath'].split('/')[-1].split('[')[0]
                if tag_name in target_attrs:
                    for attr in target_attrs[tag_name]:
                        if attr in e:
                            text += ' ' + e[attr]
            except:
                pass
            all_texts += ' ' + text
        words = self.split_text(all_texts)
        keywords = Counter(words)
        keywords = {k for k, v in keywords.items() if v == 1}
        return keywords

    def critical_resource(self, resource_content):
        """Extract keywords from critical resource content"""
        words = set(self.split_text(resource_content))
        intersection = words & self.layout_tree_keywords
        return len(intersection) > 0, intersection

    def add_resource(self, url, content):
        if url in self.resource_contents:
            return
        words = self.split_text(content)
        for w in words:
            self.resource_keywords[w] += 1
        self.resource_contents[url] = words
    
    def critical_resources(self, urls) -> dict[str, set]:
        unique_keywords = {k for k in self.resource_keywords if self.resource_keywords[k] == 1}
        critical_dict = {}
        for url in urls:
            if url not in self.resource_contents:
                critical_dict[url] = set()
                continue
            words = set(self.resource_contents[url])
            intersection = words & unique_keywords & self.layout_tree_keywords
            critical_dict[url] = intersection
        return critical_dict

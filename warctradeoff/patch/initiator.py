import json
import functools

from warctradeoff.patch import parse as patch_parse
from warctradeoff.config import CONFIG


class Initiator:
    def __init__(self, url, stack, src=None):
        self.url = url
        self.stack = stack
        self.initiators = []
        self.src = src
        self.parser = None
   
    def add_initiator(self, initiator, loc):
        self.initiators.append((initiator, loc))

    def get_src(self, loc):
        if self.parser is None:
            self.parser = patch_parse.HTMLParser(self.src, url=self.url)
        return self.parser.tag_by_loc(loc)

    @property
    def is_root(self) -> bool:
        return len(self.initiators) == 0
    
    @property
    def keywords(self) -> list:
        tokenizer = patch_parse.URLTokens(self.url)
        tokens = tokenizer.tokens
        tokens[-1] = tokens[-1][:-1] # Remove the extension
        return list(set([t for token in tokens for t in token if t != '']))

    @functools.cache
    def _root_initiators_direct(self) -> "tuple(set, Initiator)":
        all_tags, root_init = set(), None
        for initiator, loc in self.initiators:
            if initiator.is_root: # Initiator is the root of the tree
                all_tags.add(initiator.get_src(loc))
                root_init = initiator
            else:
                tags, init = initiator._root_initiators_direct()
                assert root_init is None or root_init is init, f"Root initiators are not the same: {root_init.url} != {init.url}"
                root_init = init
                all_tags |= tags
        return all_tags, root_init

    def _root_initiators_keywords(self, root_init: "Initiator") -> set:
        tags = root_init.parser.src_by_keywords(self.keywords)
        return tags

    @property
    def root_initiators(self) -> list:
        direct_tags, root_init = self._root_initiators_direct()
        keyword_tags = self._root_initiators_keywords(root_init)
        all_tags = direct_tags | keyword_tags
        return list(all_tags)


def build_initiators(dirr, prefix, page_url=None, content_type=None) -> "Dict[str, Initiator]":
    """
    Build the full initiator tree for all resources
    """
    exclude_urls = ['about:blank']
    initiators = json.load(open(f'{dirr}/{prefix}_requestStacks.json'))
    textual_resources = json.load(open(f'{dirr}/{prefix}_textualResources.json'))
    fetches = {f['url']: f for f in json.load(open(f'{dirr}/{prefix}_fetches.json'))}
    def in_content_type(url):
        if url in exclude_urls:
            return False
        if content_type is None or url not in fetches:
            return True
        for ct in content_type:
            if ct in fetches[url]['mime']:
                return True
        return False
    initiator_map = {}
    for obj in initiators:
        for url in obj['urls']:
            if url in initiator_map:
                continue
            code = textual_resources.get(url)
            initiator_map[url] = Initiator(url, obj['stackInfo'], code)
    for url, initiator in initiator_map.items():
        if not in_content_type(url):
            continue
        for frames in initiator.stack:
            # # * Heutistic to decide if the URL is statically initated by HTML
            # if len(frames['callFrames']) == 1 and frames['callFrames'][0]['url'] in exclude_urls:
            #     continue
            for frame in frames['callFrames']:
                loc = (frame['lineNumber'], frame['columnNumber'])
                initiator_url = frame['url']
                if initiator_url not in initiator_map:
                    continue
                if initiator_url == url:
                    continue
                initiator.add_initiator(initiator_map[initiator_url], loc)
    return initiator_map

if __name__ == "__main__":
    hostname = 'stripe.com_04f8099205'
    ts = '202502020008'
    ts = 'nojs-0' #!
    prefix = f'record-{ts}'

    COLL = 'watradeoff'
    COLL = 'watradeoff_test' #!
    dirr = f'{CONFIG.archive_dir}/writes/{COLL}/{hostname}'
    metadata = json.load(open(f'{dirr}/metadata.json'))
    # TODO: This is for watradeoff_test only, later metadata has different structure
    # page_url = metadata['record'][ts]['url']
    page_url = metadata['record-js'][0]['url'] #!

    # missing_scripts = json.load(open(f'../measure/diffs/{COLL}/replay-202502020008_replay-static-202501200202-202502020008_missing_scripts.json'))
    missing_scripts = json.load(open(f'../measure/diffs/{COLL}/record-nojs-0_replay-archive-0_missing_scripts.json')) #!
    missing_scripts = [s for s in missing_scripts if s['hostname'] == hostname][0]
    scripts = [s['url'] for s in missing_scripts['failFetchScripts']]
    initiators = build_initiators(dirr, prefix, page_url)
    result = {script: initiators[script].root_initiators for script in scripts if script in initiators}
    json.dump(result, open('test_initiators.json', 'w'), indent=2)
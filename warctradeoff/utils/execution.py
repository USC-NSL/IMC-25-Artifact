"""Python library for parsing execution traces dumped by nodeJS"""
import json
import sys
import esprima
import re
import requests
from dataclasses import dataclass, asdict
from functools import cached_property, lru_cache
from bs4 import BeautifulSoup
from warctradeoff.config import CONFIG
from fidex.utils import url_utils, logger
import logging
sys.setrecursionlimit(3000)

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ALL_ASTS = {} # Cache for all the ASTs {url: ASTInfo}
ALL_SCRIPTS = {} # Cache for all the code {url: code}
DIRR = None

@dataclass
class ASTInfo:
    parser: "JSTextParser"
    asts: "dict[ASTNode]"
    text_matchers: "dict[TextMatcher]"

    def find_ast(self, pos):
        for (start, end), ast in self.asts.items():
            if start <= pos < end:
                return ast
        return None
    
    def add_ast(self, ast, start, end):
        self.asts[(start, end)] = ast
    
    def find_matcher(self, pos):
        for (start, end), matcher in self.text_matchers.items():
            if start <= pos < end:
                return matcher
        return None
    
    def add_matcher(self, matcher, start, end):
        self.text_matchers[(start, end)] = matcher


# Python implementation of js-parse for abling to multiprocess
class ASTNode:
    def __init__(self, node, info, scopes=None):
        self.node = node
        self.type = node.type
        self.start = node.range[0]
        self.end = node.range[1]
        self.start_rowcol = {'line': node.loc.start.line, 'column': node.loc.start.column}
        self.end_rowcol = {'line': node.loc.end.line, 'column': node.loc.end.column}
        self.info = info
        self.text = info.get('text', '')
        self.children = []
        self.parent = None
        self._hash = None
        self.scopes = [] if scopes is None else scopes.copy()
        self.keywords = {
            'window',
            'contentWindow',
            'postMessage',
            'document',
            'domain',
            'isSameNode',
            'call',
            'value',
        }
    
    def add_child(self, child):
        self.children.append(child)
        child.parent = self
    
    def find_path(self, pos):
        """
        Args:
            pos: int - position in the text
        """
        cur_node = self
        path = []
        found = True
        while found:
            found = False
            for idx, child in enumerate(cur_node.children):
                if child.start <= pos < child.end:
                    path.append({'idx': idx, 'node': child})
                    cur_node = child
                    found = True
                    break
        # TODO: Might need to handle IIFE cases here
        return path

    def find_pos(self, path):
        cur_node = self
        for step in path:
            # TODO: Might need to handle IIFE cases here
            cur_node = cur_node.children[step['idx']]
        return {'start': cur_node.start, 'end': cur_node.end}

    def find_child(self, pos) -> "ASTNode":
        path = self.find_path(pos)
        return path[-1]['node']
    
    def same_scope(self, other):
        if len(self.scopes) != len(other.scopes):
            return False
        for s1, s2 in zip(self.scopes, other.scopes):
            if s1.type != s2.type:
                return False
        return True
    
    @cached_property
    def within_loop(self):
        """Check if the node is within a loop"""
        cur_parent = self.parent
        while cur_parent:
            if cur_parent.type in ['ForStatement', 'WhileStatement', 'DoWhileStatement']:
                return True
            cur_parent = cur_parent.parent
        return False
    
    def after(self, other):
        def path_to_root(node):
            path = []
            cur, cur_parent = node, node.parent
            while cur_parent:
                idx = 0
                for idx, child in enumerate(cur_parent.children):
                    if child is cur:
                        break
                path.insert(0, idx)
                cur = cur.parent
                cur_parent = cur_parent.parent
            return path
        a_path_to_root = path_to_root(self)
        b_path_to_root = path_to_root(other)
        for i in range(min(len(a_path_to_root), len(b_path_to_root))):
            if a_path_to_root[i] != b_path_to_root[i]:
                return a_path_to_root[i] > b_path_to_root[i]
        return len(a_path_to_root) > len(b_path_to_root)

    def __str__(self):
        return f'type: {self.type} '           \
            #  + f'Info: {self.info}'            \
            #  + f'Start: {self.start_rowcol} '  \
            #  + f'End: {self.end_rowcol} '

    def __repr__(self):
        return self.__str__()
    
    def print_all(self, depth=0, index=0):
        print('--'*(depth+1), index, self)
        child_index = 0
        for child in self.children:
            child.print_all(depth+1, child_index)
            child_index += 1
    
    def filter_archive(self):
        # * First, strip all the headers and block added by rewriting tools
        if CONFIG.replayweb:
            actual_root = self.children[2]
            actual_root.children = actual_root.children[10:]
        else:
            actual_root = self.children[2].children[9]
        actual_root.parent = None
        
        # * Second, traverse through the tree and skip all the nodes that follows the rewriting pattern
        def skip_node(node, skip):
            node.parent.children = [skip if c is node else c for c in node.parent.children]
            skip.parent = node.parent
        def choose_skip_node(node):
            node.scopes = [node.scopes[0]] + node.scopes[3:]
            # * Skip "_____WB$wombat$check$this$function_____(this)"
            if node.type == 'CallExpression' \
               and node.text.startswith('_____WB$wombat$check$this$function_____') \
               and len(node.info['arguments']) and node.info['arguments'][0] == 'this':
                    skip_node(node, node.children[1])
            # * Skip ".__WB_pmw(self)" (CallExpression)
            if node.type == 'CallExpression' \
               and '__WB_pmw(self)' in node.text \
               and len(node.info['arguments']) and node.info['arguments'][0] == 'self':
                skip_node(node, node.children[0])
            # * Skip ".__WB_pmw(self)" (PropertyAccessExpression)
            if node.type == 'PropertyAccessExpression' \
               and node.info['property'] == '__WB_pmw':
                skip_node(node, node.children[0])
            if node.type == 'MemberExpression' \
                and node.info['property'] == '__WB_pmw':
                skip_node(node, node.children[0])
            for child in node.children:
                choose_skip_node(child)
        choose_skip_node(actual_root)
        
        return actual_root

    def __hash__(self) -> int:
        """Hash the node based on merkle tree method"""
        if self._hash:
            return self._hash
        child_hashes = hash(tuple(self.children))
        hash_list = [self.type]
        if self.type == 'Identifier':
            if self.node.name in self.keywords:
                hash_list.append(self.node.name)
        self_hash = hash(tuple(hash_list))
        self._hash = hash((self_hash, child_hashes))
        return self._hash

    def __iter__(self):
        """Iterate self and children"""
        yield self
        for child in self.children:
            yield from child
    
    @staticmethod
    def linecol_2_pos(line, col, text):
        """Transform line column to position"""
        lines = text.split('\n')
        pos = 0
        for i in range(len(lines)):
            if i == line:
                pos += col
                break
            pos += len(lines[i]) + 1
        return pos

    @staticmethod
    def pos_2_linecol(pos, text):
        """Transform position to line column"""
        lines = text.split('\n')
        line = 0
        for i in range(len(lines)):
            if pos < len(lines[i]):
                return (line, pos)
            pos -= len(lines[i]) + 1
            line += 1
        return (line, pos)


def filter_archive(text):
    replace_rules = {
            '_____WB$wombat$check$this$function_____(this)': 'this',
            '.__WB_pmw(self)': '',
            '.__WB_pmw': '',
            '__WB_pmw': '',
        }
    for key, value in replace_rules.items():
        text = text.replace(key, value)
    return text

class TextMatcher:
    """If ASTNode is not available, use this to match text"""
    def __init__(self, code):
        self.code = code
        self.is_archive = False
    
    def find_unique_text(self, pos):
        """Starting from the given position, keep expanding until a unique text is found"""
        t_len = 1
        while pos + t_len < len(self.code):
            text = self.code[pos:pos+t_len]
            matches = [m.start() for m in re.finditer(re.escape(text), self.code)]
            if len(matches) == 1:
                return filter_archive(text)
            t_len += 1
        t_len = 1
        while pos - t_len >= 0:
            text = self.code[pos-t_len:pos]
            matches = [m.start() for m in re.finditer(re.escape(text), self.code)]
            if len(matches) == 1:
                return filter_archive(text)
            t_len += 1
        # Non ideal, use the character at the position for now
        return self.code[pos]

    def within_loop(self, pos, scope_name):
        """Check if the position is within a loop"""
        loop_keywords = ['for', 'while']
        t_len = 1
        while pos - t_len >= 0:
            text = self.code[pos-t_len:pos]
            if scope_name and scope_name in text:
                return False
            for keyword in loop_keywords:
                if keyword in text:
                    return True
            t_len += 1
        return False
    
    def archive_pos_2_live(self, pos):
        """Convert archive position to live position"""
        # Assume the header added to the code is fixed
        line, col = ASTNode.pos_2_linecol(pos, self.code)
        lines = self.code.split('\n')
        if not CONFIG.replayweb:
            lines[14] = lines[14][1:]
        if line == 14:
            col -= 1
        new_pos = 0
        for i in range(14, line):
            new_pos += len(filter_archive(lines[i])) + 1
        final_line = filter_archive(lines[line][:col])
        new_pos += len(final_line)
        return new_pos

    def scope(self, pos) -> int:
        """Simply check the scope of the position"""
        right_bracket_offset = 0
        while pos < len(self.code):
            if self.code[pos] == '{':
                right_bracket_offset -= 1
            if self.code[pos] == '}':
                right_bracket_offset += 1
            pos += 1
        return max(0, right_bracket_offset - 2 * self.is_archive)
    
    def after(self, pos, other, other_pos):
        scope = self.scope(pos)
        other_scope = other.scope(other_pos)
        # * If A is top scope, B is not. Then B is always after A
        # * This is not true in general case, since there can be "func a() { ... } a(); b();" Then b() is after any within a()
        # * However, in the context when this is called, it is the case:
        # * 1. If there's some common frames ahead, no pos can be in the top scope
        # * 2. If there's no common frames ahead, then both frame are from bottom, then one not in top scope definitely after the other
        if scope > 0 and other_scope == 0:
            return True
        if self.is_archive:
            pos = self.archive_pos_2_live(pos)
        if other.is_archive:
            other_pos = other.archive_pos_2_live(other_pos)
        # Taking into consideration of some error in the position
        return pos >= other_pos - len('_____WB$wombat$check$this$function_____(this)')


class JSTextParser:
    def __init__(self, js_file, url=None):
        """
        Example usage:
          program = "document.documentElement.isSameNode(documentElement)"
          parser = JSTextParser(program)
          ast_node = parser.get_ast_node()
        """
        self.text = js_file
        self.url = url

    @lru_cache(maxsize=None)
    def parse_source(self, text):
        try:
            return esprima.parseScript(text, {'loc': True, 'range': True, 'tolerant': True})
        except Exception as e:
            logging.error(f"Error in parsing js: {e}")
            return None

    def get_text(self, start, end):
        return self.text[start:end]
    
    @lru_cache(maxsize=None)
    def get_program(self, loc):
        ext = url_utils.get_file_extension(self.url)
        if ext.lower() in ['.js']:
            return self.text
        html_tags = re.compile(r'</?([a-zA-Z]+)>')
        if not html_tags.search(self.text): # JS
            return self.text
        # If the text is HTML, then return the script part
        soup = BeautifulSoup(self.text, 'html.parser')
        scripts = soup.find_all('script')
        for script in scripts:
            script_str = script.get_text()
            start = self.text.find(script_str)
            end = start + len(script_str)
            if start <= loc < end:
                return script_str
        return self.text
    
    def get_program_range(self, loc):
        program = self.get_program(loc)
        start = self.text.find(program)
        return (start, start + len(program))
    
    def get_program_identifier(self, loc):
        """Get some sort of identifier for the program
        Return either "" for JS, or "script:N" for the Nth script in HTML
        Note that Archive: script:N == Original script:N+3
        """
        start, _ = self.get_program_range(loc)
        if start == 0:
            return ""
        soup = BeautifulSoup(self.text, 'html.parser')
        scripts = soup.find_all('script')
        idx = 0
        cur_start = 0
        for script in scripts:
            script_str = script.get_text() + '</script>'
            start = self.text[cur_start:].find(script_str)
            if start + cur_start <= loc:
                idx += 1
                cur_start += start
            else:
                break
        return f"script:{idx-1}"

    def range_from_identifier(self, identifier) -> (int, int):
        if not identifier:
            return 0, len(self.text)
        script_num = int(identifier.split(':')[-1])
        soup = BeautifulSoup(self.text, 'html.parser')
        scripts = soup.find_all('script')
        if script_num >= len(scripts):
            return 0, len(self.text)
        program = scripts[script_num].get_text()
        start = self.text.find(program)
        return start, start + len(program)

    def collect_node_info(self, node):
        full_text = self.get_text(node.range[0], node.range[1])
        info = {
            'text': full_text,
        }
        if node.type == 'CallExpression':
            info['arguments'] = []
            for arg in node.arguments:
                info['arguments'].append(self.get_text(arg.range[0], arg.range[1]))
        if node.type == 'PropertyAccessExpression':
            info['property'] = node.name
        if node.type == 'MemberExpression':
            info['property'] = node.property.name
        return info

    def is_node(self, node):
        return isinstance(node, esprima.nodes.Node)

    @lru_cache(maxsize=None)
    def get_ast_node(self, archive=False, pos: int=None):
        """If pos is set, the ast_node will be returned around that position if self.text is HTML"""
        program = self.get_program(pos) if pos else self.text
        parsed_source = self.parse_source(program)
        if not parsed_source:
            return None
        scopes = []
        def traverse_helper(node, depth=0):
            info = self.collect_node_info(node)
            ast_node = ASTNode(node, info, scopes)
            if ast_node.type in ['FunctionDeclaration',
                                 'FunctionExpression', 
                                 'BlockStatement',
                                 'ArrowFunctionExpression', 
                                 'Program',]:
                scopes.append(ast_node)
            for key, value in node.items():
                if key in ['type', 'range', 'loc']:
                    continue
                if not isinstance(value, list):
                    value = [value]
                for child in value:
                    if not self.is_node(child):
                        continue
                    child_node = traverse_helper(child, depth + 1)
                    ast_node.add_child(child_node)
            if len(scopes) and scopes[-1] == ast_node:
                scopes.pop()
            return ast_node

        source_ast_node = traverse_helper(parsed_source)
        if archive:
            source_ast_node = source_ast_node.filter_archive()
        return source_ast_node
    
    @lru_cache(maxsize=128)
    def get_text_matcher(self, pos=None):
        program = self.get_program(pos) if pos else self.text
        return TextMatcher(program)


class Frame:
    REPLAYWEB_DIR = None
    REPLAYWEB_SEEN_DIRS = set()

    def __init__(self, functionName: str, url: str, lineNumber: int, columnNumber: int):
        self.functionName = functionName
        self.url = url
        if not CONFIG.replayweb:
            self.url = url_utils.replace_archive_collection(url, CONFIG.collection)
            self.url = url_utils.replace_archive_host(self.url, CONFIG.host)
        self.lineNumber = lineNumber
        self.columnNumber = columnNumber

    def __hash__(self):
        return hash((self.url, self.lineNumber, self.columnNumber))
    
    def __eq__(self, other):
        return self.url == other.url and self.lineNumber == other.lineNumber and self.columnNumber == other.columnNumber

    @cached_property
    def code(self):
        return Frame.get_code(self.url)
    
    @cached_property
    def position(self):
        if self.code is None:
            return None
        return ASTNode.linecol_2_pos(self.lineNumber, self.columnNumber, self.code)
    
    @cached_property
    def relative_position(self):
        """Relative position to the actual JS code portion"""
        parser = self.get_ASTInfo().parser
        start, _ = parser.get_program_range(self.position)
        return self.position - start

    @staticmethod
    def get_code(url):
        # * replayweb logic
        if Frame.REPLAYWEB_DIR is not None:
            if Frame.REPLAYWEB_DIR not in Frame.REPLAYWEB_SEEN_DIRS:
                with open(f"{Frame.REPLAYWEB_DIR}/live_resources.json") as f:
                    d = json.load(f)
                    d = {url_utils.url_norm(u, trim_www=True, trim_slash=True): c for u, c in d.items()}
                ALL_SCRIPTS.update(d)
                with open(f"{Frame.REPLAYWEB_DIR}/archive_resources.json") as f:
                    d = json.load(f)
                    d = {url_utils.url_norm(u, trim_www=True, trim_slash=True): c for u, c in d.items()}
                ALL_SCRIPTS.update(d)
        # * pywb logic
        else:
            if url not in ALL_SCRIPTS:
                args = {}
                if url_utils.is_archive(url):
                    url = url_utils.replace_archive_host(url, CONFIG.host)
                else:
                    url = f'http://{CONFIG.host}/{CONFIG.collection}/{CONFIG.ts}id_/{url}'
                try:
                    response = requests.get(url, timeout=5)
                except Exception as e:
                    logging.error(f"Fail to fetch {url}: {e}")
                    return None
                ALL_SCRIPTS[url] = response.text
        if url in ALL_SCRIPTS:
            return ALL_SCRIPTS[url]
        url = url_utils.url_norm(url, trim_www=True, trim_slash=True)
        return ALL_SCRIPTS[url]

    def get_program_identifier(self):
        ast_info = self.get_ASTInfo()
        if ast_info.parser is None:
            return ""
        return ast_info.parser.get_program_identifier(self.position)

    def get_ASTInfo(self) -> ASTInfo:
        parser = None
        if self.url in ALL_ASTS:
            ast = ALL_ASTS[self.url].find_ast(self.position)
            matcher = ALL_ASTS[self.url].find_matcher(self.position)
            if ast or matcher:
                return ALL_ASTS[self.url]
        else:
            ALL_ASTS[self.url] = ASTInfo(parser=JSTextParser(self.code, self.url), asts={}, text_matchers={})
        try:
            parser = ALL_ASTS[self.url].parser
            start, end = parser.get_program_range(self.position)
            matcher = parser.get_text_matcher(self.position)
            matcher.is_archive = url_utils.is_archive(self.url)
            ALL_ASTS[self.url].add_matcher(matcher, start, end)
            ast_node = parser.get_ast_node(archive=url_utils.is_archive(self.url), pos=self.position)
            ALL_ASTS[self.url].add_ast(ast_node, start, end)
        except Exception as e:
            logging.error(f"Error in parsing {self.url}: {e}")
        return ALL_ASTS[self.url]

    @cached_property
    def associated_ast(self) -> "ASTNode | None":
        ast_info = self.get_ASTInfo()
        ast_node = ast_info.find_ast(self.position)
        if not ast_node:
            # logging.error(f"AST not found for {self.url}")
            return None
        node = ast_node.find_child(self.relative_position)
        return node
    
    @cached_property
    def text_matcher(self):
        ast_info = self.get_ASTInfo()
        matcher = ast_info.find_matcher(self.position)
        if not matcher:
            matcher = ast_info.parser.get_text_matcher(self.position)
            if url_utils.is_archive(self.url):
                matcher.is_archive = True
            ast_info.add_matcher(matcher, *ast_info.parser.get_program_range(self.position))
        return matcher

    @cached_property
    def ast_path(self) -> "list[dict]":
        assert self.associated_ast, f"AST not found for {self.url}"
        ast_info = self.get_ASTInfo()
        ast_node = ast_info.find_ast(self.position)
        path = ast_node.find_path(self.relative_position)
        return [{'idx': p['idx'], 'type': p['node'].type} for p in path]

    @cached_property
    def within_loop(self):
        if self.associated_ast:
            self.associated_ast.within_loop
        return self.text_matcher.within_loop(self.relative_position, self.functionName)

    def same_file(self, other: "Frame") -> bool:
        return self.url == other.url or url_utils.url_match(self.url, other.url)

    def same_frame(self, other: "Frame") -> bool:
        if self.functionName != other.functionName:
            return False
        if not self.same_file(other):
            return False
        if self.associated_ast and other.associated_ast:
            return self.ast_path == other.ast_path
        if self.code and other.code:
            if self.text_matcher.find_unique_text(self.relative_position) \
               == other.text_matcher.find_unique_text(other.relative_position):
                return True
        return False
    
    def same_scope(self, other: "Frame") -> bool:
        # Replayweb scoping currently have some problems on AST, direcly go to fallbacks
        if not CONFIG.replayweb and self.associated_ast and other.associated_ast:
            return self.associated_ast.same_scope(other.associated_ast)
        return self.functionName == other.functionName and url_utils.url_match(self.url, other.url)

    def after(self, other: "Frame") -> bool:
        if self.associated_ast and other.associated_ast:
            return self.associated_ast.after(other.associated_ast)
        self_code, other_code = Frame.get_code(self.url), Frame.get_code(other.url)
        if not self_code or not other_code:
            return False
        self_pos = ASTNode.linecol_2_pos(self.lineNumber, self.columnNumber, Frame.get_code(self.url))
        other_pos = ASTNode.linecol_2_pos(other.lineNumber, other.columnNumber, Frame.get_code(other.url))
        return self.text_matcher.after(self.relative_position, other.text_matcher, other.relative_position)


class Stack:
    def __init__(self, stack: list):
        """
        stack: 
          [
            {
              callFrame: [
                {
                  url: str,
                  functionName: str,
                  lineNumber: int (0-indexed),
                  columnNumber: int (0-indexed)
                }
              ],
              description: str
            }
          ]
        """
        self.stack = stack
    
    def __reduce__(self):
        return (Stack, (self.stack,))
    
    @cached_property
    def serialized(self) -> "list[list[Frame]]":
        all_frames = []
        for call_frames in self.stack:
            sync_frames = []
            call_frames = call_frames['callFrames']
            for frame in call_frames:
                if 'wombat.js' not in frame['url'] and frame['url'] != '':
                    sync_frames.append(Frame(frame['functionName'], frame['url'], frame['lineNumber'], frame['columnNumber']))
            all_frames.append(sync_frames)
        return all_frames

    @cached_property
    def serialized_flat_reverse(self) -> "list[Frame]":
        return list(reversed([frame for frames in self.serialized for frame in frames]))

    @cached_property
    def scripts(self) -> "set[str]":
        """
        Get the scripts that are related to this write
        """
        scripts = set()
        for call_frames in self.stack:
            call_frames = call_frames['callFrames']
            for frame in call_frames:
                if 'wombat.js' not in frame['url'] and frame['url'] != '':
                    scripts.add(frame['url'])
        return scripts

    def overlap(self, other: "Stack") -> list:
        """Return a list of common callframes between two stacks"""
        a_frames = self.serialized_flat_reverse
        b_frames = other.serialized_flat_reverse
        common_frames = []
        min_depth = min(len(a_frames), len(b_frames))
        for i in range(min_depth):
            if a_frames[i] == b_frames[i]:
                common_frames.append(a_frames[i])
            elif a_frames[i].same_frame(b_frames[i]):
                common_frames.append(a_frames[i])
            else:
                break
        return common_frames
    
    def rw_after(self, other: "Stack") -> bool:
        """Replayweb has some problems with tracking, use fallbacks"""
        for i in range(len(self.serialized_flat_reverse)):
            a_frame = self.serialized_flat_reverse[i]
            for j in range(len(other.serialized_flat_reverse)):
                b_frame = other.serialized_flat_reverse[j]
                if a_frame.after(b_frame):
                    return True
        return False

    def after(self, other: "Stack") -> bool:
        """Check if this stack is after the other stack"""
        common_frames = self.overlap(other)
        if len(common_frames) == 0:
            if len(self.serialized_flat_reverse) > 0 \
            and len(other.serialized_flat_reverse) > 0:
                if CONFIG.replayweb:
                    return self.rw_after(other)
                a_base = self.serialized_flat_reverse[0]
                b_base = other.serialized_flat_reverse[0]
                if not a_base.same_file(b_base):
                    return False
                return a_base.after(b_base)
            else:
                return False
        else:
            # * If the last common frame is within a loop, then with static analysis it is impossible to determine
            # * we always assume self is after 
            if self.serialized_flat_reverse[len(common_frames)-1].within_loop:
                return True
            a_divergent = self.serialized_flat_reverse[len(common_frames)]
            b_divergent = other.serialized_flat_reverse[len(common_frames)]
            location_after =  a_divergent.after(b_divergent)
            # logging.info(f"Comparing {a_divergent.lineNumber=} {a_divergent.columnNumber=} and {b_divergent.lineNumber=} {b_divergent.columnNumber=}")
            same_scope = a_divergent.same_scope(b_divergent)
            # logging.info(f'{location_after=} {same_scope=}')
            return location_after and same_scope
import json
import os, sys
import time
from functools import cached_property

_FILEDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(_FILEDIR))

class Config:
    def __init__(self, path):
        self.path = path
        self.config = json.load(open(path))
        self._collection = None
        self._replayweb = False
        self._separate_collection = None

    @cached_property
    def host(self):
        return self.config.get('host')

    @cached_property
    def host_proxy(self):
        return self.config.get('host_proxy')
    
    @cached_property
    def host_proxy_test(self):
        return self.config.get('host_proxy_test')

    @cached_property
    def host_proxy_patch(self):
        return self.config.get('host_proxy_patch')
    
    @cached_property
    def pywb_env(self):
        return self.config.get('pywb_env', ':')
    
    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.config.get('collection')
        return self._collection

    @collection.setter
    def collection(self, value):
        self._collection = value
    
    @property
    def replayweb(self):
        return self._replayweb
    
    @replayweb.setter
    def replayweb(self, value):
        self._replayweb = value
        if value == True:
            os.environ['REPLAYWEB'] = '1'
    
    @property
    def ts(self):
        """Return a 12-digit timestamp by YYYYMMDDHHMM"""
        return time.strftime('%Y%m%d%H%M')
    
    @property
    def chrome_data_dir(self):
        return self.config.get('chrome_data_dir', '.')
    
    @property
    def archive_dir(self):
        return self.config.get('archive_dir', '.')
    
    @property
    def separate_collection(self):
        return self._separate_collection

    @separate_collection.setter
    def separate_collection(self, value):
        self._separate_collection = value

config_path = os.path.join(_FILEDIR, 'config.json') if not os.environ.get('FIDEX_CONFIG') else os.environ.get('FIDEX_CONFIG')
CONFIG = Config(config_path)
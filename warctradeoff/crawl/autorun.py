"""
    Auto run record.js and replay.js
    If run on remote host with large scale, need to make sure that:
        - Crawls (warc) are uploaded and "wb-manager added" to the remote server
        - Screenshots are uploaded to the remote server
        - Writes are uploaded to the remote server
    If run with local host, need to make sure that:
        - This script is run with pywb venv on.
"""
from subprocess import PIPE, check_call, Popen, call
from urllib.parse import urlsplit, urlunsplit
from collections import defaultdict
import random
import os
import json
import sys
import re
import threading
import concurrent.futures
import time
import logging
import traceback
import glob

_FILEDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(_FILEDIR))
_CURDIR = os.getcwd()
from warctradeoff.crawl import warcprocess
from warctradeoff.utils import upload, url_utils, logger, common
from warctradeoff.config import CONFIG

REMOTE = False
HOST = f'http://{CONFIG.host}'
PROXYHOST = f'http://{CONFIG.host_proxy}'
PROXYHOST_PATCH = f'http://{CONFIG.host_proxy_patch}'
HOME = os.path.expanduser("~")
default_archive = 'test'
DEFAULTARGS = ['-w', '-s', '--scroll']
SPLIT_ARCHIVE = False

DEFAULT_CHROMEDATA = CONFIG.chrome_data_dir


def record(url, archive_name,
           chrome_data=DEFAULT_CHROMEDATA,
           write_path=f'{_CURDIR}/writes',
           download_path=None,
           archive_path='./',
           wr_archive=default_archive,
           filename=None, 
           arguments=None):
    filename = 'live' if filename is None else filename
    assert '_' not in filename, "Filename cannot contain underscore"
    if download_path is not None:
        arguments = arguments + ['--download', download_path]
    p = Popen(['node', 'record.js', '-d', f'{write_path}/{archive_name}',
                '-f', filename,
                '-a', wr_archive,
                '-c', chrome_data,
                *arguments,
                url], stdout=PIPE, cwd=_FILEDIR)
    ts = None
    while True:
        line = p.stdout.readline()
        if not line:
            break
        line = line.decode()
        if "recorded page" in line:
            info = re.sub(r'.*recorded page: ', '', line)
            info = json.loads(info)
            ts, url = info['ts'], info['url']
            break
    return ts, url

def replay(url, archive_name,
           chrome_data=DEFAULT_CHROMEDATA,
           write_path=f'{_CURDIR}/writes',
           proxy=False,
           filename=None,
           arguments=None):
    if filename is None:
        filename = 'proxy' if proxy else 'archive'
    assert '_' not in filename, "Filename cannot contain underscore"
    check_call(['node', 'replay.js', '-d', f'{write_path}/{archive_name}', 
                '-f', filename,
                '-c', chrome_data,
                *arguments,
                url], cwd=_FILEDIR)

def record_replay(url, archive_name,
                  file_suffix,
                  file_prefix=None,
                  chrome_data=DEFAULT_CHROMEDATA,
                  worker_id=None,
                  write_path=f'{_CURDIR}/writes',
                  upload_write_archive=None,
                  download_path=None,
                  archive_path='./',
                  wr_archive=default_archive, 
                  pw_archive=default_archive,
                  remote_host=REMOTE,
                  sshclient=None,
                  record_live=False,
                  replay_archive=False,
                  replay_archive_patch=False,
                  replay_ts=None,
                  patch_ts=None,
                  arguments=None):
    """
    Now record and replay should be totally separate process, although they're still in the same function
    The reason is that the js and nojs combination in the pywb might change. So it doesn't make sense to replay right after record
    Args:
        url: URL to record and replay
        archive_name: Name of the archive to be saved
        write_path: Path to save the writes (-w for record.js and replay.js)
        upload_write_archive (str | None): This is the archive name under writes/ to be uploaded. If None, will be pw_archive
        download_path: Path to save the downloads (-d for record.js and replay.js)
        archive_path: Path where the archive will be saved (where wb-manager and wayback is run)
        wr_archive: Name of the archive to save & export on webrecorder
        pw_archive: Name of the archive to import for warc on pywb
        remote_host: True if run on remote host, False if run on local host
        record_live: run record on the live
        replay_archive (bool | str): True if run with archive, False if not run with archive, str if run on specific proxyhost
        replay_archive_patch (bool): True if run with patch, False if not run with patch
        replay_ts: str: If replay is set, run the specific timestamp for replay
        patch_ts: str: If replay_archive_patch is set, run the specific timestamp for patch
    """
    if arguments is None:
        arguments = DEFAULTARGS
    if upload_write_archive is None:
        upload_write_archive = pw_archive
    # assert "--disable-javascript" not in arguments, "disable javascript should be handled by record_with_js and record_without_js"
    temp_client = False
    client = None
    wb_manager = upload.WBManager(split=SPLIT_ARCHIVE and (worker_id is not None), worker_id=worker_id)
    if remote_host:
        if sshclient is None:
            temp_client = True
        client = upload.SSHClientManager(wb_manager=wb_manager)
    else:
        client = upload.LocalUploadManager(wb_manager=wb_manager)
    # client.remove_write(f'{pw_archive}/{archive_name}')

    metadata = client.get_metadata(col_name=upload_write_archive, directory=archive_name)
    if download_path is None:
        download_path = f'{chrome_data}/Downloads'
    if record_live:
        file_prefix = file_prefix or 'record'
        filename = f'{file_prefix}-{file_suffix}'
        ts, record_url = record(url, archive_name, 
                                chrome_data=chrome_data, 
                                write_path=write_path, 
                                download_path=download_path, 
                                archive_path=archive_path, 
                                wr_archive=wr_archive, 
                                filename=filename,
                                arguments=arguments)
        # Logic still in testing
        record_success = ts is not None
        if record_success:
            metadata[file_prefix][file_suffix] = {
                'ts': ts,
                'url': record_url,
                'req_url': url
            }
            check_call(['mv', f'{download_path}/{wr_archive}.warc', f'{download_path}/{archive_name}_{file_suffix}.warc'], cwd=_FILEDIR)
            client.upload_warc(f'{download_path}/{archive_name}_{file_suffix}.warc', pw_archive, pw_archive , mv_only=True)
            

    if replay_archive or replay_archive_patch:
        assert replay_archive==False or replay_archive_patch==False, "Only one of replay_archive and replay_archive_patch can be True"
        replay_ts = replay_ts or file_suffix
        # * The function should take care of URL to be run on
        # record_url = metadata['record'].get(file_suffix, {}).get('url', url)
        record_url = url
        a_pw_archive = wb_manager.collection(pw_archive)
        file_prefix = file_prefix or 'replay'
        filename = f'{file_prefix}-{file_suffix}'
        if isinstance(replay_archive, str):
            PHOST = replay_archive
        elif isinstance(replay_archive_patch, str):
            PHOST = replay_archive_patch
        elif replay_archive == True:
            PHOST = PROXYHOST
        elif replay_archive_patch == True:
            PHOST = PROXYHOST_PATCH
        else:
            PHOST = PROXYHOST
        proxy_arguments = arguments + ['--proxy', PHOST, '--proxy-ts', replay_ts]
        if patch_ts is not None:
            assert replay_archive_patch, "patch_ts should only be used with replay_archive_patch"
            proxy_arguments += ['--patch-ts', patch_ts]
        replay(record_url, archive_name, 
                chrome_data=chrome_data,
                write_path=write_path, 
                filename=filename,
                arguments=proxy_arguments)
        # Logic still in testing
        metadata[file_prefix][file_suffix] = {
            'url': record_url,
            'proxy': PHOST,
            'archive': pw_archive,
            'sub_archive': a_pw_archive,
            'directory': archive_name,
        }
    
    # The metadata will also be merged and dump together later. Here just leave a copy at the directory
    if os.path.exists(f'{write_path}/{archive_name}'):
        json.dump(metadata, open(f'{write_path}/{archive_name}/metadata.json', 'w+'), indent=2)
    client.upload_write(f'{write_path}/{archive_name}', directory=upload_write_archive)
    if temp_client:
        sshclient.close()
    return metadata


def record_replay_all_urls(urls,
                           file_suffix,
                           file_prefix=None,
                           chrome_data=DEFAULT_CHROMEDATA,
                           worker_id=None,
                           write_path=f'{_CURDIR}/writes',
                           upload_write_archive=None,
                           download_path=None,
                           archive_path='./',
                           wr_archive=default_archive,
                           pw_archive=default_archive, 
                           remote_host=REMOTE,
                           record_live=False,
                           replay_archive=False,
                           replay_archive_patch=False,
                           replay_ts=None,
                           patch_ts=None,
                           arguments=None) -> set:
    if arguments is None:
        arguments = DEFAULTARGS
    finished_urls = set()
    
    for i, url in list(enumerate(urls)):
        logging.info(f"Start {i} {url}") if worker_id is None else logging.info(f"Start {worker_id} {i} {url}")
        try:
            req_url = url_utils.request_live_url(url)
        except:
            continue
        archive_name = url_utils.calc_hostname(req_url)
        try:
            url_metadata = record_replay(req_url, archive_name, 
                                    file_suffix,
                                    file_prefix=file_prefix,
                                    chrome_data=chrome_data,
                                    worker_id=worker_id,
                                    write_path=write_path, 
                                    upload_write_archive=upload_write_archive,
                                    download_path=download_path, 
                                    archive_path=archive_path,
                                    wr_archive=wr_archive, 
                                    pw_archive=pw_archive, 
                                    remote_host=remote_host, 
                                    record_live=record_live,
                                    replay_archive=replay_archive,
                                    replay_archive_patch=replay_archive_patch,
                                    replay_ts=replay_ts,
                                    patch_ts=patch_ts,
                                    arguments=arguments)
            logging.info(f"Finished {url}")
            if len(url_metadata) == 0:
                if worker_id is not None: # Only remove chrome_data in multiprocess mode, since there might something wrong with the chrome_data
                    call(['rm', '-rf', chrome_data])
                continue
        except Exception as e:
            logging.error(f"Issue when record_replay URL {url}: {str(e)} {traceback.format_exc()}")
            continue
        finished_urls.add(url)
    return finished_urls

def record_replay_all_urls_multi(urls, file_suffix, num_workers=8,
                                 file_prefix=None,
                                 chrome_data_dir=os.path.dirname(DEFAULT_CHROMEDATA),
                                 metadata='metadata/metadata',
                                 write_path=f'{_CURDIR}/writes',
                                 upload_write_archive=None,
                                 download_path=None,
                                 wr_archive=default_archive,
                                 pw_archive=default_archive,
                                 remote_host=REMOTE,
                                 record_live=False,
                                 replay_archive=False,
                                 replay_archive_patch=False,
                                 replay_ts=None,
                                 patch_ts=None,
                                 arguments=None,
                                 trials=1):
    """
    The  multi-threaded version of record_replay_all_urls
    Need to make sure that the chrome_data_dir is set up with base, since the workers will copy from base
    Base need to have the webrecorder extension installed. Adblock is optional but recommended.
    """
    if arguments is None:
        arguments = DEFAULTARGS
    num_workers = min(num_workers, len(urls))
    # random.shuffle(urls)
    active_ids = set()
    pywb_servers = []
    id_lock = threading.Lock()
    urls_remain, finished_urls = urls.copy(), set()

    def _get_worker_task():
        with id_lock:
            for i in range(num_workers):
                if i not in active_ids:
                    active_ids.add(i)
                    url = urls_remain.pop(0) if len(urls_remain) > 0 else None
                    return i, url
        return None, None
    
    def _start_pywb_servers():
        for i in range(num_workers):
            wb_manager = upload.WBManager(split=SPLIT_ARCHIVE, worker_id=i)
            pywb_server = upload.PYWBServer(archive=wb_manager.collection(pw_archive), proxy=True)
            if replay_archive or replay_archive_patch:
                pywb_server.start()
            pywb_servers.append(pywb_server)
    _start_pywb_servers()

    def _replace_port(url, port):
            us = urlsplit(url)
            hostname = us.hostname.split(':')[0]
            us = us._replace(netloc=f'{hostname}:{port}')
            return urlunsplit(us)

    def record_replay_worker(url, 
                             file_suffix,
                             file_prefix,
                             chrome_data,
                             worker_id,
                             write_path,
                             upload_write_archive,
                             download_path,
                             wr_archive,
                             pw_archive, 
                             remote_host,
                             record_live,
                             replay_archive,
                             replay_archive_patch,
                             replay_ts,
                             patch_ts,
                             arguments):
        pywb_server = pywb_servers[worker_id]
        if CONFIG.separate_collection:
            coll_name = url_utils.calc_hostname(url)
            coll_name = upload.BaseManager.escape(f'{pw_archive}_{coll_name}')
            pywb_server.restart(coll_name)
        if replay_archive:
            replay_archive = _replace_port(PROXYHOST, pywb_server.port)
        elif replay_archive_patch:
            replay_archive_patch = _replace_port(PROXYHOST_PATCH, pywb_server.port)
        if not os.path.exists(chrome_data):
            # call(['cp', '--reflink=auto', '-r', f'{chrome_data_dir}/base', chrome_data])
            call(['cp', '-r', f'{chrome_data_dir}/base', chrome_data])
            time.sleep(worker_id*5)
        logging.info(f"Start {worker_id} {url}")
        succeed_url = record_replay_all_urls([url],
                               file_suffix,
                               file_prefix=file_prefix,
                               chrome_data=chrome_data,
                               worker_id=worker_id,
                               write_path=write_path,
                               upload_write_archive=upload_write_archive,
                               download_path=download_path,
                               wr_archive=wr_archive,
                               pw_archive=pw_archive, 
                               remote_host=remote_host,
                               record_live=record_live,
                               replay_archive=replay_archive,
                               replay_archive_patch=replay_archive_patch,
                               replay_ts=replay_ts,
                               patch_ts=patch_ts,
                               arguments=arguments)
        finished_urls.update(succeed_url)
        with id_lock:
            active_ids.remove(worker_id)
            
    for _ in range(trials):
        urls_remain = [url for url in urls if url not in finished_urls]
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            for i in range(num_workers):
                call(['rm', '-rf', f'{chrome_data_dir}/record_replay_{common.get_hostname()}_{i}'])
            # Keep track of futures
            tasks = []
            while True:
                # Get worker id
                sleep_time = 1
                while True:
                    worker_id, url = _get_worker_task()
                    if worker_id is not None:
                        break
                    else:
                        sleep_time = min(sleep_time * 2, 30)
                        time.sleep(sleep_time)
                assert worker_id is not None, "Worker ID is None"
                if url:
                    # Submit the worker thread to the pool
                    task = executor.submit(record_replay_worker, 
                                            url=url,
                                            file_suffix=file_suffix,
                                            file_prefix=file_prefix,
                                            chrome_data=f'{chrome_data_dir}/record_replay_{common.get_hostname()}_{worker_id}',
                                            worker_id=worker_id,
                                            write_path=write_path,
                                            upload_write_archive=upload_write_archive,
                                            download_path=download_path,
                                            wr_archive=wr_archive,
                                            pw_archive=pw_archive,
                                            remote_host=remote_host,
                                            record_live=record_live,
                                            replay_archive=replay_archive,
                                            replay_archive_patch=replay_archive_patch,
                                            replay_ts=replay_ts,
                                            patch_ts=patch_ts,
                                            arguments=arguments)
                    tasks.append(task)
                else:
                    # Exit the loop if no more urls
                    break
                # Check for any completed threads
                for task in tasks:
                    if task.done():
                        tasks.remove(task)
                # Exit the loop if all tasks are done
                if len(tasks) == 0 and len(active_ids) == 0:
                    break
    
    if replay_archive or replay_archive_patch:
        return []
    # Add metadata files
    if os.path.exists(f'{metadata}.json'):
        metadata_data = json.load(open(f'{metadata}.json', 'r'))
    else:
        metadata_data = []
    metadata_data.append({'suffix': file_suffix})
    json.dump(metadata_data, open(f'{metadata}.json', 'w+'), indent=2)
    return metadata_data
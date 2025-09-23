import json
import os
import logging
import traceback
from concurrent import futures
from subprocess import call

from warctradeoff.crawl import autorun
from warctradeoff.utils import upload, common, diff_utils
from warctradeoff.config import CONFIG
from warctradeoff.tests import test_patch
from warctradeoff.fidelity_check import layout_tree_patch
from fidex.fidelity_check import fidelity_detect

arguments = ['-s', '--scroll', '-t', '-w', '-e', '--headless', '-i']
chrome_data_dir = CONFIG.chrome_data_dir
client = upload.LocalUploadManager()

def fidelity_issue_wrapper(idx, dirr, left_prefix='live', right_prefix='archive', screenshot=False, more_errs=False, html_text=False, meaningful=True):
    """Check if all the data is available and then run the fidelity check"""
    logging.info(f"Processing {idx} {dirr}")
    if not os.path.exists(f'{dirr}/{left_prefix}_done'):
        return None
    if not os.path.exists(f'{dirr}/{right_prefix}_done'):
        return None
    
    try:
        return fidelity_detect.fidelity_issue_all(dirr, left_prefix=left_prefix, 
                                                        right_prefix=right_prefix,
                                                        screenshot=screenshot,
                                                        more_errs=more_errs,
                                                        html_text=html_text, 
                                                        meaningful=meaningful,
                                                        need_exist=False)
    except Exception as e:
        logging.error(f"Error in {idx} {dirr}: {e}")
        logging.error(traceback.format_exc())
        return None

def test_patch_e2e():
    call('rm testsets/warcs/*.patched.warc', shell=True)    
    d_ts = '202501200202'
    s_ts = '202502020008'
    LEFT, RIGHT = f'replay-{s_ts}', f'replay-patch-{d_ts}-{s_ts}'
    test_hostname = [
        # 'irwinnaturals.com_2fa7d40cb3',
        
        'www.yba.ne.jp_aef97df324',
        'www.gsjournal.net_15e9cb5c29',
        'www.oprahdaily.com_9c10174bcc',
        'instectelecom.com_a4ad29caeb',
        'www.ayvens.com_608058acaf',
        'bohemianlivemusic.org_8e8271f73d',
        'bumble.com_581aa806e4',
        'ridewithvia.com_15da6819f1',
        'www.gopenske.com_9d9dd70336',
        'clerk.com_92fba42070',
        'www.packoplock.se_8c7cde3fa8', # Extra interactions
        'www.experian.in_ed3f9a365f', # pywb fuzzy match
        'planetozh.com_d0c2457630', # pywb fuzzy match 2
        'www.kondice.cz_88506678ee', # adding pywb_ts causing problem
        'hjlawfirm.com_f79c9700c2', # adding pywb_ts causing problem 2
        'www.seagm.com_933c206f02', # Unclear, but likely related to iframe creation from inlined script tag        
        'corredorrojo.pe_2ce259ca84', # adding pywb_ts causing problem 3
        'www.atitesting.com_0ec30fc3f4', # adding pywb_ts causing problem 4
        'www.pcmag.com_e92d30a6c2', # Differnt order to insert
        'forms.app_a0d0409aa6', # Suspect to be <link> not patched
        'aevt.org_55b63a37d7', # <form> tag additionally closed by bs4

        # Fidelity detection issues
        'brain-market.com_73914f0a3d', # Seen pywb connection error causing problems
        'www.thamesandhudsonusa.com_7620aaa0ab',
        'fivespark.com_b3a034479b',
        'www.unsj.edu.ar_1f3f9e87ca',
        'mycharisma.com_c73c93ebd1', # extraInteraction
        'mediamonkey.io_df52e10641', # dimension miss-match
        'us.betway.com_bd4b8e423d', # Interaction miss-match
        'vbr-app.com_d7e4566d87', # Timing issue
        'texascapitalbank.com_a37090b125',

        # Invalid tags in original HTML
        'edinoepole.ru_2576841aaa',
        'rascal.co.jp_26773883b0',

        # * To check for resolve

        # ! Unresolved
        'www.evertonfc.com_b53336864d', 
        'www.travellocal.com_32113a4374', # Patch will also patch the old wrong thing
    ]

    # * Prepare tests
    call(f'rm -rf {CONFIG.archive_dir}/writes/test/', shell=True)
    call(f'mkdir -p {CONFIG.archive_dir}/writes/test/', shell=True)
    tests, warcs = [], {}
    for hostname in test_hostname:
        logging.info(f"Patching {hostname}")
        test_patch.run_patch(hostname, d_ts, s_ts)
        call(f'cp -r testsets/writes/{hostname} {CONFIG.archive_dir}/writes/test/', shell=True)
        warcs[hostname] = [f'testsets/warcs/{hostname}_{s_ts}.static.patched.warc',
                            f'testsets/warcs/{hostname}_{d_ts}.warc']
        metadata = json.load(open(f'testsets/writes/{hostname}/metadata.json', 'r'))
        url = metadata['replay'][s_ts]['url']
        tests.append({
            'hostname': hostname,
            'url': url
        })
    client.remove_archive('test')
    client.upload_warcs_to_archive(warcs, col_name='test')
    print("Testing", json.dumps(tests, indent=2), flush=True)
    
    # * Run crawl
    urls = [t['url'] for t in tests]
    autorun.record_replay_all_urls_multi(urls, s_ts, 8,
                                        file_prefix=f'replay-patch-{d_ts}',
                                        chrome_data_dir=chrome_data_dir,
                                        pw_archive='test',
                                        upload_write_archive='test',
                                        record_live=False,
                                        replay_archive=False,
                                        replay_archive_patch=True,
                                        replay_ts=s_ts,
                                        patch_ts=d_ts,
                                        arguments=arguments,
                                        trials=1)
    
    # * Fidelity check
    diffed = []
    counter = 0
    with futures.ProcessPoolExecutor(8) as executor:
        rs = []
        writes_dir = f'{CONFIG.archive_dir}/writes/test'
        for test in tests:
            hostname = test['hostname']
            rs.append(executor.submit(fidelity_issue_wrapper, counter, f'{writes_dir}/{hostname}', 
                                      LEFT, RIGHT, True, False, False, True))
            counter += 1
        while len(rs):
            for finished in futures.as_completed(rs):
                r = finished.result()
                rs.remove(finished)
                if r is None:
                    continue
                diffed.append(r)
                logging.info(f"Processed {len(diffed)}")
                
    # * Get scores
    scores = {}
    DIFF_STATIC = f'replay-{s_ts}_replay-static-{d_ts}-{s_ts}'
    DIFF_PATCH = f'replay-{s_ts}_replay-patch-{d_ts}-{s_ts}'
    for diff in diffed:
        hostname = diff.info['hostname'].split('/')[-1]
        dirr = f'{CONFIG.archive_dir}/writes/test/{hostname}'
        diff_eliminated = diff_utils.diff_eliminated(dirr, DIFF_STATIC, DIFF_PATCH)
        scores[hostname] = diff_eliminated
    print(json.dumps(scores, indent=2), flush=True)


test_patch_e2e()
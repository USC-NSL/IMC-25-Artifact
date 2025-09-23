import json
import time
import logging
from bs4 import BeautifulSoup
from subprocess import call

from warctradeoff.patch import parse, initiator, patch
from warctradeoff.patch import match as patch_match

TESTS = json.load(open('test_patch.json')) # Used to store long string for testing
logging.getLogger().setLevel(logging.DEBUG)

def check_tag_str(tag, expected):
    expected = BeautifulSoup(expected, 'html.parser').find()
    assert str(tag) == str(expected), f"Expected {expected} but got {tag}"

def test_add_ts():
    html = """<script src='http://example.com'></script>"""
    tag = BeautifulSoup(html, 'html.parser').find()
    tag = patch_match.add_ts(tag, '20250218')
    check_tag_str(tag, """<script src='http://example.com?pywb_ts=20250218'></script>""")

    html = """<script>s=document.createElement('script'); s.setAttribute('src', 'http://example.com')</script>"""
    tag = BeautifulSoup(html, 'html.parser').find()
    tag = patch_match.add_ts(tag, '20250218')
    check_tag_str(tag, """<script>s=document.createElement('script'); s.setAttribute('src', 'http://example.com?pywb_ts=20250218')</script>""")

    print("test_add_ts passed!")


def check_tag_loc(html, loc, expected=None):
    s = parse.HTMLParser(html)
    src_tag = s.tag_by_loc(loc)
    if expected is None:
        return
    assert src_tag == expected, f"Expected {expected} but got {src_tag}"

def test_find_minial_tag():

    html = """<div>
    <script></script>
</div>"""
    loc = (1, 12)
    check_tag_loc(html, loc, '<script></script>')

    html = """<div>
    <script>1</script>
</div>"""
    loc = (1, 12)
    check_tag_loc(html, loc, '<script>1</script>')

    html = """<div>
    <script> if 1<a<0: pass </script>
</div>"""
    loc = (1, 18)
    check_tag_loc(html, loc, '<script> if 1<a<0: pass </script>')

    html = """<div>
    <script><img src=123/></script>
</div>"""
    loc = (1, 21)
    check_tag_loc(html, loc, '<img src=123/>')

    html = """<div>
    <script src=123></script>
</div>"""
    loc = (1, 17)
    check_tag_loc(html, loc, '<script src=123></script>')

    html = """<div>
    <!-- <script>1</script> -->
    <script>2</script>
</div>
"""
    loc = (2, 12)
    check_tag_loc(html, loc, '<script>2</script>')

    # Incorrect html
    html = """<div>
    <!-- <script>1</script> -->
    <script>2
</div>
"""
    loc = (2, 12)
    check_tag_loc(html, loc, '<script>2\n')

    html = """<div>
    <script><q.length;++u/>1</script>
</div>
"""
    loc = (1, 15)
    check_tag_loc(html, loc, '<script><q.length;++u/>1</script>')

    print("test_find_minial_tag passed!")


def test_find_minimal_tag_real():
    html = open('testsets/minimal_tag.html').read()
    # loc is 0-indexed
    loc = (829, 95)
    check_tag_loc(html, loc, '<script async src="https://static.klaviyo.com/onsite/js/VVDrY9/klaviyo.js?company_id=VVDrY9"></script>')

    html = open('testsets/minimal_tag_2.html').read()
    loc = (19, 19)
    check_tag_loc(html, loc, """<meta
  name="sentry-config"
  data-js-dsn="https://7cd38b0eb2b348b39a6002cc768f91c7@errors.stripe.com/376"
  data-js-release="0ebff19124c4b88e3f3bfab26d1d76a6e785570c"
  data-js-environment="production"
  data-js-project="mkt"
>""")
    loc = (366, 4)
    check_tag_loc(html, loc)

    html = open('testsets/minimal_tag_3.html').read()
    loc = (2, 32)
    expected = '\n'.join(html.split('\n')[2:-2])
    check_tag_loc(html, loc, expected)

    print("test_final_minimal_tag_real passed!")


def test_initiators():
    hostname = 'stripe.com_04f8099205'
    prefix = f'record'
    suffix = 'nojs-0'
    dirr = f'testsets/writes/{hostname}'
    metadata = json.load(open(f'{dirr}/metadata.json'))
    page_url = metadata[prefix][suffix]['url']
    initiators = initiator.build_initiators(dirr, f'{prefix}-{suffix}', page_url)
    test_urls = {
        'https://b.stripecdn.com/mkt-statics-srv/assets/SiteHeader-UIT35Z2N.js': 2
    }
    for url, num_deps in test_urls.items():
        assert len(initiators[url].root_initiators) == num_deps, f"Different number of deps for {url}, {num_deps} != {len(initiators[url].root_initiators)}"

    print("test_initiators passed!")


def test_tag_match():
    def matched_tag_tojson(matched_tags):
        result = []
        for left, right in matched_tags:
            result.append({
                'left': [str(l)[:100] for l in left.tags],
                'right': [str(r)[:100] for r in right.tags]
            })
        json.dump(result, open('errors.json', 'w'), indent=4)

    def check_matched_tag(hostname, prefix, suffix_0, suffix_1, tag_0, tag_1):
        dirr = f'testsets/writes/{hostname}'
        metadata = json.load(open(f'{dirr}/metadata.json'))
        page_url_0 = metadata[prefix][suffix_0]['url']
        page_html_0 = json.load(open(f'{dirr}/{prefix}-{suffix_0}_textualResources.json'))[page_url_0]
        parser_0 = parse.HTMLParser(page_html_0)
        page_url_1 = metadata[prefix][suffix_1]['url']
        page_html_1 = json.load(open(f'{dirr}/{prefix}-{suffix_1}_textualResources.json'))[page_url_1]
        parser_1 = parse.HTMLParser(page_html_1)
        
        # with open('testsets/tag_matcher_4_0.html', 'w') as f1, open('testsets/tag_matcher_4_1.html', 'w') as f2:
        #     f1.write(page_html_0)
        #     f2.write(page_html_1)
        tag_matches = patch_match.match_tag_list(parser_0, parser_1)
        matched_tag = None
        for left, right in tag_matches:
            if left.contains(tag_0):
                matched_tag = right
                break
        if matched_tag is None:
            raise ValueError(f"Tag {tag_0} not found in {hostname} {suffix_1}")
        try:
            assert str(matched_tag) == str(tag_1), f"Expected {str(tag_1)[:200]} but got {str(matched_tag)[:200]}"
        except AssertionError as e:
            matched_tag_tojson(tag_matches)
            raise e
        print(f"test_tag_match on {hostname} passed!")

    check_matched_tag(hostname='stripe.com_04f8099205', 
                      prefix='record', 
                      suffix_0='js-0', 
                      suffix_1='nojs-0',
                      tag_0='<script type="module" src="https://b.stripecdn.com/mkt-statics-srv/assets/Bootstrapper-BOTW2RVE.js"></script>',
                      tag_1='<script type="module" src="https://b.stripecdn.com/mkt-statics-srv/assets/Bootstrapper-GSHVTVNA.js"></script>')

    tag_0 = """
        <script type="application/json" data-js-script-registry>
          [{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/SiteHeader-F6U6U5OG.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/VariantMobileMenu-2Z3ZZEO2.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/VariantSiteProductsNavCollapsedItem-4WC5DWBD.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/SiteResourcesNav-UQJNLXL3.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/HorizontalOverflowContainer-3PSOWLGU.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/CustomerProfile-VGXKZW2O.js"},{"critical":false,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/PricingIcon-EAOQUPGE.js"},{"critical":false,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/CodeFilesIcon-EJCYKMNY.js"},{"critical":false,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/LocaleControl-LRMAST4I.js"},{"critical":false,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/SiteFooterSectionSupportLinkList-G6SLPJCQ.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/Page-NUCWOGOV.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/Sentry-HGAMTSP3.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/EnforceSameSiteLaxOnCookies-TXKH4LE5.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/LoaderScript-K2AHPWAC.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/Loader-MSH7LDRL.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/ScrollDepthTracker-JFOKHML7.js"}]
        </script>"""
    tag_1 = """<script type="application/json" data-js-script-registry>
          [{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/SiteHeader-UIT35Z2N.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/VariantMobileMenu-EWPNZHT6.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/VariantSiteProductsNavCollapsedItem-OU2XQTWG.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/SiteResourcesNav-ILXSNQCK.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/HorizontalOverflowContainer-MRTAHEGS.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/CustomerProfile-Q24A63WU.js"},{"critical":false,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/PricingIcon-VR4YNZXV.js"},{"critical":false,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/CodeFilesIcon-6X3OL7RR.js"},{"critical":false,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/LocaleControl-RM6RYOEP.js"},{"critical":false,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/SiteFooterSectionSupportLinkList-DBBCVESA.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/Page-QGDOY26Y.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/Sentry-HGAMTSP3.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/EnforceSameSiteLaxOnCookies-TXKH4LE5.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/LoaderScript-POYKGSWQ.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/Loader-WB2SOMXX.js"},{"critical":true,"path":"https://b.stripecdn.com/mkt-statics-srv/assets/ScrollDepthTracker-RTFIQXF2.js"}]
        </script>"""

    check_matched_tag(hostname='stripe.com_04f8099205', 
                      prefix='record', 
                      suffix_0='js-0', 
                      suffix_1='nojs-0',
                      tag_0=tag_0,
                      tag_1=tag_1)

    tag_0 = TESTS['tag_match']['atxtoday.6amcity.com_91d7644c92'][0]["tag_0"]
    tag_1 = TESTS['tag_match']['atxtoday.6amcity.com_91d7644c92'][0]["tag_1"]
    check_matched_tag(hostname='atxtoday.6amcity.com_91d7644c92', 
                      prefix='record', 
                      suffix_0='js-0', 
                      suffix_1='nojs-0',
                      tag_0=tag_0,
                      tag_1=tag_0)

    tag_0 = TESTS['tag_match']['www.team-cymru.com_f49a1239f1'][0]["tag_0"]
    tag_1 = TESTS['tag_match']['www.team-cymru.com_f49a1239f1'][0]["tag_1"]
    check_matched_tag(hostname='www.team-cymru.com_f49a1239f1', 
                      prefix='record', 
                      suffix_0='js-0', 
                      suffix_1='nojs-0',
                      tag_0=tag_0,
                      tag_1=tag_1)

    tag_0 = TESTS['tag_match']['www.gmt-tokyo.com_d3606b7392'][0]["tag_0"]
    tag_1 = TESTS['tag_match']['www.gmt-tokyo.com_d3606b7392'][0]["tag_1"]
    check_matched_tag(hostname='www.gmt-tokyo.com_d3606b7392', 
                      prefix='record', 
                      suffix_0='js-0', 
                      suffix_1='nojs-0',
                      tag_0=tag_0,
                      tag_1=tag_1)

def run_patch(hostname, dynamic_suffix, static_suffix):
    start = time.time()
    patcher = patch.Patcher(
        dynamic_prefix=f'testsets/writes/{hostname}/record-{dynamic_suffix}',
        dynamic_warc=f'testsets/warcs/{hostname}_{dynamic_suffix}.warc',
        static_prefix=f'testsets/writes/{hostname}/record-{static_suffix}',
        static_warc=f'testsets/warcs/{hostname}_{static_suffix}.static.warc'
    )
    print(f"Patch init time: {time.time()-start}")
    try:
        patcher.build_initiators()
        print(f"Build initiators time: {time.time()-start}")
        patcher.patch()
        print(f"Patch time: {time.time()-start}")
    except Exception as e:
        with open('error.html', 'w+') as f:
            f.write(patcher.d_html)
        raise e

def test_patch_e2e():
    call('rm testsets/warcs/*.static.patched.warc', shell=True)    

    hostname = 'stripe.com_04f8099205'
    d_suffix = 'js-0'
    s_suffix = 'nojs-0'
    run_patch(hostname, d_suffix, s_suffix)

    hostname = 'atxtoday.6amcity.com_91d7644c92'
    d_suffix = 'js-0'
    s_suffix = 'nojs-0'
    run_patch(hostname, d_suffix, s_suffix)

    # * URL percent-encoded in the warc
    hostname = 'www.gsjournal.net_15e9cb5c29'
    d_suffix = '202501200202'
    s_suffix = '202502020008'
    run_patch(hostname, d_suffix, s_suffix)

    # * Mime plain for js
    hostname = 'irwinnaturals.com_2fa7d40cb3'
    d_suffix = '202501200202'
    s_suffix = '202502020008'
    run_patch(hostname, d_suffix, s_suffix)

    # * pywb_ts added to relative path in json leading to issue
    hostname = 'www.oprahdaily.com_9c10174bcc'
    d_suffix = '202501200202'
    s_suffix = '202502020008'
    run_patch(hostname, d_suffix, s_suffix)

    # * pywb_ts added to the base URL
    hostname = 'instectelecom.com_a4ad29caeb'
    d_suffix = '202501200202'
    s_suffix = '202502020008'
    run_patch(hostname, d_suffix, s_suffix)

    # * 1. keyword matches in comment tags
    # * 2. pywb_ts added to double-slash begingning URL
    hostname = 'www.yba.ne.jp_aef97df324'
    d_suffix = '202501200202'
    s_suffix = '202502020008'
    run_patch(hostname, d_suffix, s_suffix)

    # * pywb_ts added to URL encoded in JSON
    hostname = 'www.travellocal.com_32113a4374'
    d_suffix = '202501200202'
    s_suffix = '202502020008'
    run_patch(hostname, d_suffix, s_suffix)

    # * Nonce replaced, leading to CSP block
    hostname = 'www.ayvens.com_608058acaf'
    d_suffix = '202501200202'
    s_suffix = '202502020008'
    run_patch(hostname, d_suffix, s_suffix)

    # * ts should be override as dynamic ts
    hostname = 'bohemianlivemusic.org_8e8271f73d'
    d_suffix = '202501200202'
    s_suffix = '202502020008'
    run_patch(hostname, d_suffix, s_suffix)

    # * 
    hostname = 'clerk.com_92fba42070'
    d_suffix = '202501200202'
    s_suffix = '202502020008'
    run_patch(hostname, d_suffix, s_suffix)

if __name__ == '__main__':
    # test_add_ts()
    # test_find_minial_tag()
    # test_find_minimal_tag_real()
    # test_initiators()
    # test_tag_match()
    test_patch_e2e()
#!/usr/bin/env python3
from __future__ import print_function
from pydoc import describe
import threading
import requests
import argparse
import random
import time
import gzip
import sys
import re
import io
import os

from pprint import pprint
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

parser = argparse.ArgumentParser(
    description=
    '''Python cache warming tool used for warming full page cache solutions by visting pages in sitemap.xml''',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
required = parser.add_argument_group('required arguments')

optional = parser.add_argument_group('optional arguments')
optional.add_argument('--sitemap',
                        dest='sitemap',
                        action='store',
                        default=None,
                        required='--site' not in sys.argv,
                        metavar='url',
                        help='Url to sitemap, exclusive to --site.')
optional.add_argument('--site',
                        dest='site',
                        action='store',
                        default=None,
                        required='--sitemap' not in sys.argv,
                        metavar='url',
                        help='Url to site, exclusive to --sitemap.')
optional.add_argument('--delay',
                        dest='delay',
                        action='store',
                        default=0,
                        metavar='int',
                        help='Delay in seconds between url warming.')
optional.add_argument('--limit',
                        dest='limit',
                        action='store',
                        default=0,
                        metavar='int',
                        help='Number limit of urls to scan.')
optional.add_argument('--threads',
                        dest='threads',
                        action='store',
                        default=1,
                        metavar='int',
                        help='Number of concurrent threads to use.')
optional.add_argument('--timeout',
                        dest='timeout',
                        action='store',
                        default=10,
                        metavar='int',
                        help='Timeout limit for requests.')
optional.add_argument('--username',
                        dest='username',
                        action='store',
                        default=None,
                        required='--password' in sys.argv,
                        metavar='email',
                        help='Login username.')
optional.add_argument('--password',
                        dest='password',
                        action='store',
                        default=None,
                        required='--username' in sys.argv,
                        metavar='password',
                        help='Login password.')
optional.add_argument('--header', '-H', dest='headers', action='append', default=[], help='Additional headers - additive')
optional.add_argument('-r', dest='random', action='store_true', default=False, help='Randomize order of url warming.')
optional.add_argument('-v',
                        dest='verbose',
                        action='store_true',
                        default=False,
                        help='Run in verbose mode. Will print output to terminal.')
optional.add_argument('-s',
                        dest='silent',
                        action='store_true',
                        default=False,
                        help='Run in silent mode. Redirects all output to /dev/null.')

args = parser.parse_args()


class CacheWarmer:
    MAX_TEST_URL = 10
    no_urls = 0
    url_err = []
    site_urls = []
    load_times = []
    progress = 0
    thread_kill = False
    total_download_time = 0

    def __init__(
        self,
        sitemap_url='',
        site=None,
        delay=0,
        limit=None,
        threads=None,
        timeout=0,
        username=None,
        password=None,
        headers=None,
        random=False,
        verbose=False,
        silent=False,
    ):
        self.sitemap_url = sitemap_url
        self.site = site
        self.delay = delay
        self.limit = limit
        self.threads = threads
        self.timeout = timeout
        self.username = username
        self.password = password
        self.headers = headers
        self.random = random
        self.verbose = verbose
        self.silent = silent

        url_pieces = urlsplit(site or sitemap_url)
        self.scheme = url_pieces.scheme
        self.hostname = url_pieces.hostname
        self.base_url = '{}://{}/'.format(self.scheme, self.hostname)

        self.reqs = requests.Session()

    def run(self):
        """
        Main function
        :return: bool
        """

        sitemap_content = ''

        if self.silent is True:
            sys.stdout = os.devnull
            sys.stderr = os.devnull

        if None not in {self.username, self.password}:
            self._login()

        if self.sitemap_url:
            print('Downloading sitemap')
            sitemap = self._download_link(self.sitemap_url)
            if sitemap['code'] is 0:
                sitemap_content = sitemap['content']

        if self.site:
            print('Running in detect mode. Locating sitemaps')
            sitemap_content = self._assemble_multiple_sitemap(self._locate_sitemaps())

        print('Parsing sitemap')

        url_array = self._parse_sitemap(sitemap_content)

        if self.random is True:
            random.shuffle(url_array)

        if self.limit is not None and self.limit > 0:
            del url_array[self.limit:]

        self.no_urls = len(url_array)
        self.site_urls = url_array

        print('Urls:    {0}'.format(self.no_urls))
        print('Threads: {0} \n'.format(self.threads))

        start = time.time()

        try:
            splits = list(self._chunks(self.site_urls, self.threads))
            thread_pool = self._create_thread_pool(splits)

            for thread in thread_pool:
                thread.start()

            while self.progress < self.no_urls:
                time.sleep(1)
                if self.progress == self.no_urls:
                    break

        except (KeyboardInterrupt, SystemExit):
            self.thread_kill = True
            sys.exit(1)

        stop = time.time()
        time.sleep(1)  # Sleep for margin

        print('Urls warmed: {0} \nRuntime: {1}s'.format(self.no_urls, format(stop - start, '.4f')))
        avg_download_time = self._get_avg_load_time()
        print('Avg load time: {0}s/url'.format(round(avg_download_time, 4)))

        if self.verbose:
            if len(self.url_err) > 0:
                print('Failed urls: {0}'.format(len(self.url_err)))
                for err_link in self.url_err:
                    print('HTTP_CODE: {0} URL: {1}'.format(err_link['code'], err_link['url']))

        self._run_post_test()

        sys.exit(0)

    def _login(self):
        print('Logging in ...')

        account_url = self.base_url + 'customer/account/'
        login_url = account_url + 'login/'

        login_resp = self.reqs.get(
            login_url,
            headers={ "user-agent": "PFPCW cache warming script"},
            timeout=self.timeout,
        )

        login_bs = BeautifulSoup(login_resp.content, 'html.parser')
        login_form = login_bs.find('form', { 'id': 'login-form'})

        login_form_url = login_form.get('action')
        login_form_method = login_form.get('method')

        login_form_key = login_form.find('input', { 'name': 'form_key'})
        login_form_key = login_form_key.get('value')

        self.reqs.cookies.set('form_key', login_form_key)

        login_form_resp = self.reqs.request(
            method=login_form_method,
            url=login_form_url,
            data={
                'form_key': login_form_key,
                'login[username]': self.username,
                'login[password]': self.password,
            },
            headers={
                'content-type': 'application/x-www-form-urlencoded',
                'user-agent': 'PFPCW cache warming script',
            },
            timeout=self.timeout,
        )

        if len(login_form_resp.history) > 1 and login_form_resp.history[1].headers['location'] == login_url:
            print('Error while trying to login', file=sys.stderr)
            print('Request Headers:', file=sys.stderr)
            for k, v in login_form_resp.request.headers.items():
                print('    ' + k + ': ' + v, file=sys.stderr)
            print('Response Headers:', file=sys.stderr)
            for k, v in login_form_resp.history[0].headers.items():
                print('    ' + k + ': ' + v, file=sys.stderr)
            sys.exit(1)

        account_bs = BeautifulSoup(login_form_resp.content, 'html.parser')
        account_name = account_bs.find('div', { 'class': 'name-expand-wrapper'})
        account_name = account_name.text.strip()
        print("Logged in as '{}'\n".format(account_name))

    def _run_post_test(self):
        old_avg_download_time = self._get_avg_load_time()

        self.verbose = False
        self.load_times = []  # Reset the data

        print('----------------------------')
        print('Running post warming test...')
        self._warm(0, random.sample(self.site_urls, self.MAX_TEST_URL))

        new_avg_download_time = self._get_avg_load_time()

        print('Urls warmed: {0}'.format(self.MAX_TEST_URL))
        print('Avg load time: {0}s/url'.format(round(new_avg_download_time, 4)))
        print('Improved load time: {0}%'.format(
            round((old_avg_download_time - new_avg_download_time) / old_avg_download_time * 100, 1)))

    def _assemble_multiple_sitemap(self, sitemaps_array):
        """
        Combines sitemaps_array into a single string

        :param sitemaps_array:
        :return: string
        """
        sitemap_content = ''
        buffer = ''
        failed_sitemaps = []
        for idx, sitemap_url in enumerate(sitemaps_array):

            try:
                result = self._download_link(sitemap_url)['content']

                if len(result) < 1:
                    buffer += '!'
                    failed_sitemaps.append(sitemap_url)
                else:
                    buffer += '.'

                print('\r' + buffer, end=' ')

                sitemap_content += result
            except TypeError:
                print('Failed retrieving sitemap: {0}'.format(sitemap_url))

        return sitemap_content

    def _locate_sitemaps(self):
        """
        Returns all sitemap objects in robots.txt

        :return: array
        """
        result = self._download_link(self.site + '/' + 'robots.txt')

        sitemap_array = re.findall(r'(?:http|https):(?://)(?:[A-z0-9].{0,50})(?:|.xml.gz|.xml)', result['content'])

        if sitemap_array is None:
            return []

        return sitemap_array

    def _download_link(self, link):
        """
        Returns content of weblink.
        Returns uncompressed version of link if compressed

        :param link: web link
        :return: mixed: False or link content
        """
        if self._validate_link(link):
            try:
                headers = {}
                if self.headers:
                    for header in self.headers:
                        pieces = header.split(':')
                        if len(pieces) != 2:
                            print('Error while parsing header "{}"'.format(header), file=sys.stderr)
                            sys.exit(1)
                        headers[pieces[0].strip()] = pieces[1].strip()
                headers["user-agent"] = "PFPCW cache warming script"

                response = self.reqs.get(link,
                                            headers=headers,
                                            timeout=self.timeout)
                if response.ok is True:
                    content = ''

                    if '.xml.gz' in link:
                        content = gzip.GzipFile(fileobj=io.StringIO(response.content)).read()

                    if type(response.content) is bytes:
                        content = response.content.decode('utf-8')

                    return {
                        'code': 0 if response.ok else 1,
                        'url': link,
                        'content': content,
                        'status_code': response.status_code
                    }
            except Exception as e:
                print(repr(e))

            return False

    @staticmethod
    def _validate_link(link):
        """
        Check if string is a valid http/ftp/s/ link

        :param link:
        :return: bool:
        """
        regex = re.compile(
            r'^(?:http|ftp)s?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        if re.match(regex, link):
            return True
        return False

    @staticmethod
    def _chunks(seq, num):
        """
        Return array split in n amount of chunks
        :param seq:
        :param num:
        :return:
        """
        avg = len(seq) / float(num)
        out = []
        last = 0.0

        while last < len(seq):
            out.append(seq[int(last):int(last + avg)])
            last += avg

        return out

    @staticmethod
    def _parse_sitemap(sitemap_xml):
        """
        Return all occurrences of loc in sitemap.xml

        :param sitemap_xml:
        :return:
        """
        if re.findall('<urlset .*>', sitemap_xml):
            return re.findall('<loc>(.*?)</loc>?', sitemap_xml)

        return ''

    def _create_thread_pool(self, splits):
        """
        Create workers for warming

        :param splits:
        :return:
        """
        threads = []
        for i in range(self.threads):
            t = threading.Thread(target=self._warm, args=(
                i,
                splits[i],
            ))
            threads.append(t)
        return threads

    def _get_avg_load_time(self):
        """
        return avg load time

        :return:
        """
        return float(format(sum(self.load_times) / len(self.load_times)))

    def _warm(self, worker_id, links):
        """
        Download all links in :param link array.

        :param worker_id:
        :param links:
        :return: bool:
        """
        processed = 0

        for link in links:
            try:
                self.progress += 1
                processed += 1

                if self.thread_kill is True:
                    sys.exit(1)

                if self.delay > 0:
                    time.sleep(float(self.delay))

                start_time = time.time()
                result = self._download_link(link)

                if result['code'] is 0:
                    self.load_times.append(time.time() - start_time)

                if result['code'] is 1:
                    self.url_err.append({ 'url': link, 'code': result['status_code'] })

                if self.verbose:
                    print('({0}/{1}) {2} {3}'.format(self.progress, self.no_urls, '✓' if result['code'] is 0 else '×',
                                                        link))
            except Exception:
                if self.verbose:
                    print('Failed warming link: {0}'.format(link))

        if self.verbose:
            print('Thread {0} Completed. Processed {1}/{2}'.format(worker_id, processed, len(links)))

        return True


cache_warmer = CacheWarmer(
    sitemap_url=args.sitemap,
    site=args.site,
    delay=int(args.delay),
    limit=int(args.limit),
    threads=int(args.threads),
    timeout=int(args.timeout),
    username=args.username,
    password=args.password,
    headers=args.headers,
    random=args.random,
    verbose=args.verbose,
    silent=args.silent,
)
cache_warmer.run()

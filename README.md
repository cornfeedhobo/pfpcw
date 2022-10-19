# PFPCW

Python Full Page Cache Warmer

## Description

Python cache warming tool used for warming full page cache solutions by visting pages in sitemap.xml

Has built-in support for concurrent threads, randomizing sort order, url parse delay, and more.

Tests has been performed on Wordpress, Magento 1 and 2.

## Usage and flags

```plain
usage: pfpcw.py [-h] --sitemap url --site url [--delay int] [--limit int]
                [--threads int] [--timeout int] [--username email]
                [--password password] [-r] [-v] [-s]

Python cache warming tool used for warming full page cache solutions by
visting pages in sitemap.xml

optional arguments:
  -h, --help           show this help message and exit

optional arguments:
  --sitemap url        Url to sitemap, exclusive to --site. (default: None)
  --site url           Url to site, exclusive to --sitemap. (default: None)
  --delay int          Delay in seconds between url warming. (default: 0)
  --limit int          Number limit of urls to scan. (default: 0)
  --threads int        Number of concurrent threads to use. (default: 1)
  --timeout int        Timeout limit for requests. (default: 10)
  --username email     Login username. (default: None)
  --password password  Login password. (default: None)
  -r                   Randomize order of url warming. (default: False)
  -v                   Run in verbose mode. Will print output to terminal.
                       (default: False)
  -s                   Run in silent mode. Redirects all output to /dev/null.
                       (default: False)
```

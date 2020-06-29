"""
Functions dedicated to command-line processing.
"""

## This file is available from https://github.com/adbar/trafilatura
## under GNU GPL v3 license


import logging
import random
import re
import signal
import string
import sys

from collections import OrderedDict
from datetime import datetime
from os import makedirs, path, walk
from time import sleep

from .core import extract
from .settings import MIN_FILE_SIZE, MAX_FILE_SIZE, PROCESSING_TIMEOUT
from .utils import fetch_url


LOGGER = logging.getLogger(__name__)
random.seed(345)  # make generated file names reproducible
FILENAME_LEN = 8


# try signal https://stackoverflow.com/questions/492519/timeout-on-a-function-call
def handler(signum, frame):
    '''Raise a timeout exception to handle rare malicious files'''
    raise Exception('unusual file processing time, aborting')


def load_input_urls(filename):
    '''Read list of URLs to process'''
    input_urls = list()
    try:
        # optional: errors='strict', buffering=1
        with open(filename, mode='r', encoding='utf-8') as inputfile:
            for line in inputfile:
                url_match = re.match(r'https?://[^ ]+', line.strip())  # if not line.startswith('http'):
                try:
                    input_urls.append(url_match.group(0))
                except AttributeError:
                    LOGGER.warning('Not an URL, discarding line: %s', line)
                    continue
    except UnicodeDecodeError:
        sys.exit('# ERROR: system, file type or buffer encoding')
    return input_urls


def load_blacklist(filename):
    '''Read list of unwanted URLs'''
    blacklist = set()
    with open(filename, mode='r', encoding='utf-8') as inputfh:
        for line in inputfh:
            url = line.strip()
            blacklist.add(url)
            # add http/https URLs for safety
            if url.startswith('https'):
                blacklist.add(re.sub(r'^https', 'http', url))
            elif url.startswith('http'):
                blacklist.add(re.sub(r'^http:', 'https:', url))
    return blacklist


def check_outputdir_status(directory):
    '''Check if the output directory is within reach and writable'''
    # check the directory status
    if not path.exists(directory) or not path.isdir(directory):
        try:
            makedirs(directory)
        except OSError:
            sys.stderr.write('# ERROR: Destination directory cannot be created: ' + directory + '\n')
            # raise OSError()
            return False
    return True


def determine_filename(args, destination_directory, fileslug=None):
    '''Pick a file name based on output type'''
    # determine extension
    extension = '.txt'
    if args.xml or args.xmltei or args.output_format == 'xml':
        extension = '.xml'
    elif args.csv or args.output_format == 'csv':
        extension = '.csv'
    # determine file slug
    if fileslug is None:
        output_path = path.join(destination_directory, \
            ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(FILENAME_LEN)) \
            + extension)
        while path.exists(output_path):
            output_path = path.join(destination_directory, \
                ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(FILENAME_LEN)) \
                + extension)
    else:
        output_path = path.join(destination_directory, fileslug + extension)
    return output_path


def archive_html(htmlstring, args):
    '''Write a copy of raw HTML in backup directory'''
    # determine file name
    fileslug = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(FILENAME_LEN))
    output_path = path.join(args.backup_dir, fileslug + '.html')
    while path.exists(output_path):
        fileslug = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(FILENAME_LEN))
        output_path = path.join(args.backup_dir, fileslug + '.html')
    # check the directory status
    if check_outputdir_status(args.backup_dir) is True:
        # write
        with open(output_path, mode='w', encoding='utf-8') as outputfile:
            outputfile.write(htmlstring)
    return fileslug


def write_result(result, args, filename=None, counter=None):
    '''Deal with result (write to STDOUT or to file)'''
    if result is None:
        return
    if args.outputdir is None:
        sys.stdout.write(result + '\n')
    else:
        if counter is not None:
            destination_directory = path.join(args.outputdir, counter)
        else:
            destination_directory = args.outputdir
        # check the directory status
        if check_outputdir_status(destination_directory) is True:
            # write
            destination_path = determine_filename(args, destination_directory, filename)
            with open(destination_path, mode='w', encoding='utf-8') as outputfile:
                outputfile.write(result)


def generate_filelist(inputdir):
    '''Walk the directory tree and output all file names'''
    for root, _, inputfiles in walk(inputdir):
        for fname in inputfiles:
            # filelist.append(path.join(root, fname))
            yield path.join(root, fname)


def file_processing_pipeline(filename, args):
    '''Aggregated functions to process a file list'''
    try:
        with open(filename, mode='r', encoding='utf-8') as inputfh:
            htmlstring = inputfh.read()
    except UnicodeDecodeError:
        LOGGER.warning('Discarding (file type issue): %s', filename)
    else:
        result = examine(htmlstring, args, url=args.URL)
        write_result(result, args)


def url_processing_checks(blacklist, input_urls):
    '''Filter and deduplicate input urls'''
    # control blacklist
    if blacklist:
        input_urls = [u for u in input_urls if u not in blacklist]
    # deduplicate
    input_urls = list(OrderedDict.fromkeys(input_urls))
    return input_urls


def url_processing_pipeline(args, input_urls, sleeptime):
    '''Aggregated functions to show a list and download and process an input list'''
    input_urls = url_processing_checks(args.blacklist, input_urls)
    # print list without further processing
    if args.list:
        for url in input_urls:
            write_result(url, args)  # print('\n'.join(input_urls))
        return None
    # build domain-aware processing list
    domain_dict = dict()
    while len(input_urls) > 0:
        url = input_urls.pop()
        try:
            domain_name = re.search(r'^https?://([^/]+)', url).group(1)
        except AttributeError:
            domain_name = 'unknown'
        if domain_name not in domain_dict:
            domain_dict[domain_name] = list()
        domain_dict[domain_name].append(url)
    # iterate
    backoff_dict = dict()
    i = 0
    if len(input_urls) > 1000:
        counter = 0
    else:
        counter = None
    while len(domain_dict) > 0:
        domain = random.choice(list(domain_dict.keys()))
        if domain not in backoff_dict or \
        (datetime.now() - backoff_dict[domain]).total_seconds() > sleeptime:
            url = domain_dict[domain].pop()
            htmlstring = fetch_url(url)
            # register in backoff dictionary to ensure time between requests
            backoff_dict[domain] = datetime.now()
            if htmlstring is not None:
                # backup option
                if args.backup_dir:
                    filename = archive_html(htmlstring, args)
                else:
                    filename = None
                # process
                result = examine(htmlstring, args, url=url)
                counter += 1
                write_result(result, args, filename, counter)
            else:
                # log the error
                print('No result for URL: ' + url, file=sys.stderr)
            # clean registries
            if len(domain_dict[domain]) == 0:
                del domain_dict[domain]
                del backoff_dict[domain]
        # safeguard
        else:
            i += 1
            if i > len(domain_dict)*3:
                sleep(sleeptime)
                i = 0


def examine(htmlstring, args, url=None):
    """Generic safeguards and triggers"""
    result = None
    # safety check
    if htmlstring is None:
        sys.stderr.write('# ERROR: empty document\n')
    elif len(htmlstring) > MAX_FILE_SIZE:
        sys.stderr.write('# ERROR: file too large\n')
    elif len(htmlstring) < MIN_FILE_SIZE:
        sys.stderr.write('# ERROR: file too small\n')
    # proceed
    else:
        # put timeout signal in place
        if args.timeout is True:
            signal.signal(signal.SIGALRM, handler)
            signal.alarm(PROCESSING_TIMEOUT)
        try:
            result = extract(htmlstring, url, '0000', no_fallback=args.fast,
                             include_comments=args.nocomments, include_tables=args.notables,
                             include_formatting=args.formatting,
                             with_date=args.with_date,
                             output_format=args.output_format, tei_validation=args.validate,
                             target_language=args.target_language)
        # ugly but efficient
        except Exception as err:
            sys.stderr.write('# ERROR: ' + str(err) + '\nDetails: ' + str(sys.exc_info()[0]) + '\n')
        # deactivate
        if args.timeout is True:
            signal.alarm(0)
    return result

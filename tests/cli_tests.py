"""
Unit tests for the command-line interface.
"""

import io
import logging
import os
import sys

from contextlib import redirect_stdout
from datetime import datetime
from unittest.mock import patch

from trafilatura import cli, cli_utils, utils
from trafilatura.settings import DEFAULT_CONFIG


logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
TEST_DIR = os.path.abspath(os.path.dirname(__file__))


def test_parser():
    '''test argument parsing for the command-line interface'''
    testargs = ['', '-fv', '--xmltei', '--notables', '-u', 'https://www.example.org']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    assert args.fast is True
    assert args.verbose is True
    assert args.notables is False
    assert args.xmltei is True
    assert args.URL == 'https://www.example.org'
    args = cli.map_args(args)
    assert args.output_format == 'xmltei'
    testargs = ['', '-out', 'csv', '-u', 'https://www.example.org']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    assert args.fast is False
    assert args.verbose is False
    assert args.output_format == 'csv'
    # test args mapping
    testargs = ['', '--xml']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    args = cli.map_args(args)
    assert args.output_format == 'xml'
    args.xml, args.csv = False, True
    args = cli.map_args(args)
    assert args.output_format == 'csv'
    args.csv, args.json = False, True
    args = cli.map_args(args)
    assert args.output_format == 'json'
    # process_args
    args.inputdir = '/dev/null'
    args.verbose = True
    args.blacklist = os.path.join(TEST_DIR, 'resources/list-discard.txt')
    cli.process_args(args)
    assert len(args.blacklist) == 2
    # filter
    testargs = ['', '-i', 'resources/list-discard.txt', '--url-filter', 'test1', 'test2']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    assert args.inputfile == 'resources/list-discard.txt'
    assert args.url_filter == ['test1', 'test2']


def test_climain():
    '''test arguments and main CLI entrypoint'''
    assert os.system('trafilatura --help') == 0  # exit status
    # input directory walking and processing
    assert os.system('trafilatura --inputdir "tests/resources/"') == 0
    # piped input
    assert os.system('echo "<html><body></body></html>" | trafilatura') == 0


def test_input_type():
    '''test input type errors'''
    testfile = 'docs/trafilatura-demo.gif'
    testargs = ['', '-u', 'http']
    with patch.object(sys, 'argv', testargs):
        assert cli.main() is None
    testargs = ['', '-v']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    with open(testfile, 'rb') as f:
        teststring = f.read(1024)
    assert cli.examine(teststring, args) is None
    testfile = 'docs/usage.rst'
    with open(testfile, 'r') as f:
        teststring = f.read()
    assert cli.examine(teststring, args) is None
    # test file list
    assert 10 <= len(list(cli_utils.generate_filelist(os.path.join(TEST_DIR, 'resources')))) <= 20


def test_sysoutput():
    '''test command-line output with respect to CLI arguments'''
    testargs = ['', '--csv', '-o', '/root/forbidden/']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    filepath, destdir = cli_utils.determine_output_path(args, args.outputdir, '')
    assert len(filepath) >= 10 and filepath.endswith('.csv')
    assert destdir == '/root/forbidden/'
    assert cli_utils.check_outputdir_status(args.outputdir) is False
    testargs = ['', '--xml', '-o', '/tmp/you-touch-my-tralala']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    assert cli_utils.check_outputdir_status(args.outputdir) is True
    # test fileslug for name
    filepath, destdir = cli_utils.determine_output_path(args, args.outputdir, '', new_filename='AAZZ')
    assert filepath.endswith('AAZZ.xml')
    # test json output
    args2 = args
    args2.xml, args2.json = False, True
    filepath2, destdir2 = cli_utils.determine_output_path(args, args.outputdir, '', new_filename='AAZZ')
    assert filepath2.endswith('AAZZ.json')
    # test directory counter
    assert cli_utils.determine_counter_dir('testdir', 0) == 'testdir/1'
    # test file writing
    testargs = ['', '--csv', '-o', '/dev/null/']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    result = 'DADIDA'
    cli_utils.write_result(result, args)
    # process with no counter
    assert cli_utils.process_result('DADIDA', args, None, None, DEFAULT_CONFIG) is None
    # test keeping dir structure
    testargs = ['', '-i', 'myinputdir/', '-o', 'test/', '--keep-dirs']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    filepath, destdir = cli_utils.determine_output_path(args, 'testfile.txt', '')
    assert filepath == 'test/testfile.txt'
    # test hash as output file name
    assert args.hash_as_name is False
    args.hash_as_name = True
    assert args.keep_dirs is True
    args.keep_dirs = False
    filepath, destdir = cli_utils.determine_output_path(args, 'testfile.txt', '')
    assert filepath == 'test/2jmj7l5rSw0yVb-vlWAYkK-YBwk.txt'
    

def test_download():
    '''test page download and command-line interface'''
    testargs = ['', '-v']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    assert cli.examine(None, args) is None
    assert cli.examine(' ', args) is None
    assert cli.examine('0'*int(10e7), args) is None
    #url = 'https://httpbin.org/status/200'
    #teststring = utils.fetch_url(url)
    #assert teststring is None  # too small
    #assert cli.examine(teststring, args, url) is None
    #url = 'https://httpbin.org/links/2/2'
    #teststring = utils.fetch_url(url)
    #assert teststring is not None
    #assert cli.examine(teststring, args, url) is None
    url = 'https://httpbin.org/html'
    teststring = utils.fetch_url(url)
    assert teststring is not None
    assert cli.examine(teststring, args, url) is not None
    # single/multiprocessing
    domain_dict = dict()
    domain_dict['https://httpbin.org'] = ['/status/301', '/status/304', '/status/200', '/status/300', '/status/400', '/status/505']
    results = cli_utils.download_queue_processing(domain_dict, args, 0.25, None, DEFAULT_CONFIG)
    assert len(results[0]) == 5 and results[1] is None
    # test backoff algorithm
    testdict = dict()
    backoffdict = dict()
    testdict['http://test.org'] = ['/1']
    assert cli_utils.draw_backoff_url(testdict, backoffdict, 0, 0) == ('http://test.org/1', dict(), dict(), 0)
    testdict['http://test.org'] = ['/1']
    backoffdict['test.org'] = datetime(2019, 5, 18, 15, 17, 8, 132263)
    assert cli_utils.draw_backoff_url(testdict, backoffdict, 0, 0) == ('http://test.org/1', dict(), dict(), 0)
    testdict['http://test.org'] = ['/1']
    backoffdict['test.org'] = datetime(2019, 5, 18, 15, 17, 8, 132263)
    assert cli_utils.draw_backoff_url(testdict, backoffdict, 0, 3) == ('http://test.org/1', dict(), dict(), 3)
    testdict['http://test.org'] = ['/1']
    backoffdict['test.org'] = datetime(2030, 5, 18, 15, 17, 8, 132263)
    assert cli_utils.draw_backoff_url(testdict, backoffdict, 0, 3) == ('http://test.org/1', dict(), dict(), 0)


def test_cli_pipeline():
    '''test command-line processing pipeline'''
    # test URL listing
    testargs = ['', '--list']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    assert cli_utils.url_processing_pipeline(args, dict(), 0) is None
    inputdict = cli.convert_inputlist(None, ['https://www.example.org/'], None, None)
    assert cli_utils.url_processing_pipeline(args, inputdict, 0) is None
    # test inputlist + blacklist
    resources_dir = os.path.join(TEST_DIR, 'resources')
    testargs = ['', '-i', os.path.join(resources_dir, 'list-process.txt')]
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    my_urls = cli_utils.load_input_urls(args.inputfile)
    assert my_urls is not None and len(my_urls) == 2
    resources_dir = os.path.join(TEST_DIR, 'resources')
    testargs = ['', '-i', os.path.join(resources_dir, 'list-process.txt'), '--blacklist', os.path.join(resources_dir, 'list-discard.txt')]
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    assert args.blacklist is not None
    # test backoff between domain requests
    inputdict = cli_utils.convert_inputlist(args.blacklist, my_urls, None, None)
    reftime = datetime.now()
    cli_utils.url_processing_pipeline(args, inputdict, 2)
    delta = (datetime.now() - reftime).total_seconds()
    assert delta > 2
    # test blacklist and empty dict
    args.blacklist = cli_utils.load_blacklist(args.blacklist)
    assert len(args.blacklist) == 2
    inputdict = cli_utils.convert_inputlist(args.blacklist, my_urls, None, None)
    cli_utils.url_processing_pipeline(args, inputdict, 2)
    # test backup
    testargs = ['', '--backup-dir', '/tmp/']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    cli_utils.archive_html('00Test', args)
    # test date-based exclusion
    testargs = ['', '-out', 'xml', '--with-metadata']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    with open(os.path.join(resources_dir, 'httpbin_sample.html'), 'r') as f:
        teststring = f.read()
    assert cli.examine(teststring, args) is None
    # test timeout
    testargs = ['', '-out', 'xml', '--timeout']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    with open(os.path.join(resources_dir, 'httpbin_sample.html'), 'r') as f:
        teststring = f.read()
    assert cli.examine(teststring, args) is not None
    # test JSON output
    testargs = ['', '-out', 'json']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    with open(os.path.join(resources_dir, 'httpbin_sample.html'), 'r') as f:
        teststring = f.read()
    assert cli.examine(teststring, args) is not None
    # dry-run file processing pipeline
    testargs = ['', '--parallel', '1', '--inputdir', '/dev/null']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    cli_utils.file_processing_pipeline(args)
    # file processing pipeline on resources/
    args.inputdir = resources_dir
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    cli_utils.file_processing_pipeline(args)
    # sitemaps
    print('##')
    testargs = ['', '--sitemap', 'https://httpbin.org/', '--list']
    with patch.object(sys, 'argv', testargs):
        args = cli.parse_args(testargs)
    f = io.StringIO()
    with redirect_stdout(f):
        cli.process_args(args)
    assert len(f.getvalue()) == 0


def test_input_filtering():
    '''test internal functions to filter urls'''
    # deduplication and filtering
    myinput = ['https://example.org/1', 'https://example.org/2', 'https://example.org/2', 'https://example.org/3', 'https://example.org/4', 'https://example.org/5', 'https://example.org/6']
    myblacklist = {'example.org/1', 'example.org/3', 'example.org/5'}
    inputdict = cli_utils.convert_inputlist(myblacklist, myinput, None, None)
    assert inputdict['https://example.org'] == ['/2', '/4', '/6']
    # URL in blacklist
    resources_dir = os.path.join(TEST_DIR, 'resources')
    my_urls = cli_utils.load_input_urls(os.path.join(resources_dir, 'list-process.txt'))
    my_blacklist = cli_utils.load_blacklist(os.path.join(resources_dir, 'list-discard.txt'))
    inputdict = cli_utils.convert_inputlist(my_blacklist, my_urls, None, None)
    assert len(inputdict) == 0
    # URL filter
    my_urls = cli_utils.load_input_urls(os.path.join(resources_dir, 'list-process.txt'))
    assert len(cli.convert_inputlist(None, my_urls, ['status'], None)) == 1
    my_urls = cli_utils.load_input_urls(os.path.join(resources_dir, 'list-process.txt'))
    assert len(cli.convert_inputlist(None, my_urls, ['teststring'], None)) == 0
    my_urls = cli_utils.load_input_urls(os.path.join(resources_dir, 'list-process.txt'))
    assert len(cli.convert_inputlist(None, my_urls, ['status', 'teststring'], None)) == 1


if __name__ == '__main__':
    test_parser()
    test_climain()
    test_input_type()
    test_sysoutput()
    test_cli_pipeline()
    test_input_filtering()
    test_download()

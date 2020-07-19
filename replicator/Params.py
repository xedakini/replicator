import argparse, logging, os, sys


def parse_args():
    def port_number(s):
        port = int(s)
        if 0 < port < 65536:
            return port
        raise argparse.ArgumentTypeError('PORT must be integer in interval [1, 65535]')

    def positive_number(s):
        x = float(s)
        if x <= 0:
            raise argparse.ArgumentTypeError('value must be a positive number')
        return x

    parser = argparse.ArgumentParser(description='http-replicator: a caching http proxy',
                                     add_help=False)
    # yapf: disable
    parser.add_argument(
        '--port', '-p', default=8080, type=port_number,
        help='listen on PORT for incoming connections (default=8080)')
    parser.add_argument(
        '--bind', '-b', '-i', '--ip', default='::1', metavar='ADDRESS',
        help='bind server to ADDRESS (default=::1)')
    parser.add_argument(
        '--root', '-r', '-d', '--dir', metavar='ROOTDIR',
        help='set cache base directory to ROOTDIR (default is the current directory)')
    parser.add_argument(
        '--timeout', '-t', default=15, type=positive_number,
        help='break connection after TIMEOUT seconds of inactivity (default=15)')
    parser.add_argument(
        '--verbose', '-v', default=0, action='count',
        help='show transaction activity; use twice for debugging')
    parser.add_argument(
        '--flat', '-f', action='store_true',
        help='flat mode: cache all files in ROOTDIR (dangerous!)')
    parser.add_argument(
        '--static', '-s', action='store_true',
        help='static mode: assume files never change')
    parser.add_argument(
        '--offline', action='store_true',
        help='offline mode: never initiate a network connection')
    parser.add_argument(
        '--limit', default=0, type=float,
        help='cap download rate to LIMIT KiB/s')
    parser.add_argument(
        '--daemon', metavar='LOGFILE',
        help='route output to specified LOGFILE, and detach')
    parser.add_argument(
        '--pidfile', '--pid', metavar='PIDFILE',
        help='if --daemon is used, write pid of daemon to PIDFILE')
    parser.add_argument(
        '--help', '-h', action='help',
        help='show this help message and exit')
    # yapf: enable

    global OPTS
    OPTS = parser.parse_args()
    OPTS.limit *= 1024
    OPTS.maxchunk = 8192
    OPTS.suffix = '.incomplete'
    OPTS.maxfilelen = os.pathconf('.', 'PC_NAME_MAX') - len(OPTS.suffix)
    OPTS.version = 'replicator/4.0alpha4'


def setup_logging():
    global OPTS
    OPTS._logstream = open(OPTS.daemon, 'a') if OPTS.daemon else sys.stdout
    loglevel = (logging.WARNING, logging.INFO, logging.DEBUG)[min(OPTS.verbose, 2)]
    logging.basicConfig(stream=OPTS._logstream, level=loglevel, format='%(message)s')


#initialize:
OPTS = None
parse_args()
setup_logging()
if OPTS.root:
    try:
        os.chdir(OPTS.root)
    except Exception as e:
        sys.exit(f'Error: invalid cache directory {OPTS.root} ({e})')

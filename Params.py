import argparse, sys, os

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


parser = argparse.ArgumentParser(description = 'http-replicator: a caching http proxy')

parser.add_argument('-p', '--port', type=port_number, default=8080,
        help='listen on PORT for incoming connections (default=8080)')
parser.add_argument('-b', '--bind', default='::1', metavar='ADDRESS',
        help='bind server to ADDRESS (default=::1)')
parser.add_argument('-r', '--root', default=os.getcwd(),
        help='set cache base directory to ROOT, default is the current directory')
parser.add_argument('-v', '--verbose', action='count',
        help='show http headers and other info')
parser.add_argument('-t', '--timeout', type=positive_number, default=15,
        help='break connection after TIMEOUT seconds of inactivity (default=15)')
parser.add_argument('--flat', action='store_true',
        help='flat mode; cache all files in ROOT directory (dangerous!)')
parser.add_argument('--static', action='store_true',
        help='static mode; assume files never change')
parser.add_argument('--offline', action='store_true',
        help='offline mode; never connect to server')
parser.add_argument('--limit', type=float, default=0,
        help='cap download rate to LIMIT KiB/s')
parser.add_argument('--daemon', metavar='LOGFILE',
        help='route output to specified LOGFILE, and detach')
parser.add_argument('--pid', metavar='PIDFILE',
        help='if --daemon is used, write pid of daemon to PIDFILE')
parser.add_argument('--debug', action='store_true',
        help='switch from "gather" to "debug" output module')

args = parser.parse_args()

# allow old names (for now)
PORT = args.port
BIND = args.bind
ROOT = os.path.realpath(args.root) + os.sep
VERBOSE = args.verbose
TIMEOUT = args.timeout
FLAT = args.flat
STATIC = args.static
ONLINE = not args.offline
LIMIT = args.limit * 1024
LOG = args.daemon
PIDFILE = args.pid
DEBUG = args.debug

if not os.path.isdir(ROOT):
    sys.exit('Error: invalid cache directory %s' % ROOT)

# some non-commandline parameters
MAXCHUNK = 1448 # maximum lan packet?
SUFFIX = '.incomplete'
MAXFILELEN = os.pathconf(ROOT, 'PC_NAME_MAX') - len(SUFFIX)
TIMEFMT = (
        '%a, %d %b %Y %H:%M:%S GMT',
        '%a, %d %b %Y %H:%M:%S +0000 GMT',
        '%a, %d %b %Y %H:%M:%S +0000',
        )

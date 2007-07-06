import sys, os, socket

_args = iter( sys.argv )

PROG = _args.next()
PORT = 8080
TIMEFMT = '%a, %d %b %Y %H:%M:%S GMT'
MAXCHUNK = 1448 # maximum lan packet?
FAMILY = socket.AF_INET
STATIC = False
TIMEOUT = 15
DEBUG = False
VERBOSE = 0
LIMIT = 0
ROOT = os.getcwd() + os.sep
SUFFIX = '.incomplete'
USAGE = '''usage: %(PROG)s [options]

options:
  -h --help          show this help message and exit
  -p --port PORT     listen on this port for incoming connections, default %(PORT)i
  -s --static        static mode; assume files never change
  -t --timeout SEC   break connection after so many seconds of inactivity, default %(TIMEOUT)i
     --forward       forward requests to a second proxy server
  -6 --ipv6          try ipv6 addresses if available
     --limit RATE    limit download rate at a fixed K/s
  -l --log FILE      write output to a log file instead of stdout
  -v --verbose       show http headers and other info
     --debug         show traceback info
  -r --root          set cache root directory, default current: %(ROOT)s
  -d --daemon        run in background''' % locals()

for _arg in _args:

  if _arg in ('-h', '--help'):
    sys.exit( USAGE )
  elif _arg in ('-p', '--port'):
    try:
      PORT = int( _args.next() )
      assert PORT > 0
    except:
      sys.exit( 'Error: %s requires a positive numerical argument' % _arg )
  elif _arg in ('-s', '--static'):
    STATIC = True
  elif _arg in ('-t', '--timeout'):
    try:
      TIMEOUT = int( _args.next() )
      assert TIMEOUT > 0
    except:
      sys.exit( 'Error: %s requires a positive numerical argument' % _arg )
  elif _arg == '--debug':
    DEBUG = True
  elif _arg in ('-v', '--verbose'):
    VERBOSE += 1
  elif _arg == '--limit':
    try:
      LIMIT = 1024 * float( _args.next() )
    except:
      sys.exit( 'Error: %s requires a numerical argument' % _arg )
  elif _arg in ('-r', '--root'):
    try:
      ROOT = os.path.realpath( _args.next() ) + os.sep
      assert os.path.isdir( ROOT )
    except StopIteration:
      sys.exit( 'Error: %s requires a directory argument' % _arg )
    except:
      sys.exit( 'Error: invalid cache directory %s' % ROOT )
  elif _arg in ('-6', '--ipv6'):
    FAMILY = socket.AF_UNSPEC
  else:
    sys.exit( 'Error: invalid option %r' % _arg )

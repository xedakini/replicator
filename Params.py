import argparse, socket, sys, os, logging

OPTS = None

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

  parser = argparse.ArgumentParser(description = 'http-replicator: a caching http proxy')
  parser.add_argument('-p', '--port', type=port_number, default=8080,
        help='listen on PORT for incoming connections (default=8080)')
  parser.add_argument('-b', '--bind', default='::1', metavar='ADDRESS',
        help='bind server to ADDRESS (default=::1)')
  parser.add_argument('-r', '--root', default=os.getcwd(),
        help='set cache base directory to ROOT, default is the current directory')
  parser.add_argument('-v', '--verbose', default=0, action='count',
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
  parser.add_argument('--pidfile', '--pid', metavar='PIDFILE',
        help='if --daemon is used, write pid of daemon to PIDFILE')
  parser.add_argument('--debug', action='store_true',
        help='switch from "gather" to "debug" output module')

  global OPTS
  OPTS = parser.parse_args()
  OPTS.limit *= 1024
  OPTS.maxchunk = 1448 # maximum lan packet?
  OPTS.suffix = '.incomplete'
  OPTS.maxfilelen = os.pathconf('.', 'PC_NAME_MAX') - len(OPTS.suffix)
  OPTS.timefmt = (
      '%a, %d %b %Y %H:%M:%S GMT',
      '%a, %d %b %Y %H:%M:%S +0000 GMT',
      '%a, %d %b %Y %H:%M:%S +0000',
      )


def setup_logging():
  global OPTS
  OPTS._logstream = sys.stdout
  if OPTS.daemon:
    OPTS._logstream = open(OPTS.daemon, 'a')

  #map OPTS.verbose to logging level: 0=info, 1=debug, 2=notset
  logging.basicConfig(stream=OPTS._logstream,
          level=max(1,10*(2-OPTS.verbose)),
          format='%(message)s', style='%')
 
def chdir():
  try:
    os.chdir(OPTS.root)
  except Exception as e:
    sys.exit(f'Error: invalid cache directory {OPTS.root} - ({e})')

def get_listener():
  try:
    addrs = socket.getaddrinfo(OPTS.bind, OPTS.port, type=socket.SOCK_STREAM)
    family, socktype, proto, canonname, sockaddr = addrs[0]
    listener = socket.socket(family, socktype, proto)
    listener.setblocking(0)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,
            1 | listener.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR))
    listener.bind(sockaddr[:2])
    listener.listen(5)
    return listener
  except Exception as e:
    sys.exit(f'error: failed to create socket: {e}')


def daemonize():
  with open('/dev/null', 'r') as nul:
    os.dup2(nul.fileno(), sys.stdin.fileno())
  if not OPTS.daemon:
    return

  try:
    # attempt most os activity early, to catch errors before we fork
    pidout = None
    if OPTS.pidfile:
      pidout = open(OPTS.pidfile, 'w') # open pid file for writing
    os.setsid()
    # -rw-r--r-- / 0644 / u=rw,go=r
    os.umask(0o022)

    #first fork: create intermediate child process
    pid = os.fork()
  except IOError as e:
    sys.exit(f'error: failed to open {e.filename}')
  except OSError as e:
    sys.exit(f'error: failed to fork process: {e.strerror}')
  except Exception as e:
    sys.exit(f'error: {e}')

  if pid:
    #parent process waits for its child to (create daemon and exit), then exits
    cpid, status = os.wait()
    sys.exit(status >> 8)

  try:
    #second fork; will next orphan resulting granchild as daemon:
    pid = os.fork()
  except Exception as e:
    sys.exit(f'error: {e}')

  if pid:
    #child successfully spawned grandchild; report grandchild pid and exit child
    if pidout:
      pidout.write(str(pid))
      pidout.close()
    else:
      print(pid)
    sys.exit(0)

  os.dup2(OPTS._logstream.fileno(), sys.stdout.fileno())
  os.dup2(OPTS._logstream.fileno(), sys.stderr.fileno())

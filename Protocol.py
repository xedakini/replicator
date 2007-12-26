import Params, Response, time, socket, os, sys


DNSCache = {}

def connect( addr ):

  if addr not in DNSCache:

    print 'Quering name server for', addr[ 0 ]

    DNSCache[ addr ] = socket.getaddrinfo( addr[ 0 ], addr[ 1 ], Params.FAMILY, socket.SOCK_STREAM )

  family, socktype, proto, canonname, sockaddr = DNSCache[ addr ][ 0 ]

  print 'Connecting to %s:%i' % sockaddr

  sock = socket.socket( family, socktype, proto )
  sock.setblocking( 0 )
  sock.connect_ex( sockaddr )

  return sock


class Cache:

  __NOTCACHABLE = object()
  __NOTINCACHE = object()
  __PARTIAL = object()
  __INCACHE = object()

  def __init__( self, request ):

    self.__file = None

    if request.cmd() != 'GET' or request.path().endswith( '/' ):
      self.__state = self.__NOTCACHABLE
      return

    path = '%s:%i' % request.addr() + request.path()
    args = path.find( '?' )
    if args != -1:
      path = path[ :args ] + path[ args: ].replace( '/', '%2F' )

    if Params.VERBOSE:
      print 'Cache position:', path

    self.__path = Params.ROOT + path

    if args != -1:
      if Params.VERBOSE:
        print 'Dynamic content; using cache write-only'
      self.__state = self.__NOTINCACHE
      return

    if os.path.isfile( self.__path + Params.SUFFIX ):
      self.__state = self.__PARTIAL
    elif os.path.isfile( self.__path ):
      self.__state = self.__INCACHE
    else:
      self.__state = self.__NOTINCACHE
      return

    stat = os.stat( self.__state is self.__PARTIAL and self.__path + Params.SUFFIX or self.__path )
    self.__size = stat.st_size
    self.__mtime = stat.st_mtime

    print self.__state is self.__PARTIAL and 'Partial' or 'Complete', 'file in cache since', time.ctime( self.__mtime )

  def cachable( self ):

    return self.__state is not self.__NOTCACHABLE

  def partial( self ):

    return self.__state is self.__PARTIAL

  def incache( self ):

    return self.__state is self.__INCACHE

  def mtime( self ):

    return self.__mtime

  def size( self ):

    return self.__size

  def file( self ):

    assert self.__file is not None
    return self.__file

  def remove( self ):

    assert self.__file is None

    if self.__state is self.__PARTIAL:
      print 'Removing partial file from cache'
      os.remove( self.__path + Params.SUFFIX )
      if os.path.isfile( self.__path ):
        self.__state = self.__INCACHE
      else:
        self.__state = self.__NOTINCACHE
    elif self.__state is self.__INCACHE:
      print 'Removing complete file from cache'
      os.remove( self.__path )
      self.__state = self.__NOTINCACHE

  def open( self, size = None, offset = None ):

    assert self.__file is None

    if offset is not None:
      assert self.__state is self.__PARTIAL
      print 'Opening file for append at byte', offset
      self.__file = open( self.__path + Params.SUFFIX, 'a+' )
      self.__file.seek( 0, 2 )
      assert offset <= self.__file.tell() < size, 'range does not match file in cache'
      self.__file.seek( offset )
      self.__file.truncate()
      self.__size = size
    elif size is not None:
      print 'Opening new file'
      try:
        self.__makedirs( self.__path )
        self.__file = open( self.__path + Params.SUFFIX, 'w+' )
        self.__state = self.__PARTIAL
      except:
        print 'Failed to open file, falling back on tmpfile'
        self.__file = os.tmpfile()
        self.__state = self.__NOTINCACHE
      self.__size = size
    else:
      print 'Opening file read-only'
      assert self.__state is self.__INCACHE
      self.__file = open( self.__path, 'r' )
      self.__file.seek( 0, 2 )
      assert self.__size == self.__file.tell(), 'file size changed mysteriously'

  def __makedirs( self, path ):

    dir = os.path.dirname( path )
    if dir and not os.path.isdir( dir ):
      if os.path.isfile( dir ):
        print 'directory %s mistaken for file' % dir
        os.remove( dir )
      else:
        self.__makedirs( dir )
      os.mkdir( dir )

  def __finalize( self ):

    if self.__file is None or self.__state is not self.__PARTIAL:
      return

    self.__file.seek( 0, 2 )
    size = self.__file.tell()
    self.__file.close()

    if size != self.__size and self.__size != -1:
      print 'Wrong file size %i; leaving partial file in cache' % size
      return

    print 'Finalizing', self.__path
    os.rename( self.__path + Params.SUFFIX, self.__path )

  def __del__( self ):

    try:
      self.__finalize()
    except:
      print 'Finalize error:', sys.exc_value or sys.exc_type


class HttpProtocol( Cache ):

  Response = None

  def __init__( self, request ):

    Cache.__init__( self, request )

    if Params.STATIC and self.incache():

      self.Response = Response.DataResponse
      self.open()
      return

    head = '%s %s HTTP/1.1' % ( request.cmd(), request.path() )
    args = request.args()
    args[ 'Host' ] = request.addr()[ 0 ]
    args[ 'Connection' ] = 'close'
    args[ 'Date' ] = time.strftime( Params.TIMEFMT, time.gmtime() )
    args.pop( 'Keep-Alive', None )
    args.pop( 'Accept-Encoding', None )
    args.pop( 'Proxy-Connection', None )
    args.pop( 'Proxy-Authorization', None )
    if self.incache():
      print 'Checking if cache is up to date'
      args[ 'If-Modified-Since' ] = time.strftime( Params.TIMEFMT, time.gmtime( self.mtime() ) )
    elif self.partial():
      print 'Requesting resume of partial file'
      args[ 'If-Unmodified-Since' ] = time.strftime( Params.TIMEFMT, time.gmtime( self.mtime() ) )
      args[ 'Range' ] = 'bytes=%i-' % self.size()

    self.__sendbuf = '\r\n'.join( [ head ] + map( ': '.join, args.items() ) + [ '', request.body() ] )
    self.__recvbuf = ''
    self.__status = ''
    self.__message = ''
    self.__args = {}
    self.__request = request
    self.__socket = connect( request.addr() )

  def send( self, sock ):

    assert self.cansend()

    bytes = sock.send( self.__sendbuf )
    self.__sendbuf = self.__sendbuf[ bytes: ]

  def recv( self, sock ):

    assert not self.cansend()

    chunk = sock.recv( Params.MAXCHUNK, socket.MSG_PEEK )
    assert chunk, 'server closed connection before sending a complete message header'

    for line in chunk.splitlines( True ):
      sock.recv( len( line ) )
      self.__recvbuf, line = '', self.__recvbuf + line
      if line[ -1 ] != '\n':
        self.__recvbuf = line
      elif not self.__status:
        print 'Server sends', line.rstrip()
        fields = line.split()
        assert len( fields ) >= 3 and fields[ 0 ].startswith( 'HTTP/' ) and fields[ 1 ].isdigit(), 'invalid header line: %r' % line.rstrip()
        self.__status = int( fields[ 1 ] )
        self.__message = ' '.join( fields[ 2: ] )
      elif line == '\n' or line == '\r\n':
        break
      elif ':' in line:
        if Params.VERBOSE > 1:
          print '>', line.rstrip()
        key, value = line.split( ':', 1 )
        key = key.title()
        value = value.strip()
        if key in self.__args:
          self.__args[ key ] += '\r\n' + key + ': ' +  value
          if Params.VERBOSE:
            print 'Merged', key, 'values'
        else:
          self.__args[ key ] = value
      else:
        print 'Ignored:', line.rstrip()
    else:
      return

    if self.__status in ( 412, 416 ) and self.partial(): # TODO: check 412
 
      print 'Partial file changed, requesting complete file'

      self.remove()
      self.__init__( self.__request )
 
    elif self.__status == 200 and self.cachable():

      self.Response = Response.DataResponse
      print 'Server sends a complete file'

      size = int( self.__args.get( 'Content-Length', -1 ) )
      self.open( size )

    elif self.__status == 206 and self.partial():

      range = self.__args.get( 'Content-Range' )
      assert range, 'invalid 206 response: no content-range specified'
      assert range.startswith( 'bytes ' ), 'invalid content-range %r' % range
      range, size = range[ 6: ].split( '/' )
      beg, end = range.split( '-' )
      size = int( size )
      beg = int( beg )
      end = int( end )
      assert size == end + 1

      self.Response = Response.DataResponse
      print 'Server resumes transfer from byte', beg

      self.open( size, beg )

    elif self.__status == 304 and self.incache():

      print 'Cache is up to date'
      self.Response = Response.DataResponse

      self.__socket.close()
      self.open()

    else:

      print 'Forwarding response unchanged'
      self.Response = Response.BasicResponse

  def head( self ):

    return 'HTTP/1.1 %i %s' % ( self.__status, self.__message )

  def args( self, key = None, value = None ):

    if key is not None:
      return self.__args.get( key, value )

    return self.__args.copy()

  def socket( self ):

    return self.__socket

  def cansend( self ):

    return self.__sendbuf != ''

  def canjoin( self ):

    return True

    # TODO: fix re-enable joined downloads


class FtpProtocol( Cache ):

  # NOTE: in current state completely broken

  Response = None

  def __init__( self, request ):

    Cache.__init__( self, request )

    self.__socket = request.connect()
    self.__strbuf = ''

  def send( self, sock ):

    assert self.cansend(), '__rshift__ called while no data to send'

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]

  def recv( self, sock ):

    assert not self.cansend(), '__lshift__ called while still data to send'

    response = sock.recv( Params.MAXCHUNK, socket.MSG_PEEK )

    for line in response.splitlines( True ):
      if not line.endswith( '\n' ):
        return

      if Params.VERBOSE > 0:
        print '>', line.rstrip()

      sock.recv( len( line ) )

      if line[ 3 ] != '-':
        func = '__handle' + line[ :3 ]
        assert hasattr( self, func ), 'unknown response: %s' % line
        command = getattr( self, func )( line )
        if command:
          if Params.VERBOSE > 0:
            print 'Sending', command
          self.__strbuf = command + '\r\n'
        return

  def __handle220( self, line ):

    return 'USER anonymous'

  def __handle331( self, line ):

    return 'PASS anonymous@'

  def __handle230( self, line ):

    return 'TYPE I'

  def __handle200( self, line ):

    # switched to binary mode

    if self.hascache( partial=True ):
      mtime, size = self.getcache( partial=True )
      return 'REST %i' % size

  def __handle350( self, line ):

    return 'PASV'

  def __handle227( self, line ):

    # entered passive mode
    channel = eval( line.split()[ -1 ] )
    addr = '%i.%i.%i.%i' % channel[ :4 ], channel[ 4 ] * 256 + channel[ 5 ]
    print 'Connecting to %s:%i' % addr

    self.__datasocket = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
    self.__datasocket.setblocking( 0 )
    self.__datasocket.connect_ex( addr )

    return 'RETR ' + self.__path

  def __handle550( self, line ):

    print 'File not found'
    self.Response = Response.NotFoundResponse

  def __handle150( self, line ):

    # opening connection
    end = message.rfind( ' bytes)' )
    beg = message.rfind( '(', 0, end ) + 1
    if 0 < beg < end:
      size = int( message[ beg:end ] )
    else:
      size = -1

    self.setincache( partial=(beg,end) )

    self.Response = StreamBuffer
    self.__socket = self.__datasocket

  def socket( self ):

    return self.__socket

  def cansend( self ):

    return self.__strbuf != ''

  def canjoin( self ):

    return False

import Params, Response, Cache, time, socket, os, sys, calendar


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


class BlindProtocol:

  Response = None

  def __init__( self, request ):

    self.__socket = connect( request.addr() )
    self.__sendbuf = request.recvbuf()

  def socket( self ):

    return self.__socket

  def recvbuf( self ):

    return ''

  def hasdata( self ):

    return True

  def send( self, sock ):

    bytes = sock.send( self.__sendbuf )
    self.__sendbuf = self.__sendbuf[ bytes: ]
    if not self.__sendbuf:
      self.Response = Response.BlindResponse

  def done( self ):

    pass


class HttpProtocol( Cache.File ):

  Response = None

  def __init__( self, request ):

    Cache.File.__init__( self, '%s:%i' % request.addr() + request.path() )

    if Params.STATIC and self.full():
      self.__socket = None
      self.open_full()
      self.Response = Response.DataResponse
      return

    head = 'GET %s HTTP/1.1' % request.path()
    args = request.args()
    args.pop( 'Accept-Encoding', None )
    args.pop( 'Range', None )
    stat = self.partial() or self.full()
    if stat:
      size = stat.st_size
      mtime = time.strftime( Params.TIMEFMT, time.gmtime( stat.st_mtime ) )
      if self.partial():
        print 'Partial file in cache: %i bytes, %s' % ( size, mtime )
        args[ 'Range' ] = 'bytes=%i-' % size
        args[ 'If-Range' ] = mtime
      else:
        print 'Complete file in cache: %i bytes, %s' % ( size, mtime )
        args[ 'If-Modified-Since' ] = mtime

    self.__socket = connect( request.addr() )
    self.__sendbuf = '\r\n'.join( [ head ] + map( ': '.join, args.items() ) + [ '', '' ] )
    self.__recvbuf = ''
    self.__parse = HttpProtocol.__parse_head

  def hasdata( self ):

    return bool( self.__sendbuf )

  def send( self, sock ):

    assert self.hasdata()

    bytes = sock.send( self.__sendbuf )
    self.__sendbuf = self.__sendbuf[ bytes: ]

  def __parse_head( self, chunk ):

    eol = chunk.find( '\n' ) + 1
    if eol == 0:
      return 0

    line = chunk[ :eol ].rstrip()
    print 'Server sends', line
    fields = line.split()
    assert len( fields ) >= 3 and fields[ 0 ].startswith( 'HTTP/' ) and fields[ 1 ].isdigit(), 'invalid header line: %r' % line.rstrip()
    self.__status = int( fields[ 1 ] )
    self.__message = ' '.join( fields[ 2: ] )
    self.__args = {}
    self.__parse = HttpProtocol.__parse_args

    return eol

  def __parse_args( self, chunk ):

    eol = chunk.find( '\n' ) + 1
    if eol == 0:
      return 0

    line = chunk[ :eol ].rstrip()
    if ': ' in line:
      if Params.VERBOSE > 1:
        print '>', line.rstrip()
      key, value = line.split( ': ', 1 )
      key = key.title()
      if key in self.__args:
        self.__args[ key ] += '\r\n' + key + ': ' +  value
        if Params.VERBOSE:
          print 'Merged', key, 'values'
      else:
        self.__args[ key ] = value
    elif line:
      print 'Ignored:', line
    else:
      self.__parse = None

    return eol

  def recv( self, sock ):

    assert not self.hasdata()

    chunk = sock.recv( Params.MAXCHUNK, socket.MSG_PEEK )
    assert chunk, 'server closed connection before sending a complete message header'
    self.__recvbuf += chunk
    while self.__parse:
      bytes = self.__parse( self, self.__recvbuf )
      if not bytes:
        sock.recv( len( chunk ) )
        return
      self.__recvbuf = self.__recvbuf[ bytes: ]
    sock.recv( len( chunk ) - len( self.__recvbuf ) )

    if 'Last-Modified' in self.__args:
      self.mtime = calendar.timegm( time.strptime( self.__args[ 'Last-Modified' ], Params.TIMEFMT ) )

    if self.__status == 200:

      if 'Content-Length' in self.__args:
        self.size = int( self.__args[ 'Content-Length' ] )
      self.open_new()
      if self.__args.pop( 'Transfer-Encoding', None ) == 'chunked':
        self.Response = Response.ChunkedDataResponse
      else:
        self.Response = Response.DataResponse

    elif self.__status == 206 and self.partial():

      range = self.__args.get( 'Content-Range', 'none specified' )
      assert range.startswith( 'bytes ' ), 'invalid content-range: %s' % range
      range, size = range[ 6: ].split( '/' )
      beg, end = range.split( '-' )
      self.size = int( size )
      assert self.size == int( end ) + 1
      self.open_partial( int( beg ) )
      if self.__args.pop( 'Transfer-Encoding', None ) == 'chunked':
        self.Response = Response.ChunkedDataResponse
      else:
        self.Response = Response.DataResponse

    elif self.__status == 304 and self.full():

      self.open_full()
      self.__socket.close()
      self.Response = Response.DataResponse

    else:

      self.Response = Response.BlindResponse

  def recvbuf( self ):

    return '\r\n'.join( [ 'HTTP/1.1 %i %s' % ( self.__status, self.__message ) ] + map( ': '.join, self.__args.items() ) + [ '', '' ] )

  def args( self ):

    return self.__args.copy()

  def socket( self ):

    return self.__socket


class FtpProtocol( Cache.File ):

  # NOTE: in current state completely broken

  Response = None

  def __init__( self, request ):

    Cache.File.__init__( self, request )

    self.__socket = request.connect()
    self.__strbuf = ''

  def send( self, sock ):

    assert self.hasdata(), '__rshift__ called while no data to send'

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]

  def recv( self, sock ):

    assert not self.hasdata(), '__lshift__ called while still data to send'

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

  def hasdata( self ):

    return self.__strbuf != ''

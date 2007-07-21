import Params, Response, Util, time, socket


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


class HttpProtocol( Util.Cache, Util.Http ):

  Response = None

  def __init__( self, request ):

    Util.Cache.__init__( self, request )
    Util.Http.__init__( self )

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

    self.__strbuf = '\r\n'.join( [ head ] + map( ': '.join, args.items() ) + [ '', request.body() ] )
    self.__request = request
    self.__socket = connect( request.addr() )

  def send( self, sock ):

    assert self.cansend()

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]

  def recv( self, sock ):

    assert not self.cansend()

    if not self.recvhead( sock ):
      return

    status = self.head()[ 9:12 ]

    if status in ( '412', '416' ) and self.partial(): # TODO: check 412
 
      print 'Partial file changed, requesting complete file'

      self.remove()
      self.__init__( self.__request )
 
    elif self.args( 'Transfer-Encoding' ) == 'chunked':

      print 'Chunked data; not cached'
      self.Response = Response.BasicResponse

    elif status == '200' and self.cachable():

      print 'Server sends a complete file'
      self.Response = Response.DataResponse

      size = int( self.args( 'Content-Length' ) or -1 )
      self.open( size )

    elif status == '206' and self.partial():

      range = self.args( 'Content-Range' )
      assert range, 'invalid 206 response: no content-range specified'
      assert range.startswith( 'bytes ' ), 'invalid content-range %r' % range
      range, size = range[ 6: ].split( '/' )
      beg, end = range.split( '-' )
      size = int( size )
      beg = int( beg )
      end = int( end )
      assert size == end + 1

      print 'Server resumes transfer from byte', beg
      self.Response = Response.DataResponse

      self.open( size, beg )

    elif status == '304' and self.incache():

      print 'Cache is up to date'
      self.Response = Response.DataResponse

      self.__socket.close()
      self.open()

    else:

      print 'Forwarding response unchanged'
      self.Response = Response.BasicResponse

  def socket( self ):

    return self.__socket

  def cansend( self ):

    return self.__strbuf != ''

  def canjoin( self ):

    return True

    # TODO: fix re-enable joined downloads


class FtpProtocol( Util.Cache ):

  # NOTE: in current state completely broken

  Response = None

  def __init__( self, request ):

    Util.Cache.__init__( self, request )

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

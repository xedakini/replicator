import Params, Protocol, os, time, socket


class HttpRequest:

  Protocol = None

  def __init__( self ):

    self.__body = ''
    self.__size = -1
    self.__head = None
    self.__args = {}

  def recv( self, sock ):

    assert not self.Protocol, 'recv called after request is done'

    chunk = sock.recv( Params.MAXCHUNK )
    assert chunk, 'client connection closed before sending a complete header'
    self.__body += chunk

    if self.__size == -1:
      while '\n' in self.__body:
        line, self.__body = self.__body.split( '\n', 1 )
        if line == '\r' or line == '\r\n':
          break
        elif not self.__head:
          self.__head = line.split()
          assert len( self.__head ) == 3, 'invalid head %r' % line
        elif ':' in line:
          key, value = line.split( ':', 1 )
          self.__args[ key.title() ] = value.strip()
        else:
          print 'Ignored invalid header line %r' % line
      else:
        return
      if Params.VERBOSE > 1:
        print '\n > '.join( [ 'Received from client:', ' '.join( self.__head ) ] + map( ': '.join, self.__args.items() ) )
      self.__size = int( self.__args.get( 'Content-Length', 0 ) )
      if self.__head[ 0 ] != 'POST':
        assert not self.__size, '%s request has message body' % self.__head[ 0 ]

    if len( self.__body ) < self.__size:
      return

    assert len( self.__body ) == self.__size, 'request body exceeds content-length'

    url = self.__head[ 1 ]
    if url.startswith( 'http://' ):
      url = url[ 7: ]
      if self.__head[ 0 ] == 'GET':
        self.Protocol = Protocol.HttpProtocol
      else:
        self.Protocol = Protocol.BlindHttpProtocol
      self.__port = 80
    elif url.startswith( 'ftp://' ):
      url = url[ 6: ]
      assert self.__head[ 0 ] == 'GET', 'unsupported ftp operation: %s' % self.__head[ 0 ]
      self.Protocol = Protocol.FtpProtocol
      self.__port = 21
    else:
      raise AssertionError, 'invalid url: %s' % url

    sep = url.find( '/' )
    if sep == -1:
      url += '/'
    self.__host, url = url[ :sep ], url[ sep: ]
    sep = self.__host.find( ':' )
    if sep != -1:
      self.__host, self.__port = self.__host[ :sep ], int( self.__host[ sep+1: ] )

    if issubclass( self.Protocol, Protocol.TransferProtocol ):
      self.__path = '%s:%i%s' % ( self.__host, self.__port, url )
      sep = self.__path.find( '?' )
      if sep != -1:
        self.__path = self.__path[ :sep ] + self.__path[ sep: ].replace( '/', '%2F' )
      if Params.VERBOSE > 1:
        print 'Cache position:', self.__path
      if Params.STATIC and os.path.isfile( Params.ROOT + self.__path ):
        self.Protocol = Protocol.StaticProtocol
    else:
      self.__path = None

    self.__head[ 1 ] = url
    self.__args[ 'Host' ] = '%s:%i' % ( self.__host, self.__port )
    self.__args[ 'Connection' ] = 'close'
    self.__args[ 'Date' ] = time.strftime( Params.TIMEFMT, time.gmtime() )
    self.__args.pop( 'Keep-Alive', None )
    self.__args.pop( 'Accept-Encoding', None )
    self.__args.pop( 'Proxy-Connection', None )
    self.__args.pop( 'Proxy-Authorization', None )

  def __hash__( self ):

    assert self.Protocol, '__hash__ called before request is done'

    return hash( self.__path )

  def __eq__( self, other ):

    assert self.Protocol, '__eq__ called before request is done'

    return self.__path and self.__path == other.__path

  def getall( self ):

    assert self.Protocol, 'getrequest called before request is done'

    return self.__head[ : ], self.__args.copy(), self.__body

  def getarg( self, key ):

    assert self.Protocol, 'getrequest called before request is done'

    return self.__args.get( key )

  def getpath( self ):

    assert self.Protocol, 'getpath called before request is done'

    return self.__path

  def getsocket( self ):

    assert self.Protocol, 'getsocket called before request is done'

    addrinfo = socket.getaddrinfo( self.__host, self.__port, Params.FAMILY, socket.SOCK_STREAM )
    family, socktype, proto, canonname, sockaddr = addrinfo[ 0 ]
    sock = socket.socket( family, socktype, proto )
    sock.setblocking( 0 )
    sock.connect_ex( sockaddr )

    print 'Connecting to', self.__host, '(%s:%i)' % sockaddr

    return sock

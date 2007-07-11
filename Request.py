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
      port = 80
    elif url.startswith( 'ftp://' ):
      url = url[ 6: ]
      assert self.__head[ 0 ] == 'GET', 'unsupported ftp operation: %s' % self.__head[ 0 ]
      self.Protocol = Protocol.FtpProtocol
      port = 21
    else:
      raise AssertionError, 'invalid url: %s' % url

    sep = url.find( '/' )
    if sep == -1:
      url += '/'
    host, url = url[ :sep ], url[ sep: ]
    sep = host.find( ':' )
    if sep != -1:
      host, port = host[ :sep ], int( host[ sep+1: ] )

    self.__addr = host, port
    self.__head[ 1 ] = url
    self.__head[ 2 ] = 'HTTP/1.1'
    self.__args[ 'Host' ] = '%s:%i' % self.__addr
    self.__args[ 'Connection' ] = 'close'
    self.__args[ 'Date' ] = time.strftime( Params.TIMEFMT, time.gmtime() )
    self.__args.pop( 'Keep-Alive', None )
    self.__args.pop( 'Accept-Encoding', None )
    self.__args.pop( 'Proxy-Connection', None )
    self.__args.pop( 'Proxy-Authorization', None )

  def __hash__( self ):

    assert self.Protocol, '__hash__ called before request is done'

    return hash( self.__head[ 1 ] )

  def __eq__( self, other ):

    assert self.Protocol, '__eq__ called before request is done'

    return self.__addr == other.__addr and self.__head == other.__head

  def gethead( self, index = None ):

    assert self.Protocol, 'gethead called before request is done'

    if index is not None:
      return self.__head[ index ]

    return self.__head[ : ]

  def getargs( self, key = None ):

    assert self.Protocol, 'getargs called before request is done'

    if key is not None:
      return self.__args.get( key )

    return self.__args.copy()

  def getbody( self ):

    assert self.Protocol, 'getbody called before request is done'

    return self.__body

  def getsocket( self ):

    assert self.Protocol, 'getsocket called before request is done'

    addrinfo = socket.getaddrinfo( self.__addr[ 0 ], self.__addr[ 1 ], Params.FAMILY, socket.SOCK_STREAM )
    family, socktype, proto, canonname, sockaddr = addrinfo[ 0 ]
    sock = socket.socket( family, socktype, proto )
    sock.setblocking( 0 )
    sock.connect_ex( sockaddr )

    print 'Connecting to', self.__addr[ 0 ], '(%s:%i)' % sockaddr

    return sock

import Util, Params, Protocol, os, time, socket


# Request
#
# Handles http client request
#
# * << - None; receive data from client
# * getprotocol - Protocol; initial server communication
# * gethead - Http; client http header
# * getbody - str; client http body
# * getpath - str; cache path
# * getsocket - socket; server


class Request:

  def __notimpl( self, descr ):

    raise AssertionError, '%s not implemented in %s' % ( descr, self.__class__.__name__ )

  __nonzero__ = lambda self: self.__notimpl( 'stopcondition' )
  __rshift__  = lambda self, sock: self.__notimpl( 'sending' )
  __lshift__  = lambda self, sock: self.__notimpl( 'receiving' )
  getprotocol = lambda self: self.__notimpl( 'getprotocol' )
  gethead     = lambda self: self.__notimpl( 'gethead' )
  getbody     = lambda self: self.__notimpl( 'getbody' )
  getpath     = lambda self: self.__notimpl( 'getpath' )
  getsocket   = lambda self: self.__notimpl( 'getsocket' )


class Http( Request ):

  def __init__( self ):

    self.__strbuf = ''
    self.__size = -1

  def __nonzero__( self ):

    return len( self.__strbuf ) == self.__size

  def __lshift__( self, sock ):

    assert not self, '__lshift__ called after request is already complete'

    chunk = sock.recv( Params.MAXCHUNK )
    assert chunk, 'client connection closed before sending a complete header'
    self.__strbuf += chunk

    if self.__size == -1:
      try:
        self.__head = Util.Head( self.__strbuf )
      except Util.Head.ParseError:
        return
      if Params.VERBOSE:
        print 'Received from client:\n%r' % self.__head
      body = int( self.__head[ 'content-length' ] or 0 )
      if self.__head[ 0 ] != 'POST':
        assert not body, '%s request can not have a message body' % self.__head[ 0 ]
      self.__size = len( self.__head ) + body

    if len( self.__strbuf ) < self.__size:
      return

    assert self, 'request body exceeds content-length'

    url = self.__head[ 1 ]
    if url.startswith( 'http://' ):
      url = url[ 7: ]
      if self.__head[ 0 ] == 'GET':
        self.__protocol = Protocol.Http
      else:
        self.__protocol = Protocol.Blind
      self.__port = 80
    elif url.startswith( 'ftp://' ):
      url = url[ 6: ]
      assert self.__head[ 0 ] == 'GET', 'unsupported ftp operation: %s' % self.__head[ 0 ]
      self.__protocol = Protocol.Ftp
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

    if issubclass( self.__protocol, Protocol.Transfer ):
      self.__path = '%s:%i%s' % ( self.__host, self.__port, url )
      sep = self.__path.find( '?' )
      if sep != -1:
        self.__path = self.__path[ :sep ] #+ self.__path[ sep: ].replace( '/', '%2F' )
      print 'Cache position:', self.__path
      if Params.STATIC and os.path.isfile( Params.ROOT + self.__path ):
        self.__protocol = Protocol.Static
    else:
      self.__path = None

    self.__head[ 1 ] = url
    self.__head[ 'host' ] = '%s:%i' % ( self.__host, self.__port )
    self.__head[ 'keep-alive' ] = None
    self.__head[ 'accept-encoding' ] = None
    self.__head[ 'proxy-connection' ] = None
    self.__head[ 'proxy-authorization' ] = None
    self.__head[ 'connection' ] = 'close'
    self.__head[ 'date' ] = time.strftime( Params.TIMEFMT, time.gmtime() )

  def __hash__( self ):

    assert self, '__hash__ called before request is complete'

    return hash( self.__path )

  def __eq__( self, other ):

    assert self, '__eq__ called before request is complete'

    return self.__path and self.__path == other.__path

  def getprotocol( self ):

    assert self, 'getprotocol called before request is complete'

    if Params.VERBOSE:
      print 'Speaking', self.__protocol.__name__, 'on', self.__host

    return self.__protocol( self )

  def gethead( self ):

    assert self, 'getrequest called before request is complete'

    return self.__head

  def getbody( self ):

    assert self, 'getrequest called before request is complete'

    return self.__strbuf[ len( self.__head ): ]

  def getpath( self ):

    assert self, 'getpath called before request is complete'

    return self.__path

  def getsocket( self ):

    assert self, 'getsocket called before request is complete'

    addrinfo = socket.getaddrinfo( self.__host, self.__port, Params.FAMILY, socket.SOCK_STREAM )
    family, socktype, proto, canonname, sockaddr = addrinfo[ 0 ]
    sock = socket.socket( family, socktype, proto )
    sock.setblocking( 0 )
    sock.connect_ex( sockaddr )

    print 'Connecting to', self.__host, '(%s:%i)' % sockaddr

    return sock

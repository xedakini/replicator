import Params, Protocol, Util, socket


class HttpRequest( Util.Http ):

  Protocol = None

  def __init__( self ):

    Util.Http.__init__( self )

    self.__body = ''
    self.__size = -1

  def recv( self, sock ):

    assert not self.Protocol

    if self.__size == -1:

      if not self.recvhead( sock ):
        return

      head = self.head().split()
      assert len( head ) == 3, 'invalid header line'
      self.__cmd, self.__path, dummy = head
      self.__size = int( self.args( 'Content-Length' ) or 0 )
      if self.__cmd != 'POST':
        assert not self.__size, '%s request has message body' % self.__cmd
      elif self.__size > 0:
        return

    else:
        
      chunk = sock.recv( Params.MAXCHUNK )
      assert chunk, 'connection closed before sending a complete message body'
      self.__body += chunk
      if len( self.__body ) < self.__size:
        return

    assert len( self.__body ) == self.__size, 'message body exceeds content-length'

    if self.__path.startswith( 'http://' ):
      self.Protocol = Protocol.HttpProtocol
      self.__path = self.__path[ 7: ]
      self.__port = 80
    elif self.__path.startswith( 'ftp://' ):
      self.Protocol = Protocol.FtpProtocol
      self.__path = self.__path[ 6: ]
      self.__port = 21
    else:
      raise AssertionError, 'invalid url: %s' % url

    sep = self.__path.find( '/' )
    if sep == -1:
      self.__path += '/'
    self.__host, self.__path = self.__path[ :sep ], self.__path[ sep: ]

    sep = self.__host.find( ':' )
    if sep != -1:
      self.__host, self.__port = self.__host[ :sep ], int( self.__host[ sep+1: ] )

  def cmd( self ):

    assert self.Protocol
    return self.__cmd

  def addr( self ):

    assert self.Protocol
    return self.__host, self.__port

  def path( self ):

    assert self.Protocol
    return self.__path

  def body( self ):

    assert self.Protocol
    return self.__body

  def __hash__( self ):

    assert self.Protocol
    return hash( self.__path )

  def __eq__( self, other ):

    assert self.Protocol
    return ( self.__cmd, self.__host, self.__port, self.__path ) == ( other.__cmd, other.__host, other.__port, other.__path )

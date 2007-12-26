import Params, Protocol, socket, os


class HttpRequest:

  Protocol = None

  def __init__( self ):

    self.__recvbuf = ''
    self.__size = -1
    self.__body = None
    self.__cmd = None
    self.__path = None
    self.__args = {}

  def recv( self, sock ):

    assert not self.Protocol

    chunk = sock.recv( Params.MAXCHUNK )
    assert chunk, 'client closed connection before sending a complete message header'
    if self.__recvbuf:
      chunk = self.__recvbuf + chunk
      self.__recvbuf = ''

    for line in chunk.splitlines( True ):
      if self.__size != -1:
        assert self.__body, '%s request has message body' % self.__cmd
        self.__body.write( line )
        assert self.__body.tell() <= self.__size, 'message body exceeds content-length'
      elif line[ -1 ] != '\n':
        self.__recvbuf = line
      elif not self.__cmd:
        print 'Client sends', line.rstrip()
        fields = line.split()
        assert len( fields ) == 3, 'invalid header line: %r' % line.rstrip()
        self.__cmd, self.__path, dummy = fields
      elif line == '\n' or line == '\r\n':
        self.__size = int( self.__args.get( 'Content-Length', 0 ) )
        if self.__cmd == 'POST':
          if Params.VERBOSE:
            print 'Opening temporary file for POST upload'
          self.__body = os.tmpfile()
        else:
          assert not self.__size, '%s request announces message body' % self.__cmd
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

    if self.__size == -1 or self.__body and self.__body.tell() < self.__size:
      return

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

  def args( self, key = None, value = None ):

    if key is not None:
      return self.__args.get( key, value )

    return self.__args.copy()

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
    if self.__body:
      self.__body.seek( 0 )
      return self.__body.read()
    else:
      return ''

  def __hash__( self ):

    assert self.Protocol
    return hash( self.__path )

  def __eq__( self, other ):

    assert self.Protocol
    return ( self.__cmd, self.__host, self.__port, self.__path ) == ( other.__cmd, other.__host, other.__port, other.__path )

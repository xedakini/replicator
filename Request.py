import Params, Protocol, socket, os


class HttpRequest:

  Protocol = None

  def __init__( self ):

    self.__parse = self.__parse_head
    self.__recvbuf = ''

  def __parse_head( self, chunk ):

    eol = chunk.find( '\n' ) + 1
    if eol == 0:
      return 0

    line = chunk[ :eol ].rstrip()
    print 'Client sends', line
    fields = line.split()
    assert len( fields ) == 3, 'invalid header line: %r' % line
    self.__cmd, self.__path, dummy = fields
    self.__args = {}
    self.__parse = self.__parse_args

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
      self.__size = int( self.__args.get( 'Content-Length', 0 ) )
      if self.__cmd == 'POST':
        if Params.VERBOSE:
          print 'Opening temporary file for POST upload'
        self.__body = os.tmpfile()
        self.__parse = self.__parse_body
      else:
        assert not self.__size, '%s request announces message body' % self.__cmd
        self.__body = None
        self.__parse = None

    return eol

  def __parse_body( self, chunk ):

    self.__body.write( chunk )
    assert self.__body.tell() <= self.__size, 'message body exceeds content-length'
    if self.__body.tell() == self.__size:
      self.__parse = None

    return len( chunk )

  def recv( self, sock ):

    assert not self.Protocol

    chunk = sock.recv( Params.MAXCHUNK )
    assert chunk, 'client closed connection before sending a complete message header'
    chunk = self.__recvbuf + chunk
    while self.__parse:
      bytes = self.__parse( chunk )
      if not bytes:
        self.__recvbuf = chunk
        return
      chunk = chunk[ bytes: ]
    assert not chunk, 'client sends junk data after message header'

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
    request1 = self.__cmd,  self.__host,  self.__port,  self.__path
    request2 = other.__cmd, other.__host, other.__port, other.__path
    return request1 == request2

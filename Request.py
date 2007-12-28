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
    self.__recvbuf += chunk
    while self.__parse:
      bytes = self.__parse( self.__recvbuf )
      if not bytes:
        return
      self.__recvbuf = self.__recvbuf[ bytes: ]
    assert not self.__recvbuf, 'client sends junk data after message header'

    if self.__path.startswith( 'http://' ):
      self.__path = self.__path[ 7: ]
      self.__port = 80
      if self.__cmd == 'GET':
        self.Protocol = Protocol.HttpProtocol
      else:
        self.Protocol = Protocol.BlindProtocol
    elif self.__path.startswith( 'ftp://' ):
      assert self.__cmd == 'GET', '%s request unsupported for ftp' % self.__cmd
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

    self.__args[ 'Host' ] = self.__host
    self.__args[ 'Connection' ] = 'close'
    self.__args.pop( 'Keep-Alive', None )
    self.__args.pop( 'Proxy-Connection', None )
    self.__args.pop( 'Proxy-Authorization', None )

  def recvbuf( self ):

    assert self.Protocol
    lines = [ '%s %s HTTP/1.1' % ( self.__cmd, self.__path ) ]
    lines.extend( map( ': '.join, self.__args.items() ) )
    lines.append( '' )
    if self.__body:
      self.__body.seek( 0 )
      lines.append( self.__body.read() )
    else:
      lines.append( '' )

    return '\r\n'.join( lines )

  def args( self ):

    assert self.Protocol
    return self.__args.copy()

  def range( self ):

    range = self.__args.get( 'Range' )
    if not range:
      return 0, -1
    try:
      assert range.startswith( 'bytes=' )
      beg, end = range[ 6: ].split( '-' )
      if not beg:
        return int( end ), -1
      elif not end:
        return int( beg ), -1
      else:
        return int( beg ), int( end ) + 1
    except:
      raise AssertionError, 'invalid range specification: %s' % range

  def addr( self ):

    assert self.Protocol
    return self.__host, self.__port

  def path( self ):

    assert self.Protocol
    return self.__path

  def __hash__( self ):

    assert self.Protocol
    return hash( self.__path )

  def __eq__( self, other ):

    assert self.Protocol
    request1 = self.__cmd,  self.__host,  self.__port,  self.__path
    request2 = other.__cmd, other.__host, other.__port, other.__path
    return request1 == request2

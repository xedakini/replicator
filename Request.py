import Params, Protocol, socket, os, fiber


class HttpRequest:

  def __init__( self, client ):

    self.client = client

  def recv( self ):

    chunk = self.client.recv( Params.MAXCHUNK )
    assert chunk, 'client closed connection prematurely'
    return chunk

  def __iter__( self ):

    return self.__parse()

  def __parse( self ):

    recvbuf = b''
    while b'\n' not in recvbuf:
      yield fiber.RECV( self.client, Params.TIMEOUT )
      recvbuf += self.recv()
    header, recvbuf = recvbuf.split( b'\n', 1 )
    print('Client sends', header.rstrip().decode())

    self.__parse_header( header )

    args = {}
    while True:
      while b'\n' not in recvbuf:
        yield fiber.RECV( self.client, Params.TIMEOUT )
        recvbuf += self.recv()
      line, recvbuf = recvbuf.split( b'\n', 1 )
      if b':' in line:
        if Params.VERBOSE > 1:
          print('>', line.rstrip().decode())
        key, value = line.split( b':', 1 )
        key = key.title()
        assert key not in args, 'duplicate key: %s' % key
        args[ key ] = value.strip()
      elif line and line != b'\r':
        print('Ignored header line: %r' % line.rstrip())
      else:
        break

    self.__parse_args( args )

    if self.size:
      if Params.VERBOSE:
        print('Opening temporary file for POST upload')
      self.body = os.tmpfile()
      self.body.write( recvbuf )
      while self.body.tell() < self.size:
        yield fiber.RECV( self.client, Params.TIMEOUT )
        self.body.write( self.recv() )
      assert self.body.tell() == self.size, 'message body exceeds content-length'
    else:
      assert not recvbuf, 'client sends junk data'

  def __parse_header( self, line ):

    fields = line.split()
    assert len( fields ) == 3, 'invalid header line: %r' % line.rstrip()
    cmd, url, dummy = fields

    if url.startswith( b'http://' ):
      host = url[ 7: ]
      port = 80
      if cmd == b'GET':
        proto = Protocol.HttpProtocol
      else:
        proto = Protocol.BlindProtocol
    elif url.startswith( b'ftp://' ):
      assert cmd == b'GET', '%s request unsupported for ftp' % cmd
      proto = Protocol.FtpProtocol
      host = url[ 6: ]
      port = 21
    else:
      raise AssertionError('invalid url: %s' % url)

    if b'/' in host:
      host, path = host.split( b'/', 1 )
    else:
      path = b''

    if b':' in host:
      host, port = host.split( b':' )
      port = int( port )

    self.cmd = cmd
    self.addr = ( host, port )
    self.path = path
    self.cache = '%s:%i/%s' % ( host.decode(), port, path.decode() )
    self.Protocol = proto

  def __parse_args( self, args ):

    size = int( args.get( b'Content-Length', 0 ) )
    if size:
      assert self.cmd == b'POST', '%s request conflicts with message body' % self.cmd

    if b'Range' in args:
      try:
        rangestr = args[ b'Range' ]
        assert rangestr.startswith( b'bytes=' )
        beg, end = rangestr[ 6: ].split( b'-' )
        if not beg:
          range = int( end ), -1 # FIX!
        elif not end:
          range = int( beg ), -1
        else:
          range = int( beg ), int( end ) + 1
      except:
        raise AssertionError('invalid range specification: %s' % range)
    else:
      range = 0, -1

    args[ b'Host' ] = self.addr[ 0 ]
    args[ b'Connection' ] = b'close'
    args.pop( b'Keep-Alive', None )
    args.pop( b'Proxy-Connection', None )
    args.pop( b'Proxy-Authorization', None )

    self.args = args
    self.size = size
    self.range = range

  def recvbuf( self ):

    lines = [ b'%s /%s HTTP/1.1' % ( self.cmd, self.path ) ]
    lines.extend( list(map( b': '.join, self.args.items() )) )
    lines.append( b'' )
    if self.size:
      self.body.seek( 0 )
      lines.append( self.body.read() )
    else:
      lines.append( b'' )

    return b'\r\n'.join( lines )

  def __hash__( self ):

    return hash( self.cache )

  def __eq__( self, other ):

    assert self.cache == other.cache

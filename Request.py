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

    recvbuf = ''
    while '\n' not in recvbuf:
      yield fiber.RECV( self.client, Params.TIMEOUT )
      recvbuf += self.recv()
    header, recvbuf = recvbuf.split( '\n', 1 )
    print 'Client sends', header.rstrip()

    args = {}
    while True:
      while '\n' not in recvbuf:
        yield fiber.RECV( self.client, Params.TIMEOUT )
        recvbuf += self.recv()
      line, recvbuf = recvbuf.split( '\n', 1 )
      if ':' in line:
        if Params.VERBOSE > 1:
          print '>', line.rstrip()
        key, value = line.split( ':', 1 )
        key = key.title()
        assert key not in args, 'duplicate key: %s' % key
        args[ key ] = value.strip()
      elif line and line != '\r':
        print 'Ignored header line: %r' % line.rstrip()
      else:
        break

    self.__parse_header( header, args )
    self.__parse_args( args )

    if self.size:
      if Params.VERBOSE:
        print 'Opening temporary file for POST upload'
      self.body = os.tmpfile()
      self.body.write( recvbuf )
      while self.body.tell() < self.size:
        yield fiber.RECV( self.client, Params.TIMEOUT )
        self.body.write( self.recv() )
      assert self.body.tell() == self.size, 'message body exceeds content-length'
    else:
      assert not recvbuf, 'client sends junk data'

  def __parse_header( self, line, args=None ):

    if not args:
      args=dict()

    fields = line.split()
    assert len( fields ) == 3, 'invalid header line: %r' % line.rstrip()
    cmd, url, dummy = fields

    if url.startswith( 'http://' ):
      host = url[ 7: ]
      port = 80
      if cmd == 'GET':
        proto = Protocol.HttpProtocol
      else:
        proto = Protocol.BlindProtocol
    elif url.startswith( 'ftp://' ):
      assert cmd == 'GET', '%s request unsupported for ftp' % cmd
      proto = Protocol.FtpProtocol
      host = url[ 6: ]
      port = 21
    elif url.startswith('/'):
      # fallback - handling transparent proxy requests
      port = 80
      host = args.get('Host')
      if cmd == 'GET':
        proto = Protocol.HttpProtocol
      else:
        proto = Protocol.BlindProtocol      
    else:
      raise AssertionError, 'invalid url: %s' % url

    if '/' in host:
      host, path = host.split( '/', 1 )
    else:
      path = ''

    if ':' in host:
      host, port = host.split( ':' )
      port = int( port )

    self.cmd = cmd
    self.addr = ( host, port )
    self.path = path
    self.cache = '%s:%i/%s' % ( host, port, path )
    self.Protocol = proto

  def __parse_args( self, args ):

    size = int( args.get( 'Content-Length', 0 ) )
    if size:
      assert self.cmd == 'POST', '%s request conflicts with message body' % self.cmd

    if 'Range' in args:
      try:
        rangestr = args[ 'Range' ]
        assert rangestr.startswith( 'bytes=' )
        beg, end = rangestr[ 6: ].split( '-' )
        if not beg:
          range = int( end ), -1 # FIX!
        elif not end:
          range = int( beg ), -1
        else:
          range = int( beg ), int( end ) + 1
      except:
        raise AssertionError, 'invalid range specification: %s' % range
    else:
      range = 0, -1

    args[ 'Host' ] = self.addr[ 0 ]
    args[ 'Connection' ] = 'close'
    args.pop( 'Keep-Alive', None )
    args.pop( 'Proxy-Connection', None )
    args.pop( 'Proxy-Authorization', None )

    self.args = args
    self.size = size
    self.range = range

  def recvbuf( self ):

    lines = [ '%s /%s HTTP/1.1' % ( self.cmd, self.path ) ]
    lines.extend( map( ': '.join, self.args.items() ) )
    lines.append( '' )
    if self.size:
      self.body.seek( 0 )
      lines.append( self.body.read() )
    else:
      lines.append( '' )

    return '\r\n'.join( lines )

  def __hash__( self ):

    return hash( self.cache )

  def __eq__( self, other ):

    assert self.cache == other.cache
    

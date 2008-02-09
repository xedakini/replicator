import Params, time, traceback


class BlindResponse:

  Done = False

  def __init__( self, protocol, request ):

    self.__sendbuf = protocol.recvbuf()

  def hasdata( self ):

    return bool( self.__sendbuf )

  def send( self, sock ):

    assert not self.Done
    bytes = sock.send( self.__sendbuf )
    self.__sendbuf = self.__sendbuf[ bytes: ]

  def needwait( self ):

    return False

  def recv( self, sock ):

    assert not self.Done
    chunk = sock.recv( Params.MAXCHUNK )
    if chunk:
      self.__sendbuf += chunk
    elif not self.__sendbuf:
      self.Done = True


class DataResponse:

  Done = False

  def __init__( self, protocol, request ):

    self.__protocol = protocol
    self.__pos, self.__end = request.range
    if self.__end == -1:
      self.__end = self.__protocol.size

    try:
      args = self.__protocol.args()
    except:
      args = {}
    args[ 'Connection' ] = 'close'
    args[ 'Date' ] = time.strftime( Params.TIMEFMT, time.gmtime() )
    if self.__protocol.mtime >= 0:
      args[ 'Last-Modified' ] = time.strftime( Params.TIMEFMT, time.gmtime( self.__protocol.mtime ) )
    if self.__pos == 0 and self.__end == self.__protocol.size:
      head = 'HTTP/1.1 200 OK'
      if self.__protocol.size >= 0:
        args[ 'Content-Length' ] = str( self.__protocol.size )
    elif self.__end >= 0:
      head = 'HTTP/1.1 206 Partial Content'
      args[ 'Content-Length' ] = str( self.__end - self.__pos )
      if self.__protocol.size >= 0:
        args[ 'Content-Range' ] = 'bytes %i-%i/%i' % ( self.__pos, self.__end - 1, self.__protocol.size )
      else:
        args[ 'Content-Range' ] = 'bytes %i-%i/*' % ( self.__pos, self.__end - 1 )
    else:
      head = 'HTTP/1.1 416 Requested Range Not Satisfiable'
      args[ 'Content-Range' ] = 'bytes */*'
      args[ 'Content-Length' ] = '0'

    print 'Replicator responds', head
    if Params.VERBOSE > 1:
      for key in args:
        print '> %s: %s' % ( key, args[ key ].replace( '\r\n', ' > ' ) )

    self.__sendbuf = '\r\n'.join( [ head ] + map( ': '.join, args.items() ) + [ '', '' ] )
    if Params.LIMIT:
      self.__nextrecv = 0

  def hasdata( self ):

    if self.__sendbuf:
      return True
    elif self.__pos >= self.__protocol.tell():
      return False
    elif self.__pos < self.__end or self.__end == -1:
      return True
    else:
      return False

  def send( self, sock ):

    assert not self.Done
    if self.__sendbuf:
      bytes = sock.send( self.__sendbuf )
      self.__sendbuf = self.__sendbuf[ bytes: ]
    else:
      bytes = Params.MAXCHUNK
      if 0 <= self.__end < self.__pos + bytes:
        bytes = self.__end - self.__pos
      chunk = self.__protocol.read( self.__pos, bytes )
      self.__pos += sock.send( chunk )
    self.Done = not self.__sendbuf and ( self.__pos >= self.__protocol.size >= 0 or self.__pos >= self.__end >= 0 )

  def needwait( self ):

    return Params.LIMIT and max( self.__nextrecv - time.time(), 0 )

  def recv( self, sock ):

    assert not self.Done
    chunk = sock.recv( Params.MAXCHUNK )
    if chunk:
      self.__protocol.write( chunk )
      if Params.LIMIT:
        self.__nextrecv = time.time() + len( chunk ) / Params.LIMIT
    else:
      if self.__protocol.size >= 0:
        assert self.__protocol.size == self.__protocol.tell(), 'connection closed prematurely'
      else:
        self.__protocol.size = self.__protocol.tell()
        print 'Connection closed at byte', self.__protocol.size
      self.Done = not self.hasdata()


class ChunkedDataResponse( DataResponse ):

  def __init__( self, protocol, request ):

    DataResponse.__init__( self, protocol, request )
    self.__protocol = protocol
    self.__recvbuf = ''

  def recv( self, sock ):

    assert not self.Done
    chunk = sock.recv( Params.MAXCHUNK )
    assert chunk, 'chunked data error: connection closed prematurely'
    self.__recvbuf += chunk
    while '\r\n' in self.__recvbuf:
      head, tail = self.__recvbuf.split( '\r\n', 1 )
      chunksize = int( head.split( ';' )[ 0 ], 16 )
      if chunksize == 0:
        self.__protocol.size = self.__protocol.tell()
        print 'Connection closed at byte', self.__protocol.size
        self.Done = not self.hasdata()
        return
      if len( tail ) < chunksize + 2:
        return
      assert tail[ chunksize:chunksize+2 ] == '\r\n', 'chunked data error: chunk does not match announced size'
      if Params.VERBOSE > 1:
        print 'Received', chunksize, 'byte chunk'
      self.__protocol.write( tail[ :chunksize ] )
      self.__recvbuf = tail[ chunksize+2: ]


class DirectResponse:

  Done = False

  def __init__( self, status, request ):

    lines = [ 'HTTP Replicator: %s' % status, '', 'Requesting:' ]
    head, body = request.recvbuf().split( '\r\n\r\n', 1 )
    for line in head.splitlines():
      lines.append( len( line ) > 78 and '  %s...' % line[ :75 ] or '  %s' % line )
    if body:
      lines.append( '+ Body: %i bytes' % len( body ) )
    lines.append( '' )
    lines.append( traceback.format_exc() )

    self.__sendbuf = 'HTTP/1.1 %s\r\nContent-Type: text/plain\r\n\r\n%s' % ( status, '\n'.join( lines ) )
    
  def hasdata( self ):

    return bool( self.__sendbuf )

  def send( self, sock ):

    assert not self.Done
    bytes = sock.send( self.__sendbuf )
    self.__sendbuf = self.__sendbuf[ bytes: ]
    if not self.__sendbuf:
      self.Done = True

  def needwait( self ):

    return False

  def recv( self ):

    raise AssertionError


class NotFoundResponse( DirectResponse ):

  def __init__( self, protocol, request ):

    DirectResponse.__init__( self, '404 Not Found', request )


class ExceptionResponse( DirectResponse ):

  def __init__( self, request ):

    traceback.print_exc()
    DirectResponse.__init__( self, '500 Internal Server Error', request )

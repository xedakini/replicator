import Params, time, traceback, logging


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
    args[ b'Connection' ] = b'close'
    args[ b'Date' ] = time.strftime( Params.TIMEFMT[0], time.gmtime() ).encode()
    if self.__protocol.mtime >= 0:
      args[ b'Last-Modified' ] = time.strftime( Params.TIMEFMT[0], time.gmtime( self.__protocol.mtime ) ).encode()
    if self.__pos == 0 and self.__end == self.__protocol.size:
      head = b'HTTP/1.1 200 OK'
      if self.__protocol.size >= 0:
        args[ b'Content-Length' ] = b'%i' % (self.__protocol.size)
    elif self.__end >= 0:
      head = b'HTTP/1.1 206 Partial Content'
      args[ b'Content-Length' ] = b'%i' % (self.__end - self.__pos)
      if self.__protocol.size >= 0:
        args[ b'Content-Range' ] = b'bytes %i-%i/%i' % ( self.__pos, self.__end - 1, self.__protocol.size )
      else:
        args[ b'Content-Range' ] = b'bytes %i-%i/*' % ( self.__pos, self.__end - 1 )
    else:
      head = b'HTTP/1.1 416 Requested Range Not Satisfiable'
      args[ b'Content-Range' ] = b'bytes */*'
      args[ b'Content-Length' ] = b'0'

    logging.info(f'Replicator responds {head.decode()}')
    if logging.root.getEffectiveLevel() < logging.INFO:
      for key in args:
        logging.debug('> %s: %s', key.decode(), args[key].replace(b'\r\n', b' > ').decode())

    self.__sendbuf = b'\r\n'.join( [ head ] + list(map( b': '.join, iter(args.items()) )) + [ b'', b'' ] )
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
        logging.info(f'Connection closed at byte {self.__protocol.size}')
      self.Done = not self.hasdata()


class ChunkedDataResponse( DataResponse ):

  def __init__( self, protocol, request ):

    DataResponse.__init__( self, protocol, request )
    self.__protocol = protocol
    self.__recvbuf = b''

  def recv( self, sock ):

    assert not self.Done
    chunk = sock.recv( Params.MAXCHUNK )
    assert chunk, 'chunked data error: connection closed prematurely'
    self.__recvbuf += chunk
    while b'\r\n' in self.__recvbuf:
      head, tail = self.__recvbuf.split( b'\r\n', 1 )
      chunksize = int( head.split( b';' )[ 0 ], 16 )
      if chunksize == 0:
        self.__protocol.size = self.__protocol.tell()
        logging.info(f'Connection closed at byte {self.__protocol.size}')
        self.Done = not self.hasdata()
        return
      if len( tail ) < chunksize + 2:
        return
      assert tail[ chunksize:chunksize+2 ] == b'\r\n', 'chunked data error: chunk does not match announced size'
      logging.debug(f'Received {chunksize} byte chunk')
      self.__protocol.write( tail[ :chunksize ] )
      self.__recvbuf = tail[ chunksize+2: ]


class DirectResponse:

  Done = False

  def __init__( self, status, request ):

    lines = [ b'HTTP Replicator: %s' % status, b'', b'Requesting:' ]
    head, body = request.recvbuf().split( b'\r\n\r\n', 1 )
    for line in head.splitlines():
      lines.append( len( line ) > 78 and b'  %s...' % line[ :75 ] or b'  %s' % line )
    if body:
      lines.append( b'+ Body: %i bytes' % len( body ) )
    lines.append( b'' )
    lines.append( traceback.format_exc().encode() )

    self.__sendbuf = b'HTTP/1.1 %s\r\nContent-Type: text/plain\r\n\r\n%s' % ( status, b'\n'.join( lines ) )

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

    DirectResponse.__init__( self, b'404 Not Found', request )


class ExceptionResponse( DirectResponse ):

  def __init__( self, request ):
    logging.exception('ExceptionResponse invoked')
    DirectResponse.__init__( self, b'500 Internal Server Error', request )

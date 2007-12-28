import Params, time


class BlindResponse:

  Done = False

  def __init__( self, protocol, request ):

    self.__sendbuf = protocol.recvbuf()

  def cansend( self ):

    return bool( self.__sendbuf )

  def send( self, sock ):

    bytes = sock.send( self.__sendbuf )
    self.__sendbuf = self.__sendbuf[ bytes: ]

  def canrecv( self ):

    return True

  def recv( self, sock ):

    chunk = sock.recv( Params.MAXCHUNK )
    if chunk:
      self.__sendbuf += chunk
    elif not self.__sendbuf:
      self.Done = True


class DataResponse:

  Done = False

  def __init__( self, protocol, request ):

    self.__protocol = protocol
    self.__pos, self.__end = request.range()
    if self.__end == -1:
      self.__end = self.__protocol.size

    args = self.__protocol.args()
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

    if Params.VERBOSE > 0:
      print 'Sending', head
      if Params.VERBOSE > 1:
        for item in args.items():
          line = '%s: %s' % item
          eol = line[ :78 ].find( '\r' )
          print '>', eol != -1 and line[ :eol ] + '...' or len( line ) > 80 and line[ :77 ] + '...' or line

    self.__sendbuf = '\r\n'.join( [ head ] + map( ': '.join, args.items() ) + [ '', '' ] )

  def cansend( self ):

    if self.__sendbuf:
      return True
    elif self.__pos >= self.__protocol.tell():
      return False
    elif self.__pos < self.__end or self.__end == -1:
      return True
    else:
      return False

  def send( self, sock ):

    if self.__sendbuf:
      bytes = sock.send( self.__sendbuf )
      self.__sendbuf = self.__sendbuf[ bytes: ]
    else:
      bytes = Params.MAXCHUNK
      if 0 <= self.__end < self.__pos + bytes:
        bytes = self.__end - self.__pos
      chunk = self.__protocol.read( self.__pos, bytes )
      self.__pos += sock.send( chunk )

    self.Done = not self.__sendbuf and self.__pos >= self.__end >= 0

  def canrecv( self ):

    return True

  def recv( self, sock ):

    chunk = sock.recv( Params.MAXCHUNK )
    if chunk:
      self.__protocol.write( chunk )
    elif self.__protocol.size == -1:
      self.__protocol.size = self.__protocol.tell()
      print 'Connection closed at size', self.__protocol.size

    self.Done = not self.__sendbuf and self.__pos >= self.__end >= 0


class ChunkedDataResponse( DataResponse ):

  def __init__( self, protocol, request ):

    DataResponse.__init__( self, protocol, request )
    self.__protocol = protocol
    self.__recvbuf = ''

  def recv( self, sock ):

    chunk = sock.recv( Params.MAXCHUNK )
    self.__recvbuf += chunk
    beg = self.__recvbuf.find( '\n' ) + 1
    if not beg:
      assert chunk, 'chunked data error: connection closed waiting for header'
      return
    end = beg + int( self.__recvbuf[ :beg ].split( ';' )[ 0 ], 16 )
    if len( self.__recvbuf ) < end + 2:
      assert chunk, 'chunked data error: connection closed waiting for data'
      return
    assert self.__recvbuf[ end:end+2 ] == '\r\n', 'chunked data error: chunk does not match announced size'
    if Params.VERBOSE:
      print 'Received', end - beg, 'byte chunk'

    if end > beg:
      self.__protocol.write( self.__recvbuf[ beg:end ] )
      self.__recvbuf = self.__recvbuf[ end+2: ]
    else:
      self.__protocol.size = self.__protocol.tell()
      print 'Connection closed at byte', self.__protocol.size
      self.Done = not self.cansend()


class DirectResponse:

  Done = False

  def __init__( self, sendbuf ):

    self.__sendbuf = sendbuf

  def cansend( self ):

    return bool( self.__sendbuf )

  def send( self, sock ):

    bytes = sock.send( self.__sendbuf )
    self.__sendbuf = self.__sendbuf[ bytes: ]
    if not self.__sendbuf:
      self.Done = True


class NotFoundResponse( DirectResponse ):

  def __init__( self, protocol, request ):

    DirectResponse.__init__( self, 'HTTP/1.1 404 Not Found\r\n\r\n' )


class ExceptionResponse( DirectResponse ):

  def __init__( self, msg ):

    DirectResponse.__init__( self, 'HTTP/1.1 500 Internal Server Error\r\n\r\nHTTP Replicator caught an exception: %s' % msg )
    print 'Exception:', msg

import Params, time, sys, traceback


class BasicResponse:

  Done = False

  def __init__( self, protocol, request ):

    self.__strbuf = '\r\n'.join( [ protocol.head() ] + map( ': '.join, protocol.args().items() ) + [ '', '' ] )

  def send( self, sock ):

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]

  def recv( self, sock ):

    chunk = sock.recv( Params.MAXCHUNK )
    if chunk:
      self.__strbuf += chunk
    elif not self.__strbuf:
      self.Done = True

  def cansend( self ):

    return bool( self.__strbuf )

  def canrecv( self ):

    return True


class DataResponse:

  Done = False

  def __init__( self, protocol, request ):

    args = protocol.args()
    size = protocol.size()

    range = request.args( 'Range' )
    if range:
      assert range.startswith( 'bytes=' )
      sep = range.find( '-', 6 )
      beg = int( range[ 6:sep  ] or 0 )
      end = int( range[ sep+1: ] or 0 )
      if end and not beg:
        print 'Requested last', end, 'bytes'
        self.__pos = size - end
        self.__end = 0
      else:
        print 'Requested byte', beg, 'to', end or 'end'
        self.__pos = beg
        self.__end = end
    else:
      self.__pos = 0
      self.__end = size

    if self.__pos == 0 and self.__end == size:
      head = 'HTTP/1.1 200 OK'
      if size >= 0:
        args[ 'Content-Length' ] = str( size )
    elif 0 <= self.__pos <= self.__end <= size:
      head = 'HTTP/1.1 206 Partial Content'
      args[ 'Content-Range' ] = 'bytes %i-%i/%i' % ( self.__pos, self.__end - 1, size )
      args[ 'Content-Length' ] = str( self.__end - self.__pos )
    else:
      head = 'HTTP/1.1 416 Requested Range Not Satisfiable'
      if size >= 0:
        args[ 'Content-Range' ] = 'bytes */%i' % size
      else:
        args[ 'Content-Range' ] = 'bytes */*'
      args[ 'Content-Length' ] = '0'
      self.__pos = self.__end = 0

    args[ 'Connection' ] = 'close'
    args[ 'Date' ] = time.strftime( Params.TIMEFMT, time.gmtime() )

    if Params.VERBOSE > 0:
      print 'Sending', head
      if Params.VERBOSE > 1:
        for item in args.items():
          print '<', ': '.join( item )

    self.__strbuf = '\r\n'.join( [ head ] + map( ': '.join, args.items() ) + [ '', '' ] )
    self.__file = protocol.file()

  def send( self, sock ):

    if self.__strbuf:
      bytes = sock.send( self.__strbuf )
      self.__strbuf = self.__strbuf[ bytes: ]
    else:
      self.__file.seek( self.__pos )
      bytes = Params.MAXCHUNK
      if 0 <= self.__end < self.__pos + bytes:
        bytes = self.__end - self.__pos
      chunk = self.__file.read( bytes )
      self.__pos += sock.send( chunk )
      self.Done = ( self.__pos >= self.__end )

  def recv( self, sock ):

    chunk = sock.recv( Params.MAXCHUNK )
    self.__file.seek( 0, 2 )
    if chunk:
      self.__file.write( chunk )
    else:
      if self.__end == -1:
        self.__end = self.__file.tell()
      else:
        assert self.__end == self.__file.tell(), 'connection closed too early'
      self.Done = ( self.__pos >= self.__end )

  def cansend( self ):

    if self.__strbuf:
      return True

    self.__file.seek( 0, 2 )
    return self.__pos < self.__file.tell()

  def canrecv( self ):

    return True


class NotFoundResponse:

  Done = False

  def __init__( self, protocol, request ):

    self.__strbuf = 'HTTP/1.1 404 Not Found\r\n\r\n'

  def send( self, sock ):

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]
    if not self.__strbuf:
      self.Done = True

  def cansend( self ):

    return bool( self.__strbuf )


class ExceptionResponse:

  Done = False

  def __init__( self ):

    head = 'HTTP/1.1 500 Internal Server Error\r\n\r\n'
    body = traceback.format_exception( sys.exc_type, sys.exc_value, sys.exc_traceback )

    self.__strbuf = head + '\n'.join( body )

    print ''.join( traceback.format_exception( sys.exc_type, sys.exc_value, sys.exc_traceback ) ).rstrip()

  def send( self, sock ):

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]
    if not self.__strbuf:
      self.Done = True

  def cansend( self ):

    return bool( self.__strbuf )

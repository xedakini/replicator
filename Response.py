import Params, time, sys, traceback


class BlindResponse:

  Done = False

  def __init__( self, protocol, request ):

    print 'Sending unmodified response'

    self.__strbuf = ''
    self.__closed = False

  def send( self, sock ):

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]
    if self.__closed and not self.__strbuf:
      self.Done = True

  def recv( self, sock ):

    chunk = sock.recv( Params.MAXCHUNK )
    if chunk:
      self.__strbuf += chunk
    elif self.__strbuf:
      self.__closed = True
    else:
      self.Done = True

  def cansend( self ):

    return bool( self.__strbuf )

  def canrecv( self ):

    return True


class CacheResponse:

  Done = False

  def __init__( self, protocol, request ):

    size = protocol.getsize()
    range = request.getarg( 'Range' )
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
      lines = [ 'HTTP/1.1 200 OK' ]
      if size >= 0:
        lines.append( 'Content-Length: %i' % size )
    elif 0 <= self.__pos <= self.__end <= size:
      lines = [ 'HTTP/1.1 206 Partial Content' ]
      lines.append( 'Content-Range: bytes %i-%i/%i' % ( self.__pos, self.__end - 1, size ) )
      lines.append( 'Content-Length: %i' % ( self.__end - self.__pos ) )
    else:
      lines = [ 'HTTP/1.1 416 Requested Range Not Satisfiable' ]
      if size >= 0:
        lines.append( 'Content-Range: bytes */%i' % size )
      else:
        lines.append( 'Content-Range: bytes */*' )
      lines.append( 'Content-Length: 0' )
      self.__pos = self.__end = 0

    lines.append( 'Connection: close' )
    lines.append( 'Date: %s' % time.strftime( Params.TIMEFMT, time.gmtime() ) )

    if Params.VERBOSE > 1:
      print '\n > '.join( [ 'Sending to client:' ] + lines )

    self.__strbuf = '\r\n'.join( lines + [ '', '' ] )
    self.__file = protocol.getfile()

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
      if self.__pos == self.__end:
        self.Done = True

  def recv( self, sock ):

    chunk = sock.recv( Params.MAXCHUNK )
    self.__file.seek( 0, 2 )
    if chunk:
      self.__file.write( chunk )
    elif self.__end == -1:
      self.__end = self.__file.tell()
    else:
      assert self.__end == self.__file.tell(), 'connection closed too early'

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

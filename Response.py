import Util, Params, time, sys, traceback


class Response:

  def __nonzero__( self ):
    '''\
    True iff all data has been transfered to the client.'''

    raise 'stopcriterium not implemented'

  def send( self, client ):
    '''\
    No return. Sends data to client socket.'''

    raise 'send not implemented'

  def recv( self, server ):
    '''\
    No return. Receives data from server socket.'''

    raise 'recv not implemented'

  def cansend( self ):
    '''\
    True iff data is available for sending to client.'''

    raise 'cansend not implemented'

  def canrecv( self ):
    '''\
    True iff transfer rate allows data to be received from client.'''

    raise 'canrecv not implemented'


class BlindResponse( Response ):

  def __init__( self, protocol, request ):

    print 'Sending unmodified response'

    self.__strbuf = ''
    self.__closed = False
    self.__done = False

  def __nonzero__( self ):

    return self.__done

  def send( self, sock ):

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]
    if self.__closed and not self.__strbuf:
      self.__done = True

  def recv( self, sock ):

    chunk = sock.recv( Params.MAXCHUNK )
    if chunk:
      self.__strbuf += chunk
    elif self.__strbuf:
      self.__closed = True
    else:
      self.__done = True

  def cansend( self ):

    return bool( self.__strbuf )

  def canrecv( self ):

    return True


class CacheResponse( Response ):

  def __init__( self, protocol, request ):

    size = protocol.getsize()
    range = request.gethead()[ 'range' ]
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
      head = Util.Head( 'HTTP/1.1 200 OK\r\n\r\n' )
      head[ 'content-range' ] = None
      if size >= 0:
        head[ 'content-length' ] = str( size )
    elif 0 <= self.__pos <= self.__end <= size:
      head = Util.Head( 'HTTP/1.1 206 Partial Content\r\n\r\n' )
      head[ 'content-range' ] = 'bytes %i-%i/%s' % ( self.__pos, self.__end - 1, size )
      head[ 'content-length' ] = str( self.__end - self.__pos )
    else:
      head = Util.Head( 'HTTP/1.1 416 Requested Range Not Satisfiable\r\n\r\n' )
      if size >= 0:
        head[ 'content-range' ] = 'bytes */%s' % size
      else:
        head[ 'content-range' ] = 'bytes */*'
      head[ 'content-length' ] = '0'
      self.__pos = self.__end = 0

    head[ 'Connection' ] = 'close'
    head[ 'Date' ] = time.strftime( Params.TIMEFMT, time.gmtime() )

    if Params.VERBOSE:
      print 'Sending to client:\n%r' % head

    self.__strbuf = str( head )
    self.__file = protocol.getfile()

  def __nonzero__( self ):

    return not self.__strbuf and self.__pos == self.__end

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


class NotFoundResponse( Response ):

  def __init__( self, protocol, request ):

    self.__strbuf = 'HTTP/1.1 404 Not Found\r\n\r\n'
    self.__done = False

  def __nonzero__( self ):

    return self.__done

  def send( self, sock ):

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]
    if not self.__strbuf:
      self.__done = True

  def cansend( self ):

    return bool( self.__strbuf )


class ExceptionResponse( Response ):

  def __init__( self ):

    head = Util.Head( 'HTTP/1.1 500 Internal Server Error\r\n\r\n' )
    body = traceback.format_exception( sys.exc_type, sys.exc_value, sys.exc_traceback )

    self.__strbuf = str( head ) + '\n'.join( body )
    self.__done = True

    print ''.join( traceback.format_exception( sys.exc_type, sys.exc_value, sys.exc_traceback ) ).rstrip()

  def __nonzero__( self ):

    return self.__done

  def send( self, sock ):

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]
    if not self.__strbuf:
      self.__done = True

  def cansend( self ):

    return bool( self.__strbuf )

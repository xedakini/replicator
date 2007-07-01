import Util, Params, time, sys, traceback


class Response:

  '''
  Response

  * << - None; receive data from server
  * >> - None; send data to client
  * cansend - bool; data ready for sending
  * canrecv - bool; ready for next data chunk '''

  def __notimpl( self, descr ):

    raise AssertionError, '%s not implemented in %s' % ( descr, self.__class__.__name__ )

  __nonzero__ = lambda self: self.__notimpl( 'stopcondition' )
  __rshift__  = lambda self, sock: self.__notimpl( 'sending' )
  __lshift__  = lambda self, sock: self.__notimpl( 'receiving' )
  cansend     = lambda self: self.__notimpl( 'cansend' )
  canrecv     = lambda self: self.__notimpl( 'canrecv' )


class Blind( Response ):

  def __init__( self, protocol, request ):

    print 'Sending unmodified response'

    self.__strbuf = ''
    self.__closed = False
    self.__done = False

  def __nonzero__( self ):

    return self.__done

  def __rshift__( self, sock ):

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]
    if self.__closed and not self.__strbuf:
      self.__done = True

  def __lshift__( self, sock ):

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


class Cache( Response ):

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

  def __rshift__( self, sock ):

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

  def __lshift__( self, sock ):

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


class NotFound( Response ):

  def __init__( self, protocol, request ):

    self.__strbuf = 'HTTP/1.1 404 Not Found\r\n\r\n'
    self.__done = False

  def __nonzero__( self ):

    return self.__done

  def __rshift__( self, sock ):

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]
    if not self.__strbuf:
      self.__done = True

  def cansend( self ):

    return bool( self.__strbuf )


class Exception( Response ):

  def __init__( self ):

    head = Util.Head( 'HTTP/1.1 500 Internal Server Error\r\n\r\n' )
    body = traceback.format_exception( sys.exc_type, sys.exc_value, sys.exc_traceback )

    self.__strbuf = str( head ) + '\n'.join( body )
    self.__done = True

    print 'Exception:', sys.exc_value or sys.exc_type

  def __nonzero__( self ):

    return self.__done

  def __rshift__( self, sock ):

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]
    if not self.__strbuf:
      self.__done = True

  def cansend( self ):

    return bool( self.__strbuf )

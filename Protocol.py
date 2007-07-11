import Params, Response, os, sys, time, socket


class BlindHttpProtocol:

  Response = None

  def __init__( self, request ):

    print 'Using blind protocol'

    head = request.gethead()
    args = request.getargs()
    body = request.getbody()

    self.__strbuf = '\r\n'.join( [ ' '.join( head ) ] + map( ': '.join, args.items() ) + [ '', body ] )
    self.__socket = request.getsocket()

  def send( self, sock ):

    assert not self.Response, 'send called after protocol is done'

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]
    if not self.__strbuf:
      self.Response = Response.BlindResponse

  def getsocket( self ):

    return self.__socket

  def canjoin( self ):

    return False

  def cansend( self ):

    assert not self.Response, 'cansend called after protocol is done'

    return True


class Cache:

  def __init__( self, request ):

    path = request.getargs( 'Host' ) + request.gethead( 1 )
    sep = path.find( '?' )
    if sep != -1:
      path = path[ :sep ] + path[ sep: ].replace( '/', '%2F' )

    if Params.VERBOSE > 1:
      print 'Cache position:', path

    self.__file = None
    self.__path = Params.ROOT + path
    self.__partial = os.path.isfile( self.__path + Params.SUFFIX )
    self.__complete = not self.__partial and os.path.isfile( self.__path )

    if self.__partial or self.__complete:
      stat = os.stat( self.__partial and self.__path + Params.SUFFIX or self.__path )
      self.__size = stat.st_size
      self.__mtime = stat.st_mtime
      print self.__partial and 'Partial' or 'Complete', 'file in cache since', time.ctime( self.__mtime )

    # TODO: unknown file name

  def complete( self ):

    assert self.__file is None, 'complete called after file is opened'

    return self.__complete

  def partial( self ):

    assert self.__file is None, 'partial called after file is opened'

    return self.__partial

  def getmtime( self ):

    assert self.__file is None, 'getmtime called after file is opened'

    return self.__mtime

  def getsize( self ):

    return self.__size

  def getfile( self ):

    assert self.__file is not None, 'getfile called before file is opened'

    return self.__file

  def open( self, size = None, offset = None ):

    assert self.__file is None, 'open called twice'

    if offset is not None:
      assert self.__partial
      print 'Continuing previous download from byte', offset
      self.__file = open( self.__path + Params.SUFFIX, 'a+' )
      self.__file.seek( 0, 2 )
      assert offset <= self.__file.tell() < size, 'range does not match file in cache'
      self.__file.seek( offset )
      self.__file.truncate()
      self.__size = size
    elif size is not None:
      print 'Starting new download'
      self.__partial = True
      self.__makedirs( self.__path )
      self.__file = open( self.__path + Params.SUFFIX, 'w+' )
      self.__size = size
    else:
      print 'Serving file from cache'
      assert self.__complete
      self.__file = open( self.__path, 'r' )
      self.__file.seek( 0, 2 )
      assert self.__size == self.__file.tell(), 'file size changed mysteriously'

  def __makedirs( self, path ):

    dir = os.path.dirname( path )
    if dir and not os.path.isdir( dir ):
      if os.path.isfile( dir ):
        print 'directory %s mistaken for file' % dir
        os.remove( dir )
      else:
        self.__makedirs( dir )
      os.mkdir( dir )

  def __finalize( self ):

    if not self.__partial or self.__file is None:
      return

    self.__file.seek( 0, 2 )
    size = self.__file.tell()
    self.__file.close()

    if size != self.__size:
      print 'Wrong file size; removing file from cache'
      os.remove( self.__path + Params.SUFFIX )
      return

    print 'Finalizing', self.__path
    os.rename( self.__path + Params.SUFFIX, self.__path )

  def __del__( self ):

    try:
      self.__finalize()
    except:
      print 'Finalize error:', sys.exc_value or sys.exc_type


class HttpProtocol( Cache ):

  Response = None

  def __init__( self, request ):

    Cache.__init__( self, request )

    if Params.STATIC and self.complete():
      self.__socket = None
      self.open()
      self.Response = Response.CacheResponse
      return

    head = request.gethead()
    args = request.getargs()

    if self.complete():
      args[ 'If-Modified-Since' ] = time.strftime( Params.TIMEFMT, time.gmtime( self.getmtime() ) )
    elif self.partial():
      args[ 'If-Unmodified-Since' ] = time.strftime( Params.TIMEFMT, time.gmtime( self.getmtime() ) )
      args[ 'Range' ] = 'bytes=%i-' % self.getsize()

    if Params.VERBOSE > 1:
      print '\n > '.join( [ 'Sending to server:', ' '.join( head ) ] + map( ': '.join, args.items() ) )

    self.__strbuf = '\r\n'.join( [ ' '.join( head ) ] + map( ': '.join, args.items() ) + [ '', '' ] )
    self.__request = request
    self.__socket = request.getsocket()

  def send( self, sock ):

    assert self.cansend(), 'send called while no data to send'

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]

  def recv( self, sock ):

    assert not self.cansend(), 'recv called while still data to send'

    lines = sock.recv( Params.MAXCHUNK, socket.MSG_PEEK ).splitlines( True )
    headlen = len( lines[ 0 ] )
    head = lines.pop( 0 ).split()
    args = {}
    for line in lines:
      headlen += len( line )
      if line == '\r' or line == '\r\n':
        break
      elif ':' in line:
        key, value = line.split( ':', 1 )
        args[ key.title() ] = value.strip()
      else:
        print 'Ignored invalid header line %r' % line
    else:
      return

    if Params.VERBOSE > 1:
      print '\n > '.join( [ 'Received from server:', ' '.join( head ) ] + map( ': '.join, args.items() ) )

    if args.get( 'Transfer-Encoding' ) == 'chunked':

      print 'Chunked data; not cached'

      self.Response = Response.BlindResponse

    elif head[ 1 ] == '200':

      size = int( args.get( 'Content-Length', -1 ) )
      self.__socket.recv( headlen )
      self.open( size )
      self.Response = Response.CacheResponse

    elif head[ 1 ] == '206' and self.partial():

      range = args[ 'Content-Range' ]
      assert range.startswith( 'bytes ' ), 'invalid content-range'
      range, size = range[ 6: ].split( '/' )
      beg, end = range.split( '-' )
      size = int( size )
      beg = int( beg )
      end = int( end )
      assert size == end + 1

      self.__socket.recv( headlen )
      self.open( size, beg )
      self.Response = Response.CacheResponse

    elif head[ 1 ] == '304' and self.complete():

      self.__socket.close()
      self.open()
      self.Response = Response.CacheResponse

    elif head[ 1 ] == '412':
 
      print 'File has changed, resending request for complete file'

      head_ = request.gethead()
      args_ = request.getargs()

      head_.pop( 'Range', None )
      head_.pop( 'If-Unmodified-Since', None )

      if Params.VERBOSE > 1:
        print '\n > '.join( [ 'Sending to server:', ' '.join( head_ ) ] + map( ': '.join, args_.items() ) )

      self.__strbuf = '\r\n'.join( [ ' '.join( head_ ) ] + map( ': '.join, args_.items() ) + [ '', '' ] )
      self.__socket = self.__request.getsocket()
 
    else:

      self.Response = Response.BlindResponse

  def getsocket( self ):

    return self.__socket

  def cansend( self ):

    return self.__strbuf != ''

  def canjoin( self ):

    return False

    # TODO: fix re-enable joined downloads


class FtpProtocol( Cache ):

  # NOTE: in current state completely broken

  Response = None

  def __init__( self, request ):

    Cache.__init__( self, request )

    self.__socket = request.getsocket()
    self.__strbuf = ''

  def send( self, sock ):

    assert self.cansend(), '__rshift__ called while no data to send'

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]

  def recv( self, sock ):

    assert not self.cansend(), '__lshift__ called while still data to send'

    response = sock.recv( Params.MAXCHUNK, socket.MSG_PEEK )

    for line in response.splitlines( True ):
      if not line.endswith( '\n' ):
        return

      if Params.VERBOSE > 0:
        print '>', line.rstrip()

      sock.recv( len( line ) )

      if line[ 3 ] != '-':
        func = '__handle' + line[ :3 ]
        assert hasattr( self, func ), 'unknown response: %s' % line
        command = getattr( self, func )( line )
        if command:
          if Params.VERBOSE > 0:
            print 'Sending', command
          self.__strbuf = command + '\r\n'
        return

  def __handle220( self, line ):

    return 'USER anonymous'

  def __handle331( self, line ):

    return 'PASS anonymous@'

  def __handle230( self, line ):

    return 'TYPE I'

  def __handle200( self, line ):

    # switched to binary mode

    if self.hascache( partial=True ):
      mtime, size = self.getcache( partial=True )
      return 'REST %i' % size

  def __handle350( self, line ):

    return 'PASV'

  def __handle227( self, line ):

    # entered passive mode
    channel = eval( line.split()[ -1 ] )
    addr = '%i.%i.%i.%i' % channel[ :4 ], channel[ 4 ] * 256 + channel[ 5 ]
    print 'Connecting to %s:%i' % addr

    self.__datasocket = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
    self.__datasocket.setblocking( 0 )
    self.__datasocket.connect_ex( addr )

    return 'RETR ' + self.__path

  def __handle550( self, line ):

    print 'File not found'
    self.Response = Response.NotFoundResponse

  def __handle150( self, line ):

    # opening connection
    end = message.rfind( ' bytes)' )
    beg = message.rfind( '(', 0, end ) + 1
    if 0 < beg < end:
      size = int( message[ beg:end ] )
    else:
      size = -1

    self.setincache( partial=(beg,end) )

    self.Response = StreamBuffer
    self.__socket = self.__datasocket

  def getsocket( self ):

    return self.__socket

  def cansend( self ):

    return self.__strbuf != ''

  def canjoin( self ):

    return False

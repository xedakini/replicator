import Params, Response, os, sys, time, socket


class BlindHttpProtocol:

  Response = None

  def __init__( self, request ):

    print 'Using blind protocol'

    head, args, body = request.getall()

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


class StaticProtocol:

  Response = Response.CacheResponse

  def __init__( self, request ):

    print 'Using static protocol'

    self.__file = open( Params.ROOT + request.getpath(), 'r' )
    self.__file.seek( 0, 2 )

  def getsocket( self ):

    return None

  def getfile( self ):

    return self.__file
    
  def getsize( self ):
  
    return self.__file.tell()

  def canjoin( self ):

    return True


class TransferProtocol:

  Response = None

  def __init__( self, request ):

    self.__path = request.getpath()
    self.__partial = False

    # TODO: unknown file name

  def hasincache( self, partial ):

    path = Params.ROOT + self.__path
    if partial:
      path += Params.SUFFIX
    if os.path.isfile( path ):
      size = os.path.getsize( path )
      mtime = os.path.getmtime( path )
      return size, time.strftime( Params.TIMEFMT, time.gmtime( mtime ) )
    else:
      return False

  def setincache( self, partial ):

    path = Params.ROOT + self.__path
    if partial:
      path += Params.SUFFIX
      beg, end = partial
      if beg > 0:
        print 'Continuing previous download'
        self.__file = open( path, 'a+' )
        self.__file.seek( 0, 2 )
        assert beg <= self.__file.tell() < end, 'insufficient range'
        self.__file.seek( beg )
        self.__file.truncate()
      else:
        print 'Downloading file'
        self.__makedirs( path )
        self.__file = open( path, 'w+' )
      self.__size = end
      self.__partial = True
    else:
      print 'Serving file from cache'
      self.__file = open( path, 'r' )
      self.__file.seek( 0, 2 )
      self.__size = self.__file.tell()

  def __makedirs( self, path ):

    dir = os.path.dirname( path or self.path )
    if dir and not os.path.isdir( dir ):

      if os.path.isfile( dir ):
        print 'directory %s mistaken for file' % dir
        os.remove( dir )
      else:
        self.__makedirs( dir )

      os.mkdir( dir )

  def __finalize( self ):

    self.__file.seek( 0, 2 )
    size = self.__file.tell()
    self.__file.close()

    assert size == self.__size, 'wrong file size'

    print 'Finalizing', self.__path
    os.rename( self.__file.name, Params.ROOT + self.__path )

  def __del__( self ):

    if self.__partial:
      try:
        self.__finalize()
      except:
        print 'Cache error:', sys.exc_value or sys.exc_type
        os.remove( self.__file.name )

  def getfile( self ):

    assert self.Response, 'getfile called before protocol is done'

    return self.__file

  def getsize( self ):

    assert self.Response, 'getsize called before protocol is done'

    return self.__size

  def canjoin( self ):

    return not self or self.__file


class HttpProtocol( TransferProtocol ):

  def __init__( self, request ):

    TransferProtocol.__init__( self, request )

    self.__request = request
    self.__socket = request.getsocket()

    head, args, body = request.getall()
    assert body == '', 'message body not empty'

    if self.hasincache( partial=True ):

      size, mtime = self.hasincache( partial=True )
      print 'Partial file in cache since', mtime
      args[ 'Range' ] = 'bytes=%i-' % size
      args[ 'If-Unmodified-Since' ] = mtime

    elif self.hasincache( partial=False ):

      size, mtime = self.hasincache( partial=False )
      print 'Complete file in cache since', mtime
      args[ 'If-Modified-Since' ] = mtime

    if Params.VERBOSE > 1:
      print '\n > '.join( [ 'Sending to server:', ' '.join( head ) ] + map( ': '.join, args.items() ) )

    self.__strbuf = '\r\n'.join( [ ' '.join( head ) ] + map( ': '.join, args.items() ) + [ '', '' ] )

  def send( self, sock ):

    assert self.cansend(), '__rshift__ called while no data to send'

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]

  def recv( self, sock ):

    assert not self.cansend(), '__lshift__ called while still data to send'

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
      self.setincache( partial=(0,size) )
      self.__socket.recv( headlen )
      self.Response = Response.CacheResponse

    elif head[ 1 ] == '206' and self.hasincache( partial=True ):

      range = args[ 'Content-Range' ]
      assert range.startswith( 'bytes ' ), 'invalid content-range'
      range, size = range[ 6: ].split( '/' )
      beg, end = range.split( '-' )
      size = int( size )
      beg = int( beg )
      end = int( end )
      assert size == end + 1

      self.setincache( partial=(beg,size) )
      self.__socket.recv( headlen )
      self.Response = Response.CacheResponse

    elif head[ 1 ] == '304' and self.hasincache( partial=False ):

      self.setincache( partial=False )
      self.__socket.close()
      self.Response = Response.CacheResponse

    elif head[ 1 ] == '412':
 
      print 'File has changed, resending request for complete file'

      head_, args_, body_ = request.getall()

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


class FtpProtocol( TransferProtocol ):

  def __init__( self, request ):

    TransferProcotol.__init__( self, request )

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

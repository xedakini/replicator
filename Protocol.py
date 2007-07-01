import Util, Params, Response, os, sys, time, socket


class Protocol:

  def __nonzero__( self ):
    '''\
    True iff all necessary negotiations have been made with the
    server to start data transfer.'''

    raise 'stopcondition not implemented'

  def send( self, server ):
    '''\
    No return. Sends data to server socket.'''

    raise 'sending not implemented'

  def recv( self, server ):
    '''\
    No return. Receives data from server socket.'''

    raise 'receiving not implemented'

  def getresponse( self, request ):
    '''\
    Returns Response object for final data transfer. Hands request
    and self as arguments.'''

    raise 'getresponse not implemented'

  def getfile( self ):
    '''\
    Returns cache file.'''

    raise 'getfile not implemented'

  def getsize( self ):
    '''\
    Returns target file size.'''

    raise 'getsize not implemented'

  def getsocket( self ):
    '''\
    Returns server socket.'''

    raise 'getsocket not implemented'

  def canjoin( self ):
    '''\
    True iff Protocol can stream data to multiple clients.'''

    raise 'canjoin not implemented'

  def cansend( self ):
    '''\
    True iff data is available for sending to client.'''

    raise 'cansend not implemented'


class BlindProtocol( Protocol ):

  def __init__( self, request ):

    print 'Using blind protocol'

    self.__socket = request.getsocket()
    self.__strbuf = str( request.gethead() ) + request.getbody()

  def __nonzero__( self ):

    return not self.__strbuf

  def send( self, sock ):

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]

  def getresponse( self, request ):

    return Response.BlindResponse( self, request )

  def getsocket( self ):

    return self.__socket

  def canjoin( self ):

    return False

  def cansend( self ):

    return bool( self.__strbuf )


class StaticProtocol( Protocol ):

  def __init__( self, request ):

    print 'Using static protocol'

    self.__file = open( Params.ROOT + request.getpath(), 'r' )
    self.__file.seek( 0, 2 )

  def __nonzero__( self ):

    return True

  def getsocket( self ):

    return None

  def getresponse( self, request ):

    return Response.CacheResponse( self, request )

  def getfile( self ):

    return self.__file
    
  def getsize( self ):
  
    return self.__file.tell()

  def canjoin( self ):

    return True


class TransferProtocol( Protocol ):

  def __init__( self, request ):

    assert not request.getbody(), 'http body not empty'

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

    assert self, 'getfile called prematurely'

    return self.__file

  def getsize( self ):

    assert self, 'getsize called prematurely'

    return self.__size

  def canjoin( self ):

    return not self or self.__file



class HttpProtocol( TransferProtocol ):

  def __init__( self, request ):

    TransferProtocol.__init__( self, request )

    self.__request = request
    self.__socket = request.getsocket()

    head = request.gethead()

    if self.hasincache( partial=True ):

      size, mtime = self.hasincache( partial=True )
      print 'Partial file in cache since', mtime
      head[ 'range' ] = 'bytes=%i-' % size
      head[ 'if-unmodified-since' ] = mtime

    elif self.hasincache( partial=False ):

      size, mtime = self.hasincache( partial=False )
      print 'Complete file in cache since', mtime
      head[ 'if-modified-since' ] = mtime

    if Params.VERBOSE:
      print 'Sending to server:\n%r' % head

    self.__strbuf = str( head )
    self.__response = None

  def __nonzero__( self ):

    return bool( self.__response )

  def send( self, sock ):

    assert self.cansend(), '__rshift__ called while no data to send'

    bytes = sock.send( self.__strbuf )
    self.__strbuf = self.__strbuf[ bytes: ]

  def recv( self, sock ):

    assert not self.cansend(), '__lshift__ called while still data to send'
    try:
      head = Util.Head( sock.recv( Params.MAXCHUNK, socket.MSG_PEEK ) )
    except Util.Head.ParseError:
      return

    if Params.VERBOSE:
      print 'Received from server:\n%r' % head

    if head[ 'transfer-encoding' ] == 'chunked':

      print 'Chunked data; not cached'

      self.__response = Response.BlindResponse

    elif head[ 1 ] == '200':

      size = int( head[ 'content-length' ] or -1 )
      self.setincache( partial=(0,size) )
      self.__socket.recv( len( head ) )
      self.__response = Response.CacheResponse

    elif head[ 1 ] == '206' and self.hasincache( partial=True ):

      range = head[ 'content-range' ]
      assert range and range.startswith( 'bytes ' ), 'invalid content-range'
      range, size = range[ 6: ].split( '/' )
      beg, end = range.split( '-' )
      size = int( size )
      beg = int( beg )
      end = int( end )
      assert size == end + 1

      self.setincache( partial=(beg,size) )
      self.__socket.recv( len( head ) )
      self.__response = Response.CacheResponse

    elif head[ 1 ] == '304' and self.hasincache( partial=False ):

      self.setincache( partial=False )
      self.__socket.close()
      self.__response = Response.CacheResponse

    elif head[ 1 ] == '412':
 
      print 'File has changed, resending request for complete file'

      head = self.__request.gethead()
      head[ 'range' ] = None
      head[ 'if-unmodified-since' ] = None

      if Params.VERBOSE:
        print 'Sending to server:\n%r' % head

      self.__strbuf = str( head )
      self.__socket = self.__request.getsocket()
 
    else:

      self.__response = Response.BlindResponse

  def getresponse( self, request ):

    assert self, 'getresponse called prematurely'

    return self.__response( self, request )

  def getsocket( self ):

    return self.__socket

  def cansend( self ):

    return self.__strbuf != ''


class FtpProtocol( TransferProtocol ):

  def __init__( self, request ):

    TransferProcotol.__init__( self, request )

    self.__response = None
    self.__socket = request.getsocket()
    self.__strbuf = ''

  def __nonzero__( self ):

    return bool( self.__response )

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

      if Params.VERBOSE:
        print '>', line.rstrip()

      sock.recv( len( line ) )

      if line[ 3 ] != '-':
        func = '__handle' + line[ :3 ]
        assert hasattr( self, func ), 'unknown response: %s' % line
        command = getattr( self, func )( line )
        if command:
          if Params.VERBOSE:
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
    self.__response = Response.NotFoundResponse

  def __handle150( self, line ):

    # opening connection
    end = message.rfind( ' bytes)' )
    beg = message.rfind( '(', 0, end ) + 1
    if 0 < beg < end:
      size = int( message[ beg:end ] )
    else:
      size = -1

    self.setincache( partial=(beg,end) )

    self.__response = StreamBuffer
    self.__socket = self.__datasocket

  def getresponse( self, request ):

    assert self, 'getresponse called prematurely'

    return self.__response( self, request )

  def getsocket( self ):

    return self.__socket

  def cansend( self ):

    return self.__strbuf != ''

import Params, os, sys, time, socket


class Http:

  def __init__( self ):

    self.__strbuf = ''
    self.__head = []
    self.__args = {}

  def recvhead( self, sock ):

    chunk = sock.recv( Params.MAXCHUNK, socket.MSG_PEEK )
    assert chunk, 'connection closed before sending a complete message header'

    beg, end = 0, chunk.find( '\n' ) + 1
    line = self.__strbuf + chunk[ beg:end ]

    while end:

      if line == '\r\n' or line == '\n':
        sock.recv( end )
        return True

      if not self.__head:
        self.__head = line.rstrip()
        if Params.VERBOSE:
          print 'Received', self.__head
      elif ':' in line:
        if Params.VERBOSE > 1:
          print '>', line.rstrip()
        key, value = line.split( ':', 1 )
        self.__args[ key.title() ] = value.strip()
      else:
        print 'Ignored:', line.rstrip()

      beg, end = end, chunk.find( '\n', end ) + 1
      line = chunk[ beg:end ]

    sock.recv( len( chunk ) )
    self.__strbuf = chunk[ beg: ]
    return False

  def head( self ):

    return self.__head

  def args( self, key = None ):

    if key is not None:
      return self.__args.get( key )

    return self.__args.copy()


class Cache:

  __NOTCACHABLE = object()
  __NOTINCACHE = object()
  __PARTIAL = object()
  __INCACHE = object()

  def __init__( self, request ):

    self.__file = None

    if request.cmd() != 'GET' or request.path().endswith( '/' ):
      self.__state = self.__NOTCACHABLE
      return

    path = '%s:%i' % request.addr() + request.path()
    args = path.find( '?' )
    if args != -1:
      path = path[ :args ] + path[ args: ].replace( '/', '%2F' )

    if Params.VERBOSE:
      print 'Cache position:', path

    self.__path = Params.ROOT + path

    if args != -1:
      if Params.VERBOSE:
        print 'Dynamic content; using cache write-only'
      self.__state = self.__NOTINCACHE
      return

    if os.path.isfile( self.__path + Params.SUFFIX ):
      self.__state = self.__PARTIAL
    elif os.path.isfile( self.__path ):
      self.__state = self.__INCACHE
    else:
      self.__state = self.__NOTINCACHE
      return

    stat = os.stat( self.__state is self.__PARTIAL and self.__path + Params.SUFFIX or self.__path )
    self.__size = stat.st_size
    self.__mtime = stat.st_mtime

    print self.__state is self.__PARTIAL and 'Partial' or 'Complete', 'file in cache since', time.ctime( self.__mtime )

  def cachable( self ):

    return self.__state is not self.__NOTCACHABLE

  def partial( self ):

    return self.__state is self.__PARTIAL

  def incache( self ):

    return self.__state is self.__INCACHE

  def mtime( self ):

    assert self.__file is None
    return self.__mtime

  def size( self ):

    assert self.__file is not None
    return self.__size

  def file( self ):

    assert self.__file is not None
    return self.__file

  def remove( self ):

    assert self.__file is None

    if self.__state is self.__PARTIAL:
      print 'Removing partial file from cache'
      os.remove( self.__path + Params.SUFFIX )
      if os.path.isfile( self.__path ):
        self.__state = self.__INCACHE
      else:
        self.__state = self.__NOTINCACHE
    elif self.__state is self.__INCACHE:
      print 'Removing complete file from cache'
      os.remove( self.__path )
      self.__state = self.__NOTINCACHE

  def open( self, size = None, offset = None ):

    assert self.__file is None

    if offset is not None:
      assert self.__state is self.__PARTIAL
      print 'Opening file for append at byte', offset
      self.__file = open( self.__path + Params.SUFFIX, 'a+' )
      self.__file.seek( 0, 2 )
      assert offset <= self.__file.tell() < size, 'range does not match file in cache'
      self.__file.seek( offset )
      self.__file.truncate()
      self.__size = size
    elif size is not None:
      print 'Opening new file'
      try:
        self.__makedirs( self.__path )
        self.__file = open( self.__path + Params.SUFFIX, 'w+' )
        self.__state = self.__PARTIAL
      except:
        print 'Failed to open file, falling back on tmpfile'
        self.__file = os.tmpfile()
        self.__state = self.__NOTINCACHE
      self.__size = size
    else:
      print 'Opening file read-only'
      assert self.__state is self.__INCACHE
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

    if self.__file is None or self.__state is not self.__PARTIAL:
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

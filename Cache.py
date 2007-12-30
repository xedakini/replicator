import Params, os


def makedirs( path ):

  dir = os.path.dirname( path )
  if dir and not os.path.isdir( dir ):
    if os.path.isfile( dir ):
      print 'directory %s mistaken for file' % dir
      os.remove( dir )
    else:
      makedirs( dir )
    os.mkdir( dir )


class File:

  size = -1
  mtime = -1

  def __init__( self, path ):

    sep = path.find( '?' )
    if sep != -1:
      path = path[ :sep ] + path[ sep: ].replace( '/', '%2F' )
    if Params.VERBOSE:
      print 'Cache position:', path

    self.__path = Params.ROOT + path
    self.__file = None

  def partial( self ):

    return os.path.isfile( self.__path + Params.SUFFIX ) and os.stat( self.__path + Params.SUFFIX )

  def full( self ):

    return os.path.isfile( self.__path ) and os.stat( self.__path )

  def open_new( self ):

    print 'Opening new file'
    try:
      makedirs( self.__path )
      self.__file = open( self.__path + Params.SUFFIX, 'w+' )
    except:
      print 'Failed to open file, falling back on tmpfile'
      self.__file = os.tmpfile()

  def open_partial( self, offset=-1 ):

    self.mtime = os.stat( self.__path + Params.SUFFIX ).st_mtime
    self.__file = open( self.__path + Params.SUFFIX, 'a+' )
    if offset >= 0:
      assert offset <= self.tell(), 'range does not match file in cache'
      self.__file.seek( offset )
      self.__file.truncate()
    print 'Opening file for append at byte', self.tell()

  def open_full( self ):

    print 'Opening file read-only'
    self.mtime = os.stat( self.__path ).st_mtime
    self.__file = open( self.__path, 'r' )
    self.size = self.tell()

  def remove_full( self ):

    print 'Removing complete file from cache'
    os.remove( self.__path )

  def remove_partial( self ):

    print 'Removing partial file from cache'
    os.remove( self.__path + Params.SUFFIX )

  def read( self, pos, size ):

    self.__file.seek( pos )
    return self.__file.read( size )

  def write( self, chunk ):

    self.__file.seek( 0, 2 )
    return self.__file.write( chunk )

  def tell( self ):

    self.__file.seek( 0, 2 )
    return self.__file.tell()

  def close( self ):

    size = self.tell()
    self.__file.close()
    os.utime( self.__path + Params.SUFFIX, ( self.mtime, self.mtime ) )
    if self.size == size:
      os.rename( self.__path + Params.SUFFIX, self.__path )
      print 'Finalized', self.__path

  def __del__( self ):

    try:
      self.close()
    except:
      pass
